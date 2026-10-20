"""omid.core.tasks — چرخهٔ حیات وظایف: ایجاد، اجرا، تأیید، لغو و timeout.

هر درخواست کاربر به یک :class:`Task` تبدیل می‌شود که مراحل (steps) آن
کاملاً ثبت و قابل‌بازبینی است. وظایف دارای مرحلهٔ فیزیکی می‌توانند در
وضعیت ``waiting_confirm`` متوقف شوند و فقط با تأیید صریح انسانی ادامه
یابند.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from omid.events import utc_now_iso


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_CONFIRM = "waiting_confirm"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset(
    {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value}
)


@dataclass
class Step:
    """یک مرحله از وظیفه: فراخوانی یک ابزار مشخص."""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending | done | failed | denied | skipped | awaiting_confirm
    result: Any = None
    error: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "args": self.args,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "evidence": self.evidence,
        }


@dataclass
class Task:
    """وظیفهٔ کامل عامل با وضعیت، مراحل و شواهد اجرا."""

    id: str
    goal: str
    status: str = TaskStatus.PENDING.value
    planner: str = "rule-based"
    requested_by: str = "unknown"
    steps: list[Step] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    error: str | None = None
    result_summary: str | None = None
    cancel_requested: bool = False
    pending_index: int | None = None  # نقطهٔ توقف برای تأیید فیزیکی

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "planner": self.planner,
            "requested_by": self.requested_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "result_summary": self.result_summary,
            "steps": [s.to_dict() for s in self.steps],
        }


class TaskManager:
    """ثبت و پیگیری وظایف (thread-safe)."""

    def __init__(self, history_size: int = 200) -> None:
        self._tasks: dict[str, Task] = {}
        self._order: list[str] = []
        self._lock = threading.RLock()
        self._history_size = history_size
        # resumable closures برای وظایف منتظر تأیید
        self._pending_resumes: dict[str, Any] = {}

    def create(self, goal: str, *, planner: str = "rule-based", requested_by: str = "unknown") -> Task:
        task = Task(id=uuid.uuid4().hex[:12], goal=goal, planner=planner, requested_by=requested_by)
        with self._lock:
            self._tasks[task.id] = task
            self._order.append(task.id)
            while len(self._order) > self._history_size:
                old = self._order.pop(0)
                self._tasks.pop(old, None)
                self._pending_resumes.pop(old, None)
        return task

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            ids = list(self._order)[-limit:]
            return [self._tasks[i].to_dict() for i in reversed(ids)]

    def update(self, task: Task, *, status: str | None = None, error: str | None = None) -> Task:
        with self._lock:
            if status is not None:
                task.status = status
            if error is not None:
                task.error = error
            task.updated_at = utc_now_iso()
        return task

    def request_cancel(self, task_id: str) -> bool:
        """درخواست لغو همکاری‌جویانه (بین مراحل بررسی می‌شود)."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status in TERMINAL_STATUSES:
                return False
            task.cancel_requested = True
            if task.status == TaskStatus.WAITING_CONFIRM.value:
                task.status = TaskStatus.CANCELLED.value
                task.updated_at = utc_now_iso()
                self._pending_resumes.pop(task_id, None)
            return True

    def register_resume(self, task_id: str, resume_fn: Any) -> None:
        with self._lock:
            self._pending_resumes[task_id] = resume_fn

    def take_resume(self, task_id: str) -> Any:
        with self._lock:
            return self._pending_resumes.pop(task_id, None)
