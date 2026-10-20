"""omid.twin — شبیه‌ساز و Digital Twin.

اصل تفکیک: وضعیت **تخمینی (شبیه‌سازی)** و وضعیت **واقعی (live)** همیشه
جدا و برچسب‌دار نگه داشته می‌شوند. در حالت شبیه‌سازی هیچ فرمان فیزیکی
صادر نمی‌شود و خروجی‌ها هرگز به‌عنوان اندازه‌گیری زنده نمایش داده
نمی‌شوند.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
"""
from __future__ import annotations

from omid.twin.simulator import DigitalTwin, TwinState

__all__ = ["DigitalTwin", "TwinState"]
