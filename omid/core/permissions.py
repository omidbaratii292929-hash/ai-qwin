"""omid.core.permissions — سطح‌بندی ریسک ابزارها و سیاست مجوزها.

چهار سطح ریسک (اصل حداقل سطح دسترسی):

- ``read``     : خواندن وضعیت/تحلیل — در همهٔ حالت‌ها مجاز.
- ``suggest``  : تولید پیشنهاد بدون اثر اجرایی.
- ``simulate`` : اثر روی شبیه‌ساز/داده — بدون تماس با سخت‌افزار.
- ``physical`` : اثر فیزیکی واقعی — فقط در حالت control با قفل‌های ایمنی.

اجرای واقعی از :class:`omid.safety.modes.SafetyManager` استعلام می‌شود
(duck-typing تا وابستگی حلقوی ایجاد نشود)؛ این ماژول علاوه بر آن یک
kill-switch سطح ابزار (غیرفعال‌سازی دستی ابزار خاص) فراهم می‌کند.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import threading
from enum import Enum

from omid.errors import PermissionDenied


class RiskLevel(str, Enum):
    READ = "read"
    SUGGEST = "suggest"
    SIMULATE = "simulate"
    PHYSICAL = "physical"


class PermissionPolicy:
    """سیاست مجوز: دروازهٔ ریسک (از مدیر ایمنی) + kill-switch سطح ابزار."""

    def __init__(self, safety_manager) -> None:  # duck-typed SafetyManager
        self._safety = safety_manager
        self._disabled_tools: set[str] = set()
        self._lock = threading.RLock()

    def disable_tool(self, tool_name: str) -> None:
        with self._lock:
            self._disabled_tools.add(tool_name)

    def enable_tool(self, tool_name: str) -> None:
        with self._lock:
            self._disabled_tools.discard(tool_name)

    def disabled_tools(self) -> list[str]:
        with self._lock:
            return sorted(self._disabled_tools)

    def check(self, tool_name: str, risk: RiskLevel | str, *, control_granted: bool = False) -> None:
        """بررسی کامل مجوز؛ در صورت نقض PermissionDenied با دلیل صادقانه."""
        risk_value = risk.value if isinstance(risk, RiskLevel) else str(risk)
        with self._lock:
            if tool_name in self._disabled_tools:
                raise PermissionDenied(f"ابزار «{tool_name}» به‌صورت دستی غیرفعال شده است.")
        if risk_value == RiskLevel.PHYSICAL.value and not control_granted:
            raise PermissionDenied(
                f"ابزار «{tool_name}» ریسک فیزیکی دارد و اعتبار کنترل ارائه نشده است "
                "(OMID_CONTROL_TOKEN لازم است)."
            )
        # دروازهٔ حالت/توقف اضطراری — توسط مدیر ایمنی
        self._safety.assert_allowed(risk_value, context=f"tool={tool_name}")
