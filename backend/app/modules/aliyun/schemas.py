from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.db.models import BalanceSnapshot, CashCouponSnapshot


class AliyunAccountCreate(BaseModel):
    username: str
    access_key_id: str
    access_key_secret: str
    bailian_api_key: str
    remark: str = ""


class AliyunAccountUpdate(BaseModel):
    username: str | None = None
    access_key_id: str | None = None
    access_key_secret: str | None = None
    bailian_api_key: str | None = None
    remark: str | None = None


class AliyunAccountPublic(BaseModel):
    id: str
    username: str
    remark: str
    balance: BalanceSnapshot | None = None
    coupons: list[CashCouponSnapshot] = Field(default_factory=list)
    last_synced_at: str | None = None
    last_sync_error: str | None = None
    newapi_channel_id: int | None = None
    created_at: str
    updated_at: str


class AliyunAccountDetail(AliyunAccountPublic):
    access_key_id: str
    last_transactions: list[dict[str, Any]] = Field(default_factory=list)


class BillLineRow(BaseModel):
    """BSS QueryBill line item (normalized keys)."""

    product_name: str | None = None
    product_code: str | None = None
    product_type: str | None = None
    product_detail: str | None = None
    subscription_type: str | None = None
    item: str | None = None
    pretax_gross_amount: float | None = None
    pretax_amount: float | None = None
    after_tax_amount: float | None = None
    currency: str | None = None
    deducted_by_cash_coupons: float | None = None
    deducted_by_coupons: float | None = None
    cash_amount: float | None = None
    payment_time: str | None = None
    usage_start_time: str | None = None
    usage_end_time: str | None = None
    status: str | None = None
    record_id: str | None = None
    tax: float | None = None
    pip_code: str | None = None
    commodity_code: str | None = None


class QueryBillLiveResponse(BaseModel):
    """Live BSS QueryBill (not stored locally)."""

    account_id: str
    username: str
    billing_cycle: str
    page_num: int | None = None
    page_size: int | None = None
    total_count: int | None = None
    bss_account_id: str | None = None
    bss_account_name: str | None = None
    items: list[BillLineRow]
    bss_success: bool | None = None
    bss_code: str | None = None
    bss_message: str | None = None
    request_id: str | None = None


class AliyunAccountCreateResponse(AliyunAccountPublic):
    pass
