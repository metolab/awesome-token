"""Aliyun account business logic."""

from __future__ import annotations

from typing import Any

from app.db.models import AliyunAccountRecord, BalanceSnapshot, CashCouponSnapshot
from app.modules.aliyun.bss_client import fetch_account_snapshot
from app.modules.aliyun.schemas import AliyunAccountCreate, AliyunAccountDetail, AliyunAccountPublic, AliyunAccountUpdate


def format_sync_error(exc: BaseException, max_len: int = 4000) -> str:
    """Short message persisted when BSS sync fails (shown in UI)."""
    s = f"{type(exc).__name__}: {exc!s}".strip()
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def _parse_balance(raw: dict[str, Any] | None) -> BalanceSnapshot | None:
    if not raw:
        return None
    data = raw.get("Data") or raw.get("data") or raw
    if isinstance(data, dict):
        return BalanceSnapshot(
            available_amount=_str_or_none(data.get("AvailableAmount")),
            available_cash_amount=_str_or_none(data.get("AvailableCashAmount")),
            currency=_str_or_none(data.get("Currency")),
            credit_amount=_str_or_none(data.get("CreditAmount")),
            mybank_credit_amount=_str_or_none(data.get("MybankCreditAmount")),
        )
    return None


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    return str(v)


def _parse_coupons(raw: dict[str, Any] | None) -> list[CashCouponSnapshot]:
    if not raw:
        return []
    data = raw.get("Data") or raw.get("data") or raw
    if not isinstance(data, dict):
        return []
    # BSS OpenAPI 2017-12-14: SDK maps list to Data.CashCoupon (see QueryCashCouponsResponseBodyData.to_map).
    lst = (
        data.get("CashCoupon")
        or data.get("CashCouponList")
        or data.get("cash_coupon_list")
        or data.get("CashCoupons")
        or []
    )
    if isinstance(lst, dict) and "CashCoupon" in lst:
        lst = lst.get("CashCoupon") or []
    if not isinstance(lst, list):
        lst = [lst] if lst else []
    out: list[CashCouponSnapshot] = []
    for item in lst:
        if not isinstance(item, dict):
            continue
        out.append(
            CashCouponSnapshot(
                coupon_id=_str_or_none(item.get("CashCouponId") or item.get("cash_coupon_id")),
                status=_str_or_none(item.get("Status") or item.get("status")),
                balance=_str_or_none(item.get("Balance") or item.get("balance")),
                nominal_value=_str_or_none(item.get("NominalValue") or item.get("nominal_value")),
                granted_time=_str_or_none(item.get("GrantedTime") or item.get("granted_time")),
                expiry_time=_str_or_none(item.get("ExpiryTime") or item.get("expiry_time")),
                raw=item,
            )
        )
    return out


