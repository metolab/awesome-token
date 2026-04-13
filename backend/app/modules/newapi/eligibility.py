"""Coupon-based eligibility and channel priority for new-api sync.

This module answers: *which local Aliyun accounts may have a new-api channel* and *in what
priority order* channels should be numbered (1000, 1001, …). It does **not** talk to HTTP or
the JSON stores — that lives in `sync_service`.

**Threshold:** `min_coupon_balance_for_newapi` on `NewApiConfigRecord` is the lower bound
(exclusive). We require balance **strictly greater than** that value so accounts sitting
exactly on the cutoff do not flap when rounding or BSS formatting differs.

**Priority:** Among accounts that qualify, we sort by soonest **qualifying** coupon expiry
(coupons that pass the balance rule). Accounts with no future-dated qualifying coupon fall
back to older `created_at` first. Larger `priority` integers in new-api mean “prefer this
channel earlier” in the product’s ordering band (see `PRIORITY_BASE` + index).
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import AliyunAccountRecord, CashCouponSnapshot, NewApiConfigRecord

PRIORITY_BASE = 1000
"""Sequential channel priorities 1000, 1001, … — higher = preferred earlier in new-api."""


def _parse_dt(created_at: str) -> float:
    try:
        s = created_at.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return datetime.now(timezone.utc).timestamp()


def _parse_expiry_time(expiry: str | None) -> float | None:
    if not expiry or not str(expiry).strip():
        return None
    try:
        s = str(expiry).replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def effective_min_coupon_balance_for_newapi(cfg: NewApiConfigRecord) -> float:
    """Return configured minimum balance; invalid stored values fall back to 10.0."""
    try:
        return max(0.0, float(cfg.min_coupon_balance_for_newapi))
    except (TypeError, ValueError):
        return 10.0


def _parse_coupon_balance_value(c: CashCouponSnapshot) -> float | None:
    if c.balance is None or not str(c.balance).strip():
        return None
    try:
        return float(str(c.balance).replace(",", "").strip())
    except ValueError:
        return None


def _coupon_is_expired(c: CashCouponSnapshot) -> bool:
    return (c.status or "").strip().lower() == "expired"


def coupon_qualifies_for_newapi(c: CashCouponSnapshot, min_balance: float) -> bool:
    """True if coupon is not expired and parsed balance is strictly above `min_balance`."""
    if _coupon_is_expired(c):
        return False
    bal = _parse_coupon_balance_value(c)
    return bal is not None and bal > min_balance


def account_eligible_for_newapi_sync(account: AliyunAccountRecord, min_balance: float) -> bool:
    """True if at least one coupon qualifies — the account may receive a new-api channel."""
    return any(coupon_qualifies_for_newapi(c, min_balance) for c in account.coupons)


def _account_priority_sort_key(account: AliyunAccountRecord, min_balance: float) -> tuple:
    """Sort key: soonest future expiry among qualifying coupons, else account age."""
    now = datetime.now(timezone.utc).timestamp()
    future_expiries: list[float] = []
    for c in account.coupons:
        if not coupon_qualifies_for_newapi(c, min_balance):
            continue
        t = _parse_expiry_time(c.expiry_time)
        if t is not None and t > now:
            future_expiries.append(t)

    if future_expiries:
        return (0, min(future_expiries), account.id)
    created = _parse_dt(account.created_at)
    return (1, created, account.id)


def priority_map_for_accounts(
    accounts: list[AliyunAccountRecord],
    min_balance: float,
) -> dict[str, int]:
    """Map account id → PRIORITY_BASE + offset (higher = earlier preference in new-api)."""
    ordered = sorted(accounts, key=lambda a: _account_priority_sort_key(a, min_balance))
    n = len(ordered)
    out: dict[str, int] = {}
    for i, acc in enumerate(ordered):
        out[acc.id] = PRIORITY_BASE + (n - 1 - i)
    return out


def pick_highest_priority_eligible_account(
    accounts: list[AliyunAccountRecord],
    min_balance: float,
) -> AliyunAccountRecord | None:
    """The account that receives the largest new-api channel priority (same ordering as sync).

    Eligibility and sort keys match ``priority_map_for_accounts`` / channel sync.
    """
    eligible = [a for a in accounts if account_eligible_for_newapi_sync(a, min_balance)]
    if not eligible:
        return None
    ordered = sorted(eligible, key=lambda a: _account_priority_sort_key(a, min_balance))
    return ordered[0]
