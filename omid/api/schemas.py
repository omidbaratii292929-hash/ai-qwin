"""omid.api.schemas — مدل‌های درخواست/پاسخ API.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000, description="متن درخواست کاربر (فارسی یا انگلیسی)")
    requested_by: str = Field(default="api", max_length=64)


class EstopRequest(BaseModel):
    reason: str = Field(default="درخواست اپراتور از API", max_length=200)


class EstopReleaseRequest(BaseModel):
    confirm: str = Field(default="", max_length=64, description="عبارت تأیید صریح")


class ModeRequest(BaseModel):
    mode: str = Field(pattern="^(observe|simulate|control)$")
    confirm: str = Field(default="", max_length=64)


class DiscoverRequest(BaseModel):
    scope: str = Field(default="serial", pattern="^(serial|network)$")


class TwinPreviewRequest(BaseModel):
    x: float | None = None
    y: float | None = None
    z: float | None = None
    feed: float | None = None
    device: str = Field(default="grbl-01", max_length=64)


class IngestRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500, description="مسیر فایل روی ماشین سرور (فقط با اعتبار کنترل)")


class IngestDirRequest(BaseModel):
    dir: str = Field(min_length=1, max_length=500)
    max_files: int = Field(default=200, ge=1, le=1000)


class PreferenceRequest(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    value: Any = None
