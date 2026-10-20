"""omid.safety — لایهٔ ایمنی و کنترل عملیات.

این بسته مستقل از مدل زبانی است؛ تصمیم‌های ایمنی هرگز توسط LLM دور زده
نمی‌شوند. مسیر توقف اضطراری (E-Stop) کاملاً مستقل از عامل هوشمند عمل
می‌کند.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
"""
from __future__ import annotations

from omid.safety.modes import CONTROL_CONFIRM_PHRASE, ESTOP_RELEASE_PHRASE, OperationMode, SafetyManager
from omid.safety.validator import MotionCommand, screen_gcode_line, validate_motion

__all__ = [
    "CONTROL_CONFIRM_PHRASE",
    "ESTOP_RELEASE_PHRASE",
    "MotionCommand",
    "OperationMode",
    "SafetyManager",
    "screen_gcode_line",
    "validate_motion",
]
