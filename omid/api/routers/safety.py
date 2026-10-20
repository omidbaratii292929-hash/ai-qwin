"""omid.api.routers.safety — وضعیت ایمنی، توقف اضطراری و تغییر حالت.

توقف اضطراری با دسترسی خواندن هم قابل فعال‌سازی است (fail-safe) اما
آزادسازی و ارتقای حالت فقط با اعتبار کنترل ممکن است.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from omid.api.auth import require_control, require_read
from omid.api.schemas import EstopReleaseRequest, EstopRequest, ModeRequest
from omid.errors import SafetyError

router = APIRouter(prefix="/api/safety", tags=["safety"])


@router.get("")
def safety_state(request: Request, _auth: dict = Depends(require_read)) -> dict[str, Any]:
    ctx = request.app.state.ctx
    return ctx.safety.snapshot()


@router.post("/estop")
def trigger_estop(body: EstopRequest, request: Request, _auth: dict = Depends(require_read)) -> dict[str, Any]:
    """توقف اضطراری — همیشه مجاز (در جهت ایمنی). مستقل از مدل زبانی."""
    ctx = request.app.state.ctx
    snapshot = ctx.safety.trigger_estop(body.reason, source="api")
    driver_result = ctx.grbl.estop(body.reason)
    return {"ok": True, "safety": snapshot, "driver": driver_result.to_dict()}


@router.post("/estop/release")
def release_estop(
    body: EstopReleaseRequest, request: Request, _auth: dict = Depends(require_control)
) -> dict[str, Any]:
    ctx = request.app.state.ctx
    try:
        snapshot = ctx.safety.release_estop(body.confirm, source="api")
    except SafetyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    ctx.grbl.clear_alarm()
    return {"ok": True, "safety": snapshot}


@router.post("/mode")
def set_mode(body: ModeRequest, request: Request, _auth: dict = Depends(require_control)) -> dict[str, Any]:
    ctx = request.app.state.ctx
    try:
        new_mode = ctx.safety.request_mode(body.mode, body.confirm, source="api")
    except SafetyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "mode": new_mode, "safety": ctx.safety.snapshot()}
