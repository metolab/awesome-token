"""Shared persistence models for JSON stores."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


def _normalize_channel_models(value: Any) -> str:
    if isinstance(value, list):
        raw_values = [str(item) for item in value]
    elif isinstance(value, str):
        raw_values = value.split(",")
    elif value is None:
        raw_values = []
    else:
        raw_values = [str(value)]

    deduped: dict[str, str] = {}
    for raw in raw_values:
        model = raw.strip()
        if not model:
            continue
        key = model.casefold()
        if key not in deduped:
            deduped[key] = model

    return ",".join(sorted(deduped.values(), key=lambda item: (item.casefold(), item)))


def _normalize_newapi_template(template: Any) -> Any:
    if not isinstance(template, dict):
        return template
    cleaned = dict(template)
    channel = cleaned.get("channel")
    if isinstance(channel, dict) and "models" in channel:
        next_channel = dict(channel)
        next_channel["models"] = _normalize_channel_models(next_channel.get("models"))
        cleaned["channel"] = next_channel
    return cleaned


class BalanceSnapshot(BaseModel):
    available_amount: str | None = None
    available_cash_amount: str | None = None
    currency: str | None = None
    credit_amount: str | None = None
    mybank_credit_amount: str | None = None


class CashCouponSnapshot(BaseModel):
    coupon_id: str | None = None
    status: str | None = None
    balance: str | None = None
    nominal_value: str | None = None
    granted_time: str | None = None
    expiry_time: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class AliyunAccountRecord(BaseModel):
    id: str
    username: str
    access_key_id: str
    access_key_secret: str
    bailian_api_key: str
    remark: str = ""

    balance: BalanceSnapshot | None = None
    coupons: list[CashCouponSnapshot] = Field(default_factory=list)
    last_transactions: list[dict[str, Any]] = Field(default_factory=list)

    last_synced_at: str | None = None
    last_sync_error: str | None = None
    created_at: str
    updated_at: str


class NewApiConfigRecord(BaseModel):
    """new-api admin connection + one channel template."""

    id: str = "singleton"
    base_url: str = ""
    admin_token: str = ""
    admin_user_id: str = ""
    # Single template: { "name_template": "…{username}…", "channel": { … new-api channel data … } }
    template: dict[str, Any] = Field(default_factory=dict)
    # Aliyun cash-coupon balance must be strictly above this to sync a channel (same currency unit as BSS balance).
    min_coupon_balance_for_newapi: float = Field(default=10.0, ge=0)
    created_at: str | None = None
    updated_at: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_channel_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        legacy = frozenset(
            {
                "test_model",
                "disable_keywords",
                "channel_type",
                "channel_base_url",
                "channel_models",
                "channel_group",
                "auto_ban",
                "channel_name_template",
                "channel_template",
                "channel_auto_test_interval_minutes",
            }
        )
        if "template" in data:
            cleaned = {k: v for k, v in data.items() if k not in legacy}
            cleaned["template"] = _normalize_newapi_template(cleaned.get("template"))
            return cleaned

        name = data.get("channel_name_template", "Aliyun {username}")
        raw_ch = data.get("channel_template")
        ch: dict[str, Any] = raw_ch if isinstance(raw_ch, dict) else {}
        if not ch:
            ch = {
                "type": data.get("channel_type", 17),
                "base_url": data.get("channel_base_url")
                or "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "models": data.get("channel_models", "qwen-turbo"),
                "group": data.get("channel_group", "default"),
                "status": 1,
                "auto_ban": data.get("auto_ban", 1),
                "test_model": data.get("test_model", "qwen-turbo"),
            }
        cleaned = {k: v for k, v in data.items() if k not in legacy}
        cleaned["template"] = _normalize_newapi_template({"name_template": name, "channel": ch})
        return cleaned


class OpenApiKeyRecord(BaseModel):
    """Server-side key for public Bailian token resolution (hashed at rest)."""

    id: str
    label: str = ""
    key_hash: str
    key_prefix: str
    created_at: str
    updated_at: str


class ScheduledJobRecord(BaseModel):
    """Periodic task registration (id is APScheduler job id)."""

    id: str
    name: str
    interval_minutes: int = 15
    enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None
