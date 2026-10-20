"""omid.api.routers.status — سلامت، درباره، وضعیت و رویدادها.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from omid import __version__, branding
from omid.api.auth import dev_mode_notice, require_read

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/health")
def health() -> dict[str, Any]:
    """Liveness ساده و باز (بدون اطلاعات حساس)."""
    return {"status": "ok", "service": branding.get("project_name"), "version": __version__}


@router.get("/about")
def about(request: Request) -> dict[str, Any]:
    """هویت رسمی پروژه و شرکت — منبع: branding.json."""
    payload = branding.about_dict()
    payload["safety_mode"] = request.app.state.ctx.safety.mode
    notice = dev_mode_notice(request)
    if notice:
        payload["notice"] = notice
    return payload


@router.get("/status")
def status(request: Request, _auth: dict = Depends(require_read)) -> dict[str, Any]:
    ctx = request.app.state.ctx
    payload = ctx.status()
    notice = dev_mode_notice(request)
    if notice:
        payload["notice"] = notice
    return payload


@router.get("/events")
def events(
    request: Request,
    limit: int = 100,
    severity: str | None = None,
    type_prefix: str | None = None,
    _auth: dict = Depends(require_read),
) -> dict[str, Any]:
    """رویدادهای اخیر (redact‌شده) از گذرگاه رویداد."""
    ctx = request.app.state.ctx
    limit = max(1, min(limit, 500))
    return {"events": ctx.bus.history(limit, severity=severity, type_prefix=type_prefix)}
