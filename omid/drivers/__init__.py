"""omid.drivers — لایهٔ کنترل و درایورهای تجهیزات.

رابط مشترک و قابل‌توسعه برای همهٔ درایورها: اتصال، خواندن وضعیت،
اعلام قابلیت‌ها، اجرای فرمان **ساختاریافتهٔ** مجاز، توقف امن و گزارش
خطا. خروجی هر درایور همیشه برچسب منبع دارد: ``simulation`` یا ``live``.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
"""
from __future__ import annotations

from omid.drivers.base import CommandResult, DeviceDriver
from omid.drivers.grbl import GRBLDriver

__all__ = ["CommandResult", "DeviceDriver", "GRBLDriver"]
