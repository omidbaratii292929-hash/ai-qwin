"""omid.twin.simulator — Digital Twin با برچسب‌های صریح Simulation/Live.

- :meth:`DigitalTwin.preview_motion` حرکت را فقط روی مدل نرم‌افزاری اعمال
  می‌کند و نتیجه همیشه ``source="simulation"`` دارد.
- :meth:`DigitalTwin.run_scenario` یک سناریوی چندمرحله‌ای را از مسیر
  رجیستری ابزارها dry-run می‌کند؛ دروازه‌های ایمنی فعال‌اند، بنابراین
  مراحل فیزیکی صادقانه رد می‌شوند (نه وانمود).
- وضعیت live فقط وقتی پر می‌شود که درایور واقعاً متصل باشد و خواندن
  وضعیت زنده موفق شود؛ در غیر این صورت ``None`` است.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from omid.errors import ValidationError
from omid.events import utc_now_iso
from omid.safety.validator import MotionCommand, validate_motion


@dataclass
class TwinState:
    """وضعیت تخمینی یک دستگاه در مدل نرم‌افزاری."""

    device_id: str
    position: dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    status: str = "Idle"
    source: str = "simulation"  # همیشه simulation برای twin
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "position": self.position,
            "status": self.status,
            "source": self.source,
            "updated_at": self.updated_at,
        }


class DigitalTwin:
    """مدل نرم‌افزاری دستگاه‌ها + اجرای سناریوی آزمایشی بدون سخت‌افزار."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self._states: dict[str, TwinState] = {}
        self._lock = threading.RLock()

    def state(self, device_id: str) -> TwinState:
        with self._lock:
            if device_id not in self._states:
                self._states[device_id] = TwinState(device_id=device_id)
            return self._states[device_id]

    def preview_motion(self, device_id: str, cmd: MotionCommand) -> dict[str, Any]:
        """پیش‌نمایش/شبیه‌سازی حرکت با اعتبارسنجی کامل محدوده — بدون سخت‌افزار."""
        limits = self.ctx.config.limits
        try:
            validate_motion(cmd, limits)
        except ValidationError as exc:
            return {"ok": False, "error": str(exc), "source": "simulation"}
        twin = self.state(device_id)
        with self._lock:
            for axis in ("x", "y", "z"):
                value = getattr(cmd, axis)
                if value is not None:
                    twin.position[axis] = value
            twin.status = "Idle (simulated move applied)"
            twin.updated_at = utc_now_iso()
        self.ctx.audit_event(
            "twin.preview_motion",
            f"حرکت روی twin شبیه‌سازی شد ({device_id}): {cmd.to_gcode()}",
            data={"device": device_id, **cmd.to_dict()},
        )
        return {
            "ok": True,
            "device_id": device_id,
            "gcode_preview": cmd.to_gcode(),
            "estimated_position": dict(twin.position),
            "source": "simulation",
            "note": "این نتیجه شبیه‌سازی است، نه اندازه‌گیری زنده.",
        }

    def run_scenario(self, steps: list[dict[str, Any]]) -> dict[str, Any]:
        """dry-run یک سناریوی چندمرحله‌ای از مسیر ابزارها (بدون کنترل سخت‌افزار)."""
        transcript: list[dict[str, Any]] = []
        for i, spec in enumerate(steps[:10], 1):
            tool_name = spec.get("tool")
            args = spec.get("args") or {}
            if not isinstance(tool_name, str):
                transcript.append({"step": i, "ok": False, "error": "نام ابزار نامعتبر است."})
                continue
            # در سناریوی شبیه‌سازی اعتبار کنترل هرگز اعطا نمی‌شود → مراحل فیزیکی رد می‌شوند
            result = self.ctx.tools.invoke(tool_name, args, self.ctx, control_granted=False)
            transcript.append(
                {"step": i, "tool": tool_name, "ok": result.ok, "data": result.data, "error": result.error}
            )
        return {
            "label": "SIMULATION",
            "steps_executed": len(transcript),
            "transcript": transcript,
            "note": "سناریو بدون تماس با سخت‌افزار اجرا شد؛ مراحل فیزیکی صادقانه رد شدند.",
        }

    def live_state(self, device_id: str) -> dict[str, Any] | None:
        """وضعیت واقعی از درایور متصل — None اگر سخت‌افزار متصل نیست."""
        driver = self.ctx.drivers.get("grbl")
        if driver is None or getattr(driver, "device_id", None) != device_id:
            return None
        result = driver.read_status()
        if not result.ok or result.source != "live":
            return None
        return {"device_id": device_id, "source": "live", "data": result.data, "ts": result.ts}

    def snapshot(self) -> dict[str, Any]:
        """نمای کامل twin برای داشبورد/API با برچسب صریح."""
        with self._lock:
            twins = [s.to_dict() for s in self._states.values()]
        return {
            "label": "SIMULATION",
            "twins": twins,
            "live": self.live_state(getattr(self.ctx.grbl, "device_id", "grbl-01")),
            "safety_mode": self.ctx.safety.mode,
        }
