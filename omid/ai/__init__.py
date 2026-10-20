"""omid.ai — لایهٔ هوش مصنوعی محلی (اختیاری).

سامانه **بدون مدل زبانی هم کار می‌کند** (حالت افتقاده‌ی مبتنی بر قواعد).
اتصال به Ollama یا سرویس سازگار، با بررسی سلامت، timeout و ثبت اطلاعات
تشخیصی انجام می‌شود. تنظیمات مدل از کد جداست (متغیرهای محیطی).

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
"""
from __future__ import annotations

from omid.ai.ollama import HealthStatus, OllamaProvider, ProviderResult

__all__ = ["HealthStatus", "OllamaProvider", "ProviderResult"]
