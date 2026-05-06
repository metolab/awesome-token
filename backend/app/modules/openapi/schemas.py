from __future__ import annotations

from pydantic import BaseModel, Field


class OpenApiKeyCreate(BaseModel):
    label: str = Field(default="", max_length=200)


class OpenApiKeyListItem(BaseModel):
    id: str
    label: str
    key_prefix: str
    key_plain: str = ""
    created_at: str


class OpenApiKeyCreated(BaseModel):
    id: str
    label: str
    key_prefix: str
    secret: str
    created_at: str


class BailianTokenResponse(BaseModel):
    token: str
    account_id: str
    username: str
