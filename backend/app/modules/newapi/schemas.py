from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NewApiConfigIn(BaseModel):
    base_url: str = ""
    admin_token: str = ""
    admin_user_id: str = ""
    template: list[dict[str, Any]] = Field(default_factory=list)
    min_coupon_balance_for_newapi: float = Field(default=10.0, ge=0)
    max_channels_for_newapi_sync: int = Field(default=5, ge=1)


class NewApiConfigOut(NewApiConfigIn):
    id: str = "singleton"


class ChannelRow(BaseModel):
    id: int
    name: str | None = None
    type: int | None = None
    status: int | None = None
    priority: int | None = None
    models: str | None = None
    group: str | None = None
    aliyun_account_id: str | None = None
    template_index: int | None = None


class ChannelDetailResponse(BaseModel):
    """Full JSON returned by new-api `GET /api/channel/{id}` (passthrough)."""

    channel_id: int
    body: dict[str, Any]
