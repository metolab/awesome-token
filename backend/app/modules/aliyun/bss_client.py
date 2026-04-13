"""Alibaba Cloud BSS OpenAPI async client wrapper."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from alibabacloud_bssopenapi20171214.client import Client as BssClient
from alibabacloud_bssopenapi20171214 import models as bss_models
from alibabacloud_tea_openapi import utils_models as tea_models


def _make_client(access_key_id: str, access_key_secret: str, region_id: str = "cn-hangzhou") -> BssClient:
    cfg = tea_models.Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        region_id=region_id,
    )
    return BssClient(cfg)


def _to_plain(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "to_map"):
        return obj.to_map()
    if isinstance(obj, dict):
        return obj
    return obj


async def fetch_account_snapshot(
    access_key_id: str,
    access_key_secret: str,
) -> dict[str, Any]:
    """Query balance, recent transactions, and cash coupons."""
    client = _make_client(access_key_id, access_key_secret)

    balance_resp = await client.query_account_balance_async()
    balance_map = _to_plain(getattr(balance_resp, "body", balance_resp))

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    tx_req = bss_models.QueryAccountTransactionsRequest(
        create_time_start=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        create_time_end=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        page_num=1,
        page_size=50,
    )
    tx_resp = await client.query_account_transactions_async(tx_req)
    tx_map = _to_plain(getattr(tx_resp, "body", tx_resp))

    coupon_req = bss_models.QueryCashCouponsRequest()
    coupon_resp = await client.query_cash_coupons_async(coupon_req)
    coupon_map = _to_plain(getattr(coupon_resp, "body", coupon_resp))

    return {
        "balance": balance_map,
        "transactions": tx_map,
        "coupons": coupon_map,
    }


async def fetch_query_bill(
    access_key_id: str,
    access_key_secret: str,
    *,
    billing_cycle: str,
    page_num: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """BSS QueryBill — bill lines for a calendar month (YYYY-MM)."""
    client = _make_client(access_key_id, access_key_secret)
    ps = max(1, min(page_size, 300))
    pn = max(1, page_num)
    req = bss_models.QueryBillRequest(
        billing_cycle=billing_cycle,
        page_num=pn,
        page_size=ps,
    )
    resp = await client.query_bill_async(req)
    return _to_plain(getattr(resp, "body", resp))
