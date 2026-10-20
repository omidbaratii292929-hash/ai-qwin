"""omid.core.agent — حلقهٔ عامل هوشمند: تحلیل هدف → برنامه‌ریزی → اجرا → شاهد.

تفکیک تصمیم از اجرا (اصل بنیادین):
- برنامه‌ریز LLM (در صورت سلامت Ollama) فقط «نام ابزار + آرگومان» از
  فهرست ابزارهای **ثبت‌شده** پیشنهاد می‌دهد (JSON ساختاریافته).
- هر پیشنهاد پیش از اجرا اعتبارسنجی می‌شود؛ ابزار ناشناخته یا آرگومان
  نامعتبر صادقانه رد می‌شود و به برنامه‌ریز قواعد-محور بازمی‌گردیم.
- خروجی متنی مدل **هرگز** مستقیماً اجرا نمی‌شود (بدون shell، بدون G-code خام).
- در نبود مدل، موتور قواعد-محور (کلیدواژه‌های فارسی/انگلیسی) سامانه را
  کاربردی نگه می‌دارد.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from omid.core.tasks import Step, Task, TaskManager, TaskStatus
from omid.core.tools import ToolResult

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

# موتور قواعد-محور: (کلیدواژه‌ها، ابزار، سازندهٔ آرگومان)
# ترتیب مهم است — اولین تطابق برنده است.
_INTENT_RULES: list[tuple[tuple[str, ...], str]] = [
    (("توقف اضطراری", "estop", "emergency stop", "قطع اضطراری"), "trigger_estop"),
    (("درباره", "هویت", "برند", "about", "branding", "سازنده"), "get_branding"),
    (("کمک", "راهنما", "چه کار", "capability", "help", "abilities"), "describe_capabilities"),
    (("کشف", "اسکن", "discover", "scan", "شناسایی دستگاه"), "discover_devices"),
    (("عیب", "خطا", "تشخیص", "هشدار", "diagnos", "fault", "anomal", "بررسی فنی", "نگهداری"), "run_diagnostics"),
    (("شبیه‌ساز", "شبیه‌سازی", "simulate", "simulation", "پیش‌نمایش حرکت"), "simulate_motion"),
    (("دانش", "مستند", "راهنمای فنی", "knowledge", "document", "rag"), "query_knowledge"),
    (("حافظه", "سابقه", "ترجیح", "memory", "recall", "history"), "recall_memory"),
    (("تجهیزات", "دستگاه", "device", "hardware", "سخت‌افزار", "درایور"), "list_devices"),
    (("وضعیت", "سلامت", "status", "health", "state", "چطوری"), "system_status"),
]


class AgentRuntime:
    """عامل هوشمند OMID — هماهنگ‌کنندهٔ ابزارها، وظایف و ایمنی."""

    PLANNER_SYSTEM_PROMPT = (
        "You are the planning module of OMID Industrial AI Agent. "
        "Reply ONLY with compact JSON: {\"steps\": [{\"tool\": NAME, \"args\": {...}}]} using at most 4 steps. "
        "Only use tools from the provided allowlist. Never invent tools. Never output raw G-code or shell commands. "
        "If the request is unsafe or unsupported, return {\"steps\": [], \"note\": REASON}."
    )

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.tasks: TaskManager = ctx.tasks

    # ================== ورودی اصلی ==================
    def handle_request(
        self,
        text: str,
        *,
        requested_by: str = "api",
        control_granted: bool = False,
        timeout_s: float = 60.0,
    ) -> Task:
        text = (text or "").strip()
        task = self.tasks.create(goal=text or "(خالی)", requested_by=requested_by)
        if not text:
            self.tasks.update(task, status=TaskStatus.FAILED.value, error="درخواست خالی است.")
            task.result_summary = "درخواست خالی بود؛ چیزی اجرا نشد."
            return task

        plan, planner = self._plan(text)
        task.planner = planner
        if not plan:
            self.tasks.update(task, status=TaskStatus.COMPLETED.value)
            task.result_summary = (
                "هدف قابل نگاشت به هیچ ابزار مجازی نبود (صادقانه: عملیاتی انجام نشد). "
                "برای دیدن قابلیت‌ها درخواست «کمک» بفرستید."
            )
            return task

        task.steps = [Step(tool=p["tool"], args=p.get("args") or {}) for p in plan]
        self._execute(task, start_index=0, control_granted=control_granted, timeout_s=timeout_s)
        return task

    # ================== برنامه‌ریزی ==================
    def _plan(self, text: str) -> tuple[list[dict[str, Any]], str]:
        """تولید برنامهٔ ابزارها؛ ابتدا LLM (در صورت سلامت) و سپس قواعد."""
        note = ""
        if self.ctx.ai_available():
            llm_plan = self._plan_with_llm(text)
            if llm_plan is not None:
                return llm_plan, "llm"
            note = " (برنامه‌ریز LLM ناموفق بود؛ به موتور قواعد-محور بازگشتیم)"
        else:
            note = " (مدل زبانی محلی در دسترس نیست؛ موتور قواعد-محور)"
        return self._plan_with_rules(text), "rule-based" + note

    def _plan_with_llm(self, text: str) -> list[dict[str, Any]] | None:
        allowed = self.ctx.tools.describe()
        user_prompt = (
            f"Allowed tools (JSON):\n{json.dumps(allowed, ensure_ascii=False)}\n\n"
            f"User request (Persian or English):\n{text}\n\nProduce the JSON plan now."
        )
        result = self.ctx.ai.chat(
            [
                {"role": "system", "content": self.PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
        if not result.ok:
            self.ctx.audit_event(
                "agent.llm_unavailable",
                f"برنامه‌ریز LLM ناموفق بود: {result.error}",
                severity="warning",
            )
            return None
        parsed = self._parse_llm_plan(result.text, allowed_names={t["name"] for t in allowed})
        if parsed is None:
            self.ctx.audit_event(
                "agent.llm_invalid_plan",
                "خروجی LLM برنامهٔ JSON معتبر/مجاز نبود؛ رد شد (خروجی مدل هرگز مستقیم اجرا نمی‌شود).",
                data={"raw_preview": result.text[:300]},
                severity="warning",
            )
        return parsed

    def _parse_llm_plan(self, raw: str, *, allowed_names: set[str]) -> list[dict[str, Any]] | None:
        """اعتبارسنجی سخت‌گیرانهٔ خروجی مدل: فقط JSON، فقط ابزار مجاز."""
        raw = raw.strip()
        # تحمل مدل‌هایی که JSON را در markdown می‌پیچند
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
        candidate = fence.group(1) if fence else raw
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return None
        steps_raw = data.get("steps")
        if not isinstance(steps_raw, list):
            return None
        steps: list[dict[str, Any]] = []
        for item in steps_raw[:4]:
            if not isinstance(item, dict):
                continue
            name = item.get("tool")
            args = item.get("args")
            if not isinstance(name, str) or name not in allowed_names:
                continue  # ابزار ناشناخته/نامعتبر → صادقانه حذف می‌شود
            if args is not None and not isinstance(args, dict):
                continue
            steps.append({"tool": name, "args": args or {}})
        return steps if steps else None

    def _plan_with_rules(self, text: str) -> list[dict[str, Any]]:
        lowered = text.lower()
        for keywords, tool in _INTENT_RULES:
            if any(k in lowered for k in keywords):
                return [{"tool": tool, "args": self._rule_args(tool, text)}]
        return [{"tool": "describe_capabilities", "args": {"note": "هدف ناشناخته بود؛ فهرست قابلیت‌ها"}}]

    def _rule_args(self, tool: str, text: str) -> dict[str, Any]:
        if tool == "trigger_estop":
            return {"reason": text[:200]}
        if tool in {"query_knowledge", "recall_memory"}:
            return {"query": text}
        if tool == "simulate_motion":
            return self._parse_motion(text)
        if tool == "discover_devices":
            scope = "network" if any(k in text.lower() for k in ("شبکه", "network", "modbus", "mqtt")) else "serial"
            return {"scope": scope}
        return {}

    @staticmethod
    def _parse_motion(text: str) -> dict[str, Any]:
        """استخراج اعداد به‌ترتیب x, y, z, feed از متن (قواعد-محور)."""
        nums = [float(n) for n in _NUMBER.findall(text)][:4]
        args: dict[str, Any] = {}
        for key, value in zip(("x", "y", "z", "feed"), nums, strict=False):
            args[key] = value
        return args

    # ================== اجرا ==================
    def _execute(
        self,
        task: Task,
        *,
        start_index: int,
        control_granted: bool,
        timeout_s: float,
    ) -> None:
        self.tasks.update(task, status=TaskStatus.RUNNING.value)
        deadline = time.monotonic() + timeout_s
        index = start_index
        while index < len(task.steps):
            if task.cancel_requested:
                self._finish(task, TaskStatus.CANCELLED.value, error="وظیفه توسط کاربر لغو شد.")
                return
            if time.monotonic() > deadline:
                self._finish(
                    task, TaskStatus.FAILED.value, error=f"وظیفه پس از {timeout_s:.0f}s زمان‌خورده لغو شد."
                )
                return
            step = task.steps[index]
            tool = self.ctx.tools.get(step.tool)
            if (
                tool is not None
                and tool.risk.value == "physical"
                and control_granted
                and step.status != "confirmed"
            ):
                # عملیات فیزیکی حتی با اعتبار کنترل هم نیازمند تأیید صریح انسانی است
                step.status = "awaiting_confirm"
                self.tasks.update(task, status=TaskStatus.WAITING_CONFIRM.value)
                task.pending_index = index
                self.ctx.audit_event(
                    "agent.confirm_required",
                    f"وظیفه {task.id} در انتظار تأیید صریح عملیات فیزیکی است (مرحله {index}).",
                    data={"task": task.id, "tool": step.tool},
                    severity="audit",
                )
                self.tasks.register_resume(
                    task.id,
                    lambda idx=index, cg=control_granted, t=task: self._execute(
                        t, start_index=idx, control_granted=cg, timeout_s=timeout_s
                    ),
                )
                return
            result: ToolResult = self.ctx.tools.invoke(
                step.tool, step.args, self.ctx, control_granted=control_granted, audit=self.ctx.audit_event
            )
            step.status = "done" if result.ok else ("denied" if result.denied else "failed")
            step.result = result.data
            step.error = result.error
            step.evidence = result.evidence
            if not result.ok:
                self._finish(task, TaskStatus.FAILED.value, error=result.error)
                return
            index += 1
        self._finish(task, TaskStatus.COMPLETED.value)

    def _finish(self, task: Task, status: str, *, error: str | None = None) -> None:
        """پایان وظیفه: ثبت وضعیت، خلاصه و حافظهٔ عملیات (برای همهٔ حالات پایانی)."""
        self.tasks.update(task, status=status, error=error)
        task.result_summary = self._summarize(task)
        try:
            self.ctx.memory.record_operation(task.id, task.goal, task.status, task.result_summary or "")
        except Exception:  # noqa: BLE001 - حافظه نباید مانع پایان وظیفه شود
            pass

    def confirm_task(self, task_id: str, *, control_granted: bool) -> Task | None:
        """ادامهٔ وظیفهٔ منتظر تأیید — فقط با اعتبار کنترل."""
        task = self.tasks.get(task_id)
        if task is None:
            return None
        if task.status != TaskStatus.WAITING_CONFIRM.value:
            return task
        if not control_granted:
            task.error = "تأیید بدون اعتبار کنترل ممکن نیست."
            self.tasks.update(task, status=TaskStatus.FAILED.value, error=task.error)
            return task
        resume = self.tasks.take_resume(task_id)
        if resume is None:
            self.tasks.update(task, status=TaskStatus.FAILED.value, error="مسیر ادامهٔ وظیفه یافت نشد.")
            return task
        if task.pending_index is not None and task.pending_index < len(task.steps):
            task.steps[task.pending_index].status = "confirmed"  # تأیید انسانی ثبت شد؛ حلقهٔ تأیید تکرار نمی‌شود
        self.ctx.audit_event(
            "agent.confirmed",
            f"عملیات فیزیکی وظیفه {task_id} با تأیید صریح انسانی ادامه یافت.",
            data={"task": task_id},
            severity="audit",
        )
        resume()
        return task

    # ================== گزارش ==================
    def _summarize(self, task: Task) -> str:
        """خلاصهٔ فارسی و روشن نتیجه با برچسب صادقانهٔ حالت."""
        mode = self.ctx.safety.mode
        lines = [f"وظیفه «{task.goal[:60]}» — وضعیت: {task.status} — حالت سامانه: {mode}"]
        for i, step in enumerate(task.steps, 1):
            mark = {"done": "✔", "failed": "✖", "denied": "⛔", "skipped": "–"}.get(step.status, "…")
            detail = step.error if step.error else _short(step.result)
            lines.append(f"{mark} مرحله {i} [{step.tool}]: {detail}")
        if mode != "control":
            lines.append("توجه: هیچ فرمان فیزیکی در این حالت صادر نشده است (شبیه‌سازی/مشاهده).")
        return "\n".join(lines)


def _short(value: Any, limit: int = 160) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = repr(value)
    return text if len(text) <= limit else text[:limit] + "…"
