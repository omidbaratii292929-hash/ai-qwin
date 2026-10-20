"""omid.api.routers.agent — درخواست‌های عامل و مدیریت وظایف.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from omid.api.auth import control_granted, require_read
from omid.api.schemas import AgentRequest

router = APIRouter(prefix="/api", tags=["agent"])


@router.post("/agent/request")
def agent_request(body: AgentRequest, request: Request, auth: dict = Depends(require_read)) -> dict[str, Any]:
    """ارسال درخواست زبان طبیعی به عامل؛ نتیجه = وظیفه با شواهد اجرا."""
    ctx = request.app.state.ctx
    granted = control_granted(request)
    task = ctx.agent.handle_request(
        body.text,
        requested_by=body.requested_by or auth.get("principal", "api"),
        control_granted=granted,
    )
    return task.to_dict()


@router.get("/tasks")
def list_tasks(request: Request, limit: int = 50, _auth: dict = Depends(require_read)) -> dict[str, Any]:
    ctx = request.app.state.ctx
    return {"tasks": ctx.tasks.list(limit=max(1, min(limit, 200)))}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request, _auth: dict = Depends(require_read)) -> dict[str, Any]:
    ctx = request.app.state.ctx
    task = ctx.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="وظیفه یافت نشد.")
    return task.to_dict()


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str, request: Request, _auth: dict = Depends(require_read)) -> dict[str, Any]:
    ctx = request.app.state.ctx
    ok = ctx.tasks.request_cancel(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="وظیفه یافت نشد یا قبلاً پایان یافته است.")
    ctx.audit_event("api.task_cancel", f"لغو وظیفه {task_id} درخواست شد.", data={"task": task_id})
    return {"ok": True, "task_id": task_id}


@router.post("/tasks/{task_id}/confirm")
def confirm_task(task_id: str, request: Request) -> dict[str, Any]:
    """تأیید صریح انسانی برای ادامهٔ عملیات فیزیکی — نیازمند اعتبار کنترل."""
    from omid.api.auth import require_control

    principal = require_control(request)  # بررسی مستقیم (بدون Depends برای پیام شفاف‌تر)
    ctx = request.app.state.ctx
    task = ctx.agent.confirm_task(task_id, control_granted=True)
    if task is None:
        raise HTTPException(status_code=404, detail="وظیفه یافت نشد.")
    ctx.audit_event(
        "api.task_confirmed",
        f"وظیفه {task_id} با تأیید صریح ادامه یافت.",
        data={"task": task_id, "principal": principal.get("principal")},
    )
    return task.to_dict()