def _parse_transactions(raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows, _meta = extract_account_transactions_from_bss_body(raw)
    return rows[:50]


def _extract_transaction_rows_from_data(data: dict[str, Any]) -> list[Any]:
    """BSS may return AccountTransactionsList as nested dict or as a plain array."""
    atl = data.get("AccountTransactionsList") or data.get("account_transactions_list")
    if isinstance(atl, list):
        return atl
    if not isinstance(atl, dict):
        return []
    return (
        atl.get("AccountTransactionsList")
        or atl.get("account_transactions_list")
        or atl.get("AccountTransaction")
        or atl.get("account_transaction")
        or []
    )


def extract_account_transactions_from_bss_body(
    raw: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse QueryAccountTransactions response body; returns rows and paging meta."""
    meta: dict[str, Any] = {}
    if not raw:
        return [], meta
    meta["bss_success"] = raw.get("Success")
    meta["bss_code"] = raw.get("Code") or raw.get("code")
    meta["bss_message"] = raw.get("Message") or raw.get("message")
    meta["request_id"] = raw.get("RequestId") or raw.get("request_id")
    data = raw.get("Data") or raw.get("data")
    if not isinstance(data, dict):
        return [], meta
    meta.update(
        {
            "account_name": data.get("AccountName") or data.get("account_name"),
            "page_num": data.get("PageNum") or data.get("page_num"),
            "page_size": data.get("PageSize") or data.get("page_size"),
            "total_count": data.get("TotalCount") if data.get("TotalCount") is not None else data.get("total_count"),
        }
    )
    rows_raw = _extract_transaction_rows_from_data(data)
    if not isinstance(rows_raw, list):
        return [], meta
    plain: list[dict[str, Any]] = []
    for r in rows_raw:
        if r is None:
            continue
        if isinstance(r, dict):
            plain.append(_normalize_transaction_row(r))
    return plain, meta


def _normalize_transaction_row(r: dict[str, Any]) -> dict[str, Any]:
    """Stable keys for API / UI (BSS uses PascalCase in to_map)."""
    return {
        "amount": r.get("Amount") or r.get("amount"),
        "balance": r.get("Balance") or r.get("balance"),
        "billing_cycle": r.get("BillingCycle") or r.get("billing_cycle"),
        "fund_type": r.get("FundType") or r.get("fund_type"),
        "record_id": r.get("RecordID") or r.get("record_id"),
        "remarks": r.get("Remarks") or r.get("remarks"),
        "transaction_account": r.get("TransactionAccount") or r.get("transaction_account"),
        "transaction_channel": r.get("TransactionChannel") or r.get("transaction_channel"),
        "transaction_channel_sn": r.get("TransactionChannelSN") or r.get("transaction_channel_sn"),
        "transaction_flow": r.get("TransactionFlow") or r.get("transaction_flow"),
        "transaction_number": r.get("TransactionNumber") or r.get("transaction_number"),
        "transaction_time": r.get("TransactionTime") or r.get("transaction_time"),
        "transaction_type": r.get("TransactionType") or r.get("transaction_type"),
    }


def _pick(r: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in r and r[k] is not None:
            return r[k]
    return None


def _normalize_bill_line_row(r: dict[str, Any]) -> dict[str, Any]:
    """QueryBill Data.Items.Item → stable keys for API / UI."""
    return {
        "product_name": _pick(r, "ProductName", "product_name"),
        "product_code": _pick(r, "ProductCode", "product_code"),
        "product_type": _pick(r, "ProductType", "product_type"),
        "product_detail": _pick(r, "ProductDetail", "product_detail"),
        "subscription_type": _pick(r, "SubscriptionType", "subscription_type"),
        "item": _pick(r, "Item", "item"),
        "pretax_gross_amount": _pick(r, "PretaxGrossAmount", "pretax_gross_amount"),
        "pretax_amount": _pick(r, "PretaxAmount", "pretax_amount"),
        "after_tax_amount": _pick(r, "AfterTaxAmount", "after_tax_amount"),
        "currency": _pick(r, "Currency", "currency"),
        "deducted_by_cash_coupons": _pick(r, "DeductedByCashCoupons", "deducted_by_cash_coupons"),
        "deducted_by_coupons": _pick(r, "DeductedByCoupons", "deducted_by_coupons"),
        "cash_amount": _pick(r, "CashAmount", "cash_amount"),
        "payment_time": _pick(r, "PaymentTime", "payment_time"),
        "usage_start_time": _pick(r, "UsageStartTime", "usage_start_time"),
        "usage_end_time": _pick(r, "UsageEndTime", "usage_end_time"),
        "status": _pick(r, "Status", "status"),
        "record_id": _pick(r, "RecordID", "record_id"),
        "tax": _pick(r, "Tax", "tax"),
        "pip_code": _pick(r, "PipCode", "pip_code"),
        "commodity_code": _pick(r, "CommodityCode", "commodity_code"),
    }


def extract_query_bill_from_bss_body(
    raw: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse QueryBill response body (Data.Items.Item)."""
    meta: dict[str, Any] = {}
    if not raw:
        return [], meta
    meta["bss_success"] = raw.get("Success")
    meta["bss_code"] = raw.get("Code") or raw.get("code")
    meta["bss_message"] = raw.get("Message") or raw.get("message")
    meta["request_id"] = raw.get("RequestId") or raw.get("request_id")
    data = raw.get("Data") or raw.get("data")
    if not isinstance(data, dict):
        return [], meta
    meta.update(
        {
            "bss_account_id": data.get("AccountID") or data.get("account_id"),
            "account_name": data.get("AccountName") or data.get("account_name"),
            "billing_cycle": data.get("BillingCycle") or data.get("billing_cycle"),
            "page_num": data.get("PageNum"),
            "page_size": data.get("PageSize"),
            "total_count": data.get("TotalCount"),
        }
    )
    items_obj = data.get("Items") or data.get("items")
    rows_raw: list[Any] = []
    if isinstance(items_obj, dict):
        rows_raw = items_obj.get("Item") or items_obj.get("item") or []
    elif isinstance(items_obj, list):
        rows_raw = items_obj
    if not isinstance(rows_raw, list):
        rows_raw = []
    plain = [_normalize_bill_line_row(x) for x in rows_raw if isinstance(x, dict)]
    return plain, meta


def public_from_record(
    rec: AliyunAccountRecord,
    *,
    newapi_channel_id: int | None = None,
) -> AliyunAccountPublic:
    return AliyunAccountPublic(
        id=rec.id,
        username=rec.username,
        remark=rec.remark,
        balance=rec.balance,
        coupons=rec.coupons,
        last_synced_at=rec.last_synced_at,
        newapi_channel_id=newapi_channel_id,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def detail_from_record(
    rec: AliyunAccountRecord,
    *,
    newapi_channel_id: int | None = None,
) -> AliyunAccountDetail:
    base = public_from_record(rec, newapi_channel_id=newapi_channel_id)
    return AliyunAccountDetail(
        **base.model_dump(),
        access_key_id=rec.access_key_id,
        last_transactions=rec.last_transactions,
    )


async def sync_aliyun_account_data(account: AliyunAccountRecord) -> AliyunAccountRecord:
    snap = await fetch_account_snapshot(account.access_key_id, account.access_key_secret)
    bal_raw = snap.get("balance") or {}
    tx_raw = snap.get("transactions") or {}
    cp_raw = snap.get("coupons") or {}

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    partial = {
        "balance": _parse_balance(bal_raw if isinstance(bal_raw, dict) else None),
        "coupons": _parse_coupons(cp_raw if isinstance(cp_raw, dict) else None),
        "last_transactions": _parse_transactions(tx_raw if isinstance(tx_raw, dict) else None),
        "last_synced_at": now,
        "last_sync_error": None,
    }
    merged = account.model_dump()
    for k, v in partial.items():
        if k == "last_sync_error" or v is not None:
            merged[k] = v
    return AliyunAccountRecord.model_validate(merged)
