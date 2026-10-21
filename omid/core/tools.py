"""omid.core.tools — رجیستری ابزارها با دروازهٔ مجوز، timeout و حسابرسی.

هر ابزار یک واحد قابلیت صریح و محدود است (فهرست مشخص ابزارهای مجاز).
خروجی مدل زبانی فقط می‌تواند به همین ابزارهای ثبت‌شده نگاشت شود؛ ابزار
ناشناخته صادقانه رد می‌شود. اجرای هر ابزار:

1. بررسی مجوز (ریسک × حالت ایمنی × اعتبار کنترل × kill-switch)
2. اجرا با timeout محافظت‌شده
3. ثبت حسابرسی پیش و پس از اجرا (با redaction خودکار)
4. بازگرداندن نتیجهٔ ساختاریافته همراه با «شاهد» (evidence)

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Any

from omid.core.permissions import PermissionPolicy, RiskLevel
from omid.errors import PermissionDenied, SafetyError, ToolError
from omid.events import redact, utc_now_iso


@dataclass
class ToolResult:
    """نتیجهٔ ساختاریافتهٔ اجرای ابزار + شاهد قابل‌بررسی."""

    ok: bool
    data: Any = None
    error: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    denied: bool = False  # True اگر به‌دلیل مجوز/ایمنی رد شده باشد

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "evidence": self.evidence,
            "denied": self.denied,
        }


@dataclass
class Tool:
    """تعریف یک ابزار مجاز."""

    name: str
    description: str
    risk: RiskLevel
    handler: Callable[[dict[str, Any], Any], ToolResult]  # (args, ctx) -> ToolResult
    timeout_s: float = 30.0
    requires: tuple[str, ...] = ()  # قابلیت‌های لازم مثل "driver:grbl"


class ToolRegistry:
    """رجیستری مرکزی ابزارها — تنها مسیر اجرای قابلیت‌ها."""

    def __init__(self, policy: PermissionPolicy, *, executor: ThreadPoolExecutor | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._policy = policy
        self._executor = executor or ThreadPoolExecutor(max_workers=4, thread_name_prefix="omid-tool")
        self._lock = threading.RLock()

    def register(self, tool: Tool) -> None:
        if not tool.name or not callable(tool.handler):
            raise ToolError("ابزار باید نام و handler معتبر داشته باشد.")
        with self._lock:
            if tool.name in self._tools:
                raise ToolError(f"ابزار «{tool.name}» قبلاً ثبت شده است.")
            self._tools[tool.name] = tool

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._tools)

    def get(self, name: str) -> Tool | None:
        with self._lock:
            return self._tools.get(name)

    def describe(self) -> list[dict[str, Any]]:
        """شرح ابزارها برای انسان و برای prompt برنامه‌ریز (فقط نام‌های مجاز)."""
        with self._lock:
            tools = list(self._tools.values())
        return [
            {"name": t.name, "description": t.description, "risk": t.risk.value, "requires": list(t.requires)}
            for t in sorted(tools, key=lambda t: t.name)
        ]

    def invoke(
        self,
        name: str,
        args: dict[str, Any] | None,
        ctx: Any,
        *,
        control_granted: bool = False,
        audit: Callable[..., None] | None = None,
    ) -> ToolResult:
        """اجرای محافظت‌شدهٔ یک ابزار؛ هرگز exception بیرون نمی‌دهد."""
        audit = audit or (lambda *a, **k: None)
        args = args if isinstance(args, dict) else {}
        tool = self.get(name)
        if tool is None:
            # صداقت: ابزار ناشناخته را وانمود نمی‌کنیم
            return ToolResult(
                ok=False,
                error=f"ابزار «{name}» در فهرست ابزارهای مجاز وجود ندارد. ابزارهای موجود: {self.names()}",
                evidence={"tool": name, "ts": utc_now_iso(), "granted": False},
            )

        evidence: dict[str, Any] = {
            "tool": name,
            "risk": tool.risk.value,
            "control_granted": control_granted,
            "ts": utc_now_iso(),
        }
        try:
            self._policy.check(name, tool.risk, control_granted=control_granted)
        except (PermissionDenied, SafetyError) as exc:
            evidence.update(granted=False, denied_reason=str(exc))
            audit(
                "tool.denied",
                f"اجرای ابزار «{name}» رد شد: {exc}",
                data={"tool": name, "risk": tool.risk.value, "reason": str(exc)},
                severity="warning",
            )
            return ToolResult(ok=False, error=str(exc), evidence=evidence, denied=True)

        audit(
            "tool.invoked",
            f"اجرای ابزار «{name}» با ریسک {tool.risk.value} آغاز شد.",
            data={"tool": name, "risk": tool.risk.value, "args": args},
            severity="audit",
        )
        started = time.monotonic()
        try:
            future = self._executor.submit(tool.handler, args, ctx)
            result = future.result(timeout=tool.timeout_s)
        except FuturesTimeoutError:
            cancelled_before_start = future.cancel()
            timeout_evidence: dict[str, Any] = {
                "timed_out": True,
                "cancelled_before_start": cancelled_before_start,
                "execution_may_continue": not cancelled_before_start,
            }
            if cancelled_before_start:
                timeout_error = f"ابزار «{name}» پس از {tool.timeout_s}s زمان‌خورده شد و پیش از شروع لغو شد."
            else:
                timeout_error = (
                    f"ابزار «{name}» پس از {tool.timeout_s}s زمان‌خورده شد؛ لغو اجرای شروع‌شده تضمین‌شده نیست "
                    "و ممکن است در پس‌زمینه ادامه یابد. وضعیت را بررسی کنید و از اجرای فوری مجدد خودداری کنید."
                )
            if tool.risk == RiskLevel.PHYSICAL and not cancelled_before_start:
                reason = f"Tool timeout: {name}"
                safety = getattr(ctx, "safety", None)
                if safety is not None:
                    try:
                        snapshot = safety.trigger_estop(reason, source="tool_timeout")
                        timeout_evidence["logical_estop_active"] = bool(snapshot.get("estop_active"))
                    except Exception as stop_exc:  # noqa: BLE001 - timeout handling must remain fail-safe
                        timeout_evidence["logical_estop_error"] = type(stop_exc).__name__
                driver = getattr(ctx, "grbl", None)
                if driver is not None:
                    try:
                        stop_result = driver.estop(reason)
                        stop_data = getattr(stop_result, "data", None) or {}
                        timeout_evidence["driver_stop_requested"] = bool(stop_data.get("stop_commands_sent"))
                        timeout_evidence["physical_stop_confirmed"] = stop_data.get("physical_stop_confirmed") is True
                        timeout_evidence["driver_stop_source"] = getattr(stop_result, "source", None)
                    except Exception as stop_exc:  # noqa: BLE001
                        timeout_evidence["driver_stop_error"] = type(stop_exc).__name__
                timeout_error += (
                    " به‌دلیل ریسک فیزیکی، توقف اضطراری نرم‌افزاری و درخواست توقف درایور نیز تلاش شد؛ "
                    "این کار توقف فیزیکی را تضمین یا تأیید نمی‌کند."
                )
                audit(
                    "tool.timeout_estop",
                    f"ابزار فیزیکی «{name}» timeout شد؛ توقف اضطراری بهترین‌تلاش اجرا شد.",
                    data={"tool": name, **timeout_evidence},
                    severity="critical",
                )
            audit(
                "tool.timeout",
                f"ابزار «{name}» از مهلت {tool.timeout_s}s عبور کرد.",
                data={"tool": name, "risk": tool.risk.value, **timeout_evidence},
                severity="critical" if tool.risk == RiskLevel.PHYSICAL else "error",
            )
            result = ToolResult(ok=False, error=timeout_error, evidence=timeout_evidence)
        except Exception as exc:  # noqa: BLE001 - tool failures are reported, not propagated
            result = ToolResult(ok=False, error=f"خطای اجرای ابزار «{name}»: {type(exc).__name__}: {exc}")
        elapsed_ms = round((time.monotonic() - started) * 1000, 2)
        if not isinstance(result, ToolResult):
            result = ToolResult(ok=False, error=f"خروجی ابزار «{name}» از نوع معتبر ToolResult نبود.")
        result.evidence = {**evidence, "granted": True, "elapsed_ms": elapsed_ms, **result.evidence}
        audit(
            "tool.completed" if result.ok else "tool.failed",
            f"ابزار «{name}» {'با موفقیت اجرا شد' if result.ok else 'ناموفق بود'} ({elapsed_ms}ms).",
            data={"tool": name, "ok": result.ok, "error": result.error, "result_preview": _preview(result.data)},
            severity="audit" if result.ok else "error",
        )
        return result


def _preview(data: Any, limit: int = 400) -> Any:
    """پیش‌نمایش کوتاه و redact‌شده از نتیجه برای لاگ حسابرسی."""
    safe = redact(data)
    text = repr(safe)
    return text if len(text) <= limit else text[:limit] + "…"
