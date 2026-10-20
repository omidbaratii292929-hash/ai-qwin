"""omid.errors — سلسله‌مراتب خطاهای مرکزی پروژه.

همه خطاهای اختصاصی OMID از :class:`OMIDError` مشتق می‌شوند تا مدیریت خطا
یکنواخت باشد و لایه‌های بالادستی (API، عامل، CLI) بتوانند صادقانه و بدون
نشت جزئیات حساس گزارش دهند.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations


class OMIDError(RuntimeError):
    """خطای پایهٔ همهٔ خطاهای اختصاصی پروژه OMID."""


class BrandingError(OMIDError):
    """اطلاعات هویت/برند نامعتبر یا در دسترس نیست."""


class ConfigError(OMIDError):
    """پیکربندی نامعتبر (مقادیر محیطی یا فایل تنظیمات)."""


class SafetyError(OMIDError):
    """عملیات با قواعد ایمنی یا حالت عملیاتی فعلی سازگار نیست."""


class PermissionDenied(SafetyError):
    """مجوز لازم برای ابزار/ریسک درخواست‌شده وجود ندارد."""


class ToolError(OMIDError):
    """خطای ثبت یا اجرای ابزار در رجیستری ابزارها."""


class DriverError(OMIDError):
    """خطای درایور تجهیزات (اتصال، پروتکل، اجرای فرمان)."""


class ValidationError(OMIDError):
    """اعتبارسنجی ورودی یا فرمان ناموفق بود."""
