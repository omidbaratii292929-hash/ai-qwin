"""omid.branding — بارگذاری و اعتبارسنجی منبع یکتای هویت برند.

این ماژول تنها نقطهٔ دسترسی رسمی به اطلاعات هویت پروژه است:

    شرکت: هوشمندسازی صنعت امید
    شعار رسمی: ما می‌سازیم تا شما راحت زندگی کنید
    طراح و سازندهٔ اصلی: مهندس امید براتی
    با همکاری: دکتر کیمیا زهرا براتی و مهندس محسن بابایی

مقادیر از فایل ``branding.json`` در ریشهٔ مخزن خوانده می‌شوند (قابل جایگزینی
با متغیر محیطی ``OMID_BRANDING_FILE``). هیچ بخشی از پروژه نباید مقادیر هویت
را دستی hard-code کند؛ README، داشبورد، API و گزارش‌ها همه از این منبع
تغذیه می‌شوند و آزمون برند (``tests/test_branding.py``) تناقض را شناسایی
می‌کند.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from omid.errors import BrandingError

REQUIRED_FIELDS: tuple[str, ...] = (
    "project_name",
    "company_name",
    "tagline",
    "lead_designer_and_creator",
    "collaborators",
)

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "branding.json"

_cache: dict[str, Any] | None = None
_lock = threading.Lock()


def branding_path() -> Path:
    """مسیر فایل برند فعلی (پیش‌فرض: branding.json در ریشهٔ مخزن)."""
    return Path(os.environ.get("OMID_BRANDING_FILE") or _DEFAULT_PATH)


def validate(data: Any) -> None:
    """اعتبارسنجی ساختار و مقادیر هویت؛ در صورت نقص BrandingError می‌دهد."""
    if not isinstance(data, dict):
        raise BrandingError("برند باید یک شیء JSON معتبر باشد.")
    for field in REQUIRED_FIELDS:
        value = data.get(field)
        if field == "collaborators":
            if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
                raise BrandingError("فیلد collaborators باید فهرست غیرخالی از رشته‌ها باشد.")
        elif not isinstance(value, str) or not value.strip():
            raise BrandingError(f"فیلد الزامی هویت خالی یا نامعتبر است: {field}")


def load_branding(*, refresh: bool = False) -> dict[str, Any]:
    """بارگذاری (با کش) اطلاعات برند از منبع یکتا."""
    global _cache
    with _lock:
        if _cache is not None and not refresh:
            return dict(_cache)
        path = branding_path()
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise BrandingError(f"خواندن فایل برند ناموفق بود ({path}): {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BrandingError(f"فایل برند JSON معتبر نیست ({path}): {exc}") from exc
        validate(data)
        _cache = data
        return dict(data)


def get(field: str, default: Any = None) -> Any:
    """خواندن یک فیلد از منبع برند."""
    return load_branding().get(field, default)


def report_header() -> str:
    """سربرگ متنی استاندارد برای گزارش‌های فنی و مستندات تولیدشده."""
    b = load_branding()
    collaborators = " و ".join(b["collaborators"])
    return (
        f"{b['project_name']}\n"
        f"{b['company_name']} — {b['tagline']}\n"
        f"طراح و سازندهٔ اصلی: {b['lead_designer_and_creator']} | با همکاری: {collaborators}"
    )


def footer_text() -> str:
    """پابرگ استاندارد رابط و گزارش‌ها."""
    b = load_branding()
    return f"© {b['company_name']} — {b['tagline']} — {b['project_name']}"


def about_dict() -> dict[str, Any]:
    """اطلاعات هویت به‌همراه نسخه، برای صفحهٔ درباره و endpoint مربوطه."""
    from omid import __version__

    b = load_branding()
    return {
        **b,
        "version": __version__,
        "footer": footer_text(),
    }
