"""omid.drivers.grbl — درایور کنترلر حرکتی GRBL (شبیه‌ساز + سریال واقعی).

قواعد ایمنی پیاده‌شده در این درایور:
- backend پیش‌فرض ``simulated`` است و همهٔ نتایج برچسب ``simulation`` دارند.
- حرکت فیزیکی فقط وقتی ممکن است که: حالت ایمنی ``control`` باشد، توقف
  اضطراری فعال نباشد، قفل پیکربندی باز باشد و سخت‌افزار سریال **واقعاً**
  متصل باشد. در نبود سخت‌افزار، اجرای زنده صادقانه رد می‌شود — هرگز
  «موفقیت زنده» جعل نمی‌شود.
- G-code خام (به‌ویژه از متن مدل زبانی) هرگز ارسال نمی‌شود؛ فقط
  فرمان‌های فقط‌خواندنیِ whitelist و :class:`MotionCommand`
  اعتبارسنجی‌شده.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from omid.config import MachineLimits
from omid.drivers.base import CommandResult, DeviceDriver
from omid.errors import ValidationError
from omid.safety.validator import MotionCommand, screen_gcode_line, validate_motion

# پاسخ‌های شبیه‌سازی‌شدهٔ فرمان‌های فقط‌خواندنی (برچسب simulation دارند)
_SIM_READONLY_RESPONSES = {
    "?": "<Idle|MPos:0.000,0.000,0.000|Bf:15,128|FS:0,0|WCO:0.000,0.000,0.000>",
    "$$": "$0=10\n$1=25\n$100=250.000\n$110=8000.000\n$120=500.000\n$130=300.000 (simulated)",
    "$i": "Grbl 1.1h ['$' for help] (simulated)",
    "$g": "[G0 G54 G17 G21 G90 G94 M5 M9 T0 F0 S0] (simulated)",
    "$#": "[G54:0.000,0.000,0.000] (simulated)",
    "$n": "$0=\n$1= (simulated)",
    "$c": "Check mode (simulated)",
}


class GRBLDriver(DeviceDriver):
    """درایور GRBL با دو backend: شبیه‌ساز (پیش‌فرض) و سریال واقعی."""

    name = "grbl"
    protocol = "grbl-1.1"

    def __init__(
        self,
        *,
        device_id: str = "grbl-01",
        limits: MachineLimits | None = None,
        backend: str = "simulated",
        serial_port: str | None = None,
        baudrate: int = 115200,
        safety: Any = None,
        audit: Callable[..., None] | None = None,
    ) -> None:
        self.device_id = device_id
        self.limits = limits or MachineLimits()
        self.backend = backend if backend in {"simulated", "serial"} else "simulated"
        self.serial_port = serial_port
        self.baudrate = baudrate
        self._safety = safety  # SafetyManager (duck-typed)
        self._audit = audit or (lambda *a, **k: None)
        self._lock = threading.RLock()
        self._serial: Any = None
        # وضعیت شبیه‌ساز
        self._sim_connected = False
        self._sim_position = [0.0, 0.0, 0.0]
        self._sim_status = "Idle"
        self._sim_alarm: str | None = None

    # ---------- قابلیت‌ها ----------
    def capabilities(self) -> list[str]:
        caps = ["status-read", "readonly-gcode", "motion-structured"]
        if self.backend == "simulated":
            caps.append("simulation")
        else:
            caps.append("live-serial")
        return caps

    def backend_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "protocol": self.protocol,
            "device_id": self.device_id,
            "backend": self.backend,
            "serial_port": self.serial_port,
            "capabilities": self.capabilities(),
        }

    # ---------- اتصال ----------
    def connect(self) -> CommandResult:
        if self.backend == "simulated":
            with self._lock:
                self._sim_connected = True
                self._sim_status = "Idle"
            self._audit("driver.grbl.connected", "اتصال شبیه‌ساز GRBL برقرار شد.", data={"id": self.device_id})
            return CommandResult(ok=True, data={"connected": True}, source="simulation")
        # backend سریال — نیازمند pyserial و سخت‌افزار واقعی
        try:
            import serial  # type: ignore
        except ImportError:
            return CommandResult(
                ok=False,
                error="pyserial نصب نیست؛ اتصال سریال واقعی ممکن نیست (وانمود نمی‌شود).",
                source="live",
            )
        if not self.serial_port:
            return CommandResult(ok=False, error="پورت سریال مشخص نشده است.", source="live")
        try:
            with self._lock:
                self._serial = serial.Serial(self.serial_port, self.baudrate, timeout=2)
            self._audit("driver.grbl.connected", f"اتصال سریال واقعی به {self.serial_port}.", data={"id": self.device_id})
            return CommandResult(ok=True, data={"connected": True, "port": self.serial_port}, source="live")
        except Exception as exc:  # noqa: BLE001 - خطاهای سریال متنوع‌اند
            return CommandResult(ok=False, error=f"اتصال سریال ناموفق: {type(exc).__name__}: {exc}", source="live")

    def disconnect(self) -> CommandResult:
        with self._lock:
            if self._serial is not None:
                try:
                    self._serial.close()
                except Exception:  # noqa: BLE001
                    pass
                self._serial = None
            self._sim_connected = False
        return CommandResult(ok=True, data={"connected": False}, source="simulation" if self.backend == "simulated" else "live")

    # ---------- وضعیت ----------
    def read_status(self) -> CommandResult:
        if self.backend != "simulated" and self._serial is None:
            return CommandResult(ok=False, error="اتصال سریال واقعی برقرار نیست؛ وضعیت زنده قابل خواندن نیست.", source="live")
        if self.backend == "simulated":
            with self._lock:
                data = {
                    "connected": self._sim_connected,
                    "status": self._sim_status,
                    "position": {"x": self._sim_position[0], "y": self._sim_position[1], "z": self._sim_position[2]},
                    "alarm": self._sim_alarm,
                    "backend": "simulated",
                }
            return CommandResult(ok=True, data=data, source="simulation")
        # وضعیت زنده از سخت‌افزار
        raw = self._send_raw("?\n")
        normalized = raw.strip() if raw is not None else ""
        if not normalized.startswith("<") or not normalized.endswith(">"):
            return CommandResult(
                ok=False,
                error="پاسخ وضعیت GRBL خالی، ناقص یا نامعتبر است؛ وضعیت زنده تأیید نشد.",
                data={"backend": "serial"},
                source="live",
            )
        return CommandResult(ok=True, data={"raw": normalized, "backend": "serial"}, source="live")

    def simulated_metrics(self) -> dict[str, Any]:
        """متریک‌های برچسب‌خوردهٔ شبیه‌سازی برای تشخیص عیب (هرگز live وانمود نمی‌شود)."""
        with self._lock:
            return {
                "source": "simulation",
                "temperature_c": 42.0,
                "vibration_mm_s": 1.8,
                "spindle_load_pct": 35.0,
                "comm_timeout_count": 0,
                "position": list(self._sim_position),
                "status": self._sim_status,
                "alarm": self._sim_alarm,
            }

    # ---------- اجرای فرمان ----------
    def execute(self, command: Any) -> CommandResult:
        """اجرای فرمان ساختاریافته یا فقط‌خواندنیِ whitelist‌شده."""
        if isinstance(command, MotionCommand):
            return self._execute_motion(command)
        if isinstance(command, str):
            return self._execute_text(command)
        return CommandResult(ok=False, error=f"نوع فرمان پشتیبانی‌نشده: {type(command).__name__}")

    def _execute_motion(self, cmd: MotionCommand) -> CommandResult:
        # 1) اعتبارسنجی محدوده — همیشه، صرف‌نظر از حالت
        try:
            validate_motion(cmd, self.limits)
        except (ValidationError, Exception) as exc:  # noqa: BLE001
            return CommandResult(ok=False, error=f"فرمان حرکتی نامعتبر: {exc}", source="simulation")

        safety_mode = self._safety.mode if self._safety else "simulate"
        estop = self._safety.estop_active if self._safety else False

        if estop:
            return CommandResult(ok=False, error="توقف اضطراری فعال است؛ حرکت مسدود شد.", source="simulation")

        if safety_mode == "control":
            if self._serial is None:
                # صداقت محض: بدون سخت‌افزار واقعی، اجرای زنده جعل نمی‌شود
                return CommandResult(
                    ok=False,
                    error="حالت control فعال است اما سخت‌افزار سریال متصل نیست؛ اجرای فیزیکی رد شد "
                    "(شبیه‌سازی به‌جای اجرای زنده جا نمی‌زند).",
                    source="live",
                )
            gcode = cmd.to_gcode() + "\n"
            raw = self._send_command(gcode)
            lines = [line.strip() for line in raw.splitlines()] if raw else []
            has_error = any(line.lower().startswith("error:") for line in lines)
            if not lines or lines[-1].lower() != "ok" or has_error:
                response = raw.strip() if raw is not None and raw.strip() else "پاسخ خالی/timeout"
                return CommandResult(
                    ok=False,
                    error=f"کنترلر فرمان حرکتی را با پاسخ ok تأیید نکرد: {response}",
                    data={"gcode": cmd.to_gcode(), "response": response},
                    source="live",
                )
            with self._lock:
                self._sim_position = [
                    cmd.x if cmd.x is not None else self._sim_position[0],
                    cmd.y if cmd.y is not None else self._sim_position[1],
                    cmd.z if cmd.z is not None else self._sim_position[2],
                ]
            self._audit("driver.grbl.motion_live", f"حرکت فیزیکی اجرا شد: {cmd.to_gcode()}", data=cmd.to_dict())
            return CommandResult(ok=True, data={"gcode": cmd.to_gcode(), "response": raw.strip()}, source="live")

        # حالت simulate/observe → فقط شبیه‌ساز
        if safety_mode != "simulate":
            return CommandResult(
                ok=False, error=f"حرکت در حالت {safety_mode} مجاز نیست.", source="simulation"
            )
        with self._lock:
            self._sim_status = "Run"
            self._sim_position = [
                cmd.x if cmd.x is not None else self._sim_position[0],
                cmd.y if cmd.y is not None else self._sim_position[1],
                cmd.z if cmd.z is not None else self._sim_position[2],
            ]
            self._sim_status = "Idle"
        self._audit("driver.grbl.motion_sim", f"حرکت شبیه‌سازی شد: {cmd.to_gcode()}", data=cmd.to_dict())
        return CommandResult(
            ok=True,
            data={"gcode_preview": cmd.to_gcode(), "position": dict(zip(("x", "y", "z"), self._sim_position, strict=True))},
            source="simulation",
        )

    def _execute_text(self, text: str) -> CommandResult:
        allowed, normalized, reason = screen_gcode_line(text)
        if not allowed:
            return CommandResult(ok=False, error=reason, source="simulation")
        if self.backend != "simulated" and self._serial is None:
            return CommandResult(ok=False, error="backend سریال انتخاب شده اما اتصال واقعی برقرار نیست؛ فرمان ارسال نشد.", source="live")
        if self._serial is not None:
            # GRBL status reports are a single realtime frame; system queries may emit
            # multiple lines ending in "ok" and must be drained to their terminator.
            sender = self._send_raw if normalized == "?" else self._send_command
            raw = sender(normalized + ("\n" if normalized != "?" else ""))
            lines = [line.strip() for line in raw.splitlines()] if raw else []
            has_error = any(line.lower().startswith("error:") for line in lines)
            invalid_status_frame = normalized == "?" and not (
                len(lines) == 1 and lines[0].startswith("<") and lines[0].endswith(">")
            )
            if not lines or has_error or invalid_status_frame or (normalized != "?" and lines[-1].lower() != "ok"):
                response = raw.strip() if raw is not None and raw.strip() else "پاسخ خالی/timeout"
                return CommandResult(
                    ok=False,
                    error=f"فرمان فقط‌خواندنی از کنترلر تأیید نشد: {response}",
                    data={"sent": normalized, "response": response},
                    source="live",
                )
            return CommandResult(ok=True, data={"sent": normalized, "response": raw.strip()}, source="live")
        response = _SIM_READONLY_RESPONSES.get(normalized, "ok (simulated)")
        if normalized == "?" and self.backend == "simulated":
            with self._lock:
                x, y, z = self._sim_position
                status = self._sim_status
            response = f"<{status}|MPos:{x:.3f},{y:.3f},{z:.3f}|Bf:15,128|FS:0,0> (simulated)"
        return CommandResult(ok=True, data={"sent": normalized, "response": response}, source="simulation")

    # ---------- توقف اضطراری (مسیر مستقل) ----------
    def estop(self, reason: str = "") -> CommandResult:
        """Request a driver-level halt; never claim a physical stop without successful I/O.

        This software request is not a substitute for a certified hardware E-stop circuit.
        """
        source = "live" if self.backend != "simulated" else "simulation"
        # Successful writes prove only that bytes were accepted by the serial API,
        # not that the machine physically stopped. Hardware confirmation stays false.
        physical_stop_confirmed = False
        stop_commands_sent = False
        errors: list[str] = []
        if self.backend == "simulated":
            with self._lock:
                self._sim_status = "Alarm"
                self._sim_alarm = reason or "E-STOP"
        elif self._serial is None:
            errors.append("اتصال سریال واقعی برقرار نیست؛ توقف فیزیکی تأیید نشد.")
        else:
            # Realtime E-Stop bytes do not require a line-based "ok" reply.
            # Count only complete serial writes; this is still not physical-stop confirmation.
            hold_sent = self._write_raw("!")
            reset_sent = self._write_raw("\x18")
            if not hold_sent:
                errors.append("ارسال feed-hold ناموفق بود.")
            if not reset_sent:
                errors.append("ارسال soft-reset ناموفق بود.")
            stop_commands_sent = hold_sent and reset_sent
        self._audit(
            "driver.grbl.estop",
            f"درخواست توقف اضطراری درایور GRBL ({reason or 'بدون دلیل'}) — منبع: {source}.",
            data={"reason": reason, "device": self.device_id, "physical_stop_confirmed": physical_stop_confirmed, "stop_commands_sent": stop_commands_sent, "errors": errors},
            severity="critical",
        )
        if source == "live" and not stop_commands_sent:
            return CommandResult(ok=False, error=" ".join(errors) or "ارسال فرمان‌های توقف تأیید نشد.", data={"physical_stop_confirmed": False, "stop_commands_sent": False}, source="live")
        return CommandResult(ok=True, data={"status": "Alarm" if source == "simulation" else "stop_requested", "alarm": reason or "E-STOP", "physical_stop_confirmed": False, "stop_commands_sent": stop_commands_sent}, source=source)

    def clear_alarm(self) -> CommandResult:
        """Clear only simulated alarms; never claim a live controller was reset."""
        if self.backend != "simulated":
            return CommandResult(
                ok=False,
                error="پاک‌کردن آلارم زنده هنوز پیاده‌سازی نشده است؛ وضعیت دستگاه تغییر نکرد.",
                data={"status": "unknown", "backend": self.backend},
                source="live",
            )
        with self._lock:
            if self._sim_alarm:
                self._sim_alarm = None
                self._sim_status = "Idle"
        return CommandResult(ok=True, data={"status": "Idle"}, source="simulation")

    # ---------- داخلی ----------
    def _write_raw(self, payload: str) -> bool:
        """Write a real-time serial payload without waiting for a line response."""
        with self._lock:
            ser = self._serial
        if ser is None:
            return False
        try:
            encoded = payload.encode("ascii")
            written = ser.write(encoded)
            ser.flush()
            return written == len(encoded)
        except Exception:  # noqa: BLE001 - serial exceptions vary by driver
            return False

    def _send_raw(self, payload: str) -> str | None:
        """Send a realtime status query and read its single response frame."""
        with self._lock:
            ser = self._serial
        if ser is None:
            return None
        try:
            ser.reset_input_buffer()
            encoded = payload.encode("ascii")
            written = ser.write(encoded)
            if written != len(encoded):
                return None
            ser.flush()
            line = ser.readline()
            if not line:
                return None
            response = line.decode("ascii", errors="replace").strip()
            return response if response else None
        except Exception:  # noqa: BLE001 - serial exceptions vary by driver
            return None

    def _send_command(self, payload: str) -> str | None:
        """Send a GRBL command and read all response lines through ok/error terminator."""
        with self._lock:
            ser = self._serial
        if ser is None:
            return None
        original_timeout = getattr(ser, "timeout", 2.0)
        manage_timeout = original_timeout is None or isinstance(original_timeout, (int, float))
        timeout_s = float(original_timeout) if isinstance(original_timeout, (int, float)) else 2.0
        deadline = time.monotonic() + max(2.0, min(10.0, timeout_s * 4.0))
        response_lines: list[str] = []
        try:
            ser.reset_input_buffer()
            encoded = payload.encode("ascii")
            written = ser.write(encoded)
            if written != len(encoded):
                return None
            ser.flush()
            for _ in range(128):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                if manage_timeout:
                    ser.timeout = remaining
                raw_line = ser.readline()
                if not raw_line:
                    return None
                line = raw_line.decode("ascii", errors="replace").strip()
                if not line:
                    continue
                response_lines.append(line)
                if line.lower() == "ok" or line.lower().startswith("error:"):
                    return "\n".join(response_lines)
            return None
        except Exception:  # noqa: BLE001 - serial exceptions vary by driver
            return None
        finally:
            if manage_timeout:
                try:
                    ser.timeout = original_timeout
                except Exception:  # noqa: BLE001
                    pass
