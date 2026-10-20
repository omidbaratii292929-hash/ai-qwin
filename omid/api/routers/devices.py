"""omid.api.routers.devices — تجهیزات، درایورها و Digital Twin.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from omid.api.auth import require_read
from omid.api.schemas import DiscoverRequest, TwinPreviewRequest
from omid.safety.validator import MotionCommand

router = APIRouter(prefix="/api", tags=["devices"])


@router.get("/devices")
def list_devices(request: Request, _auth: dict = Depends(require_read)) -> dict[str, Any]:
    ctx = request.app.state.ctx
    return {"devices": ctx.devices.list(), "count": ctx.devices.count()}


@router.get("/devices/{device_id}")
def get_device(device_id: str, request: Request, _auth: dict = Depends(require_read)) -> dict[str, Any]:
    ctx = request.app.state.ctx
    device = ctx.devices.get(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="دستگاه یافت نشد.")
    return device.to_dict()


@router.post("/devices/discover")
def discover(body: DiscoverRequest, request: Request, _auth: dict = Depends(require_read)) -> dict[str, Any]:
    """کشف کنترل‌شده — شبکه فقط روی allowlist پیکربندی‌شده."""
    ctx = request.app.state.ctx
    if body.scope == "network":
        return ctx.discover_network()
    return ctx.discover_serial()


@router.get("/drivers")
def drivers(request: Request, _auth: dict = Depends(require_read)) -> dict[str, Any]:
    ctx = request.app.state.ctx
    return {"drivers": [d.backend_info() for d in ctx.drivers.values()]}


@router.post("/drivers/{name}/status")
def driver_status(name: str, request: Request, _auth: dict = Depends(require_read)) -> dict[str, Any]:
    ctx = request.app.state.ctx
    driver = ctx.drivers.get(name)
    if driver is None:
        raise HTTPException(status_code=404, detail=f"درایور «{name}» وجود ندارد. موجود: {sorted(ctx.drivers)}")
    result = driver.read_status()
    return result.to_dict()


@router.get("/twin")
def twin_snapshot(request: Request, _auth: dict = Depends(require_read)) -> dict[str, Any]:
    ctx = request.app.state.ctx
    return ctx.twin.snapshot()


@router.post("/twin/preview")
def twin_preview(body: TwinPreviewRequest, request: Request, _auth: dict = Depends(require_read)) -> dict[str, Any]:
    """پیش‌نمایش حرکت روی twin — همیشه simulation، با اعتبارسنجی محدوده."""
    ctx = request.app.state.ctx
    cmd = MotionCommand(x=body.x, y=body.y, z=body.z, feed=body.feed)
    return ctx.twin.preview_motion(body.device, cmd)
