"""omid.drivers.base — رابط مشترک همهٔ درایورهای تجهیزات.

هر درایور باید قابلیت‌های **واقعی** خود را اعلام کند و هرگز اجرای زنده را
وانمود نکند: فیلد ``source`` در نتایج همیشه ``simulation`` یا ``live`` است.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from omid.events import utc_now_iso


@dataclass
class CommandResult:
    """نتیجهٔ اجرای فرمان با برچسب صادقانهٔ منبع."""

    ok: bool
    data: Any = None
    error: str | None = None
    source: str = "simulation"  # simulation | live
    ts: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "data": self.data, "error": self.error, "source": self.source, "ts": self.ts}


class DeviceDriver(ABC):
    """رابط پایهٔ درایور: اتصال، وضعیت، قابلیت‌ها، اجرای مجاز، توقف امن."""

    name: str = "base"
    protocol: str = "unknown"

    @abstractmethod
    def capabilities(self) -> list[str]:
        """قابلیت‌های واقعی پشتیبانی‌شده توسط این درایور."""

    @abstractmethod
    def connect(self) -> CommandResult:
        """اتصال به تجهیزات (یا شبیه‌ساز)."""

    @abstractmethod
    def disconnect(self) -> CommandResult:
        """قطع اتصال به‌شکل امن."""

    @abstractmethod
    def read_status(self) -> CommandResult:
        """خواندن وضعیت فعلی — کم‌خطرترین عملیات ممکن."""

    @abstractmethod
    def execute(self, command: Any) -> CommandResult:
        """اجرای فرمان ساختاریافتهٔ اعتبارسنجی‌شده (نه متن خام)."""

    @abstractmethod
    def estop(self, reason: str = "") -> CommandResult:
        """توقف امن فوری — مسیر مستقل از مدل زبانی و برنامه‌ریز."""

    def backend_info(self) -> dict[str, Any]:
        return {"name": self.name, "protocol": self.protocol}
