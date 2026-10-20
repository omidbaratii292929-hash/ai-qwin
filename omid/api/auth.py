"""omid.api.auth — احراز هویت و تفکیک دسترسی خواندن از دسترسی کنترل.

مدل دسترسی:
- ``read``: با توکن ``OMID_API_TOKEN`` (هدر ``Authorization: Bearer ...``).
  اگر توکن پیکربندی نشده باشد، API در «حالت توسعه» فقط خواندن/شبیه‌سازی
  را روی شبکهٔ محلی باز می‌گذارد و این را صریحاً در پاسخ‌ها اعلام می‌کند.
- ``control``: با توکن جداگانهٔ ``OMID_CONTROL_TOKEN`` (هدر
  ``X-OMID-Control-Token``). اگر پیکربندی نشده باشد، همهٔ endpointهای
  کنترلی **رد** می‌شوند (پیش‌فرض امن: فقدان اعتبار = فقدان دسترسی).

مقایسهٔ توکن‌ها زمان-ثابت (compare_digest) است و توکن‌ها هرگز در پاسخ،
لاگ یا خطاها بازنویسی نمی‌شوند.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import hmac
from typing import Any

from fastapi import HTTPException, Request

BEARER_PREFIX = "bearer "


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith(BEARER_PREFIX):
        return header[len(BEARER_PREFIX) :].strip()
    return None


def _config(request: Request) -> Any:
    return request.app.state.ctx.config


def require_read(request: Request) -> dict[str, Any]:
    """وابستگی FastAPI برای دسترسی خواندن."""
    config = _config(request)
    if config.api_token:
        token = _bearer_token(request)
        if not token or not hmac.compare_digest(token, config.api_token):
            raise HTTPException(status_code=401, detail="توکن خواندن نامعتبر یا ارسال نشده است (Authorization: Bearer).")
        return {"principal": "read-token", "auth_mode": "token"}
    # حالت توسعه بدون توکن — صریح و صادقانه برچسب می‌خورد
    return {"principal": "anonymous-dev", "auth_mode": "dev-no-token"}


def require_control(request: Request) -> dict[str, Any]:
    """وابستگی FastAPI برای عملیات کنترلی (توکن جداگانهٔ کنترل)."""
    config = _config(request)
    if not config.control_token:
        raise HTTPException(
            status_code=403,
            detail="اعتبار کنترل پیکربندی نشده است (OMID_CONTROL_TOKEN) — عملیات کنترلی غیرفعال است.",
        )
    header_token = request.headers.get("x-omid-control-token", "")
    if not header_token or not hmac.compare_digest(header_token, config.control_token):
        raise HTTPException(status_code=403, detail="توکن کنترل نامعتبر یا ارسال نشده است (X-OMID-Control-Token).")
    return {"principal": "control-token", "auth_mode": "token"}


def control_granted(request: Request) -> bool:
    """آیا اعتبار کنترل معتبر ارائه شده؟ (بدون exception — برای عامل)."""
    config = _config(request)
    if not config.control_token:
        return False
    header_token = request.headers.get("x-omid-control-token", "")
    return bool(header_token) and hmac.compare_digest(header_token, config.control_token)


def dev_mode_notice(request: Request) -> str | None:
    """پیام صادقانهٔ حالت توسعه (بدون توکن) برای درج در پاسخ‌ها."""
    if _config(request).api_token:
        return None
    return "API بدون توکن خواندن اجرا می‌شود (حالت توسعه/شبکهٔ محلی). برای استقرار، OMID_API_TOKEN را تنظیم کنید."
