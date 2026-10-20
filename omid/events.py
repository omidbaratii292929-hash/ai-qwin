"""omid.events — گذرگاه رویداد و لاگ حسابرسی با redaction داده‌های حساس.

هر رویداد مهم سامانه (تغییر حالت ایمنی، اجرای ابزار، خطاها، عملیات کنترلی)
به‌صورت ساختاریافته ثبت می‌شود تا پروژه «قابل‌ممیزی» باشد. مقادیر کلیدهایی
که شبیه راز هستند (token, secret, password, ...) پیش از نوشتن روی دیسک
پنهان‌سازی (redact) می‌شوند.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import json
import re
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEVERITIES: tuple[str, ...] = ("debug", "info", "warning", "error", "critical", "audit")
AUDITED_SEVERITIES: frozenset[str] = frozenset({"audit", "warning", "error", "critical"})

_SENSITIVE_KEY = re.compile(r"(token|secret|password|passwd|credential|api[_-]?key|authorization)", re.I)
_REDACTED = "***REDACTED***"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact(obj: Any, _depth: int = 0) -> Any:
    """پنهان‌سازی بازگشتی مقادیر حساس در dict/list."""
    if _depth > 6:
        return "***DEPTH-LIMIT***"
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if isinstance(key, str) and _SENSITIVE_KEY.search(key):
                out[key] = _REDACTED
            else:
                out[key] = redact(value, _depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(v, _depth + 1) for v in obj]
    return obj


@dataclass
class Event:
    """یک رویداد ساختاریافتهٔ سامانه."""

    type: str
    message: str
    severity: str = "info"
    source: str = "omid"
    data: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            self.severity = "info"

    def to_dict(self, *, redacted: bool = True) -> dict[str, Any]:
        data = redact(self.data) if redacted else self.data
        return {
            "ts": self.ts,
            "type": self.type,
            "severity": self.severity,
            "source": self.source,
            "message": self.message,
            "data": data,
        }


class EventBus:
    """گذرگاه رویداد ساده و همگام با حافظهٔ کوتاه‌مدت رویدادها."""

    def __init__(self, history_size: int = 1000) -> None:
        self._subscribers: list[Callable[[Event], None]] = []
        self._history: deque[Event] = deque(maxlen=history_size)
        self._lock = threading.RLock()
        self.last_subscriber_error: str | None = None

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def publish(self, event: Event) -> None:
        with self._lock:
            self._history.append(event)
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception as exc:  # noqa: BLE001 - subscriber failure must not break the bus
                self.last_subscriber_error = f"{callback!r}: {exc}"

    def history(
        self,
        limit: int = 100,
        *,
        severity: str | None = None,
        type_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._history)
        if severity:
            events = [e for e in events if e.severity == severity]
        if type_prefix:
            events = [e for e in events if e.type.startswith(type_prefix)]
        return [e.to_dict() for e in events[-limit:]]


class AuditLog:
    """لاگ حسابرسی روی دیسک (JSONL) با redaction خودکار."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, event: Event) -> bool:
        """نوشتن یک رویداد؛ در صورت خطای دیسک False برمی‌گرداند (بدون crash)."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(event.to_dict(redacted=True), ensure_ascii=False)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            return True
        except OSError:
            return False

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
