from __future__ import annotations

import hashlib
import secrets
from app.db.models import AliyunAccountRecord, OpenApiKeyRecord
from app.db.store import aliyun_accounts, newapi_config, openapi_keys
from app.modules.newapi.eligibility import (
    effective_min_coupon_balance_for_newapi,
    pick_highest_priority_eligible_account,
)


def hash_api_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_api_secret() -> str:
    return "at_" + secrets.token_urlsafe(32)


def key_prefix_from_secret(secret: str, max_len: int = 14) -> str:
    s = secret.strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…"


async def verify_api_secret(raw: str) -> OpenApiKeyRecord | None:
    col = openapi_keys()
    rows = await col.list_items()
    if not raw or not rows:
        return None
    digest = hash_api_secret(raw)
    for row in rows:
        if secrets.compare_digest(digest, row.key_hash):
            return row
    return None


async def resolve_best_bailian_token() -> tuple[AliyunAccountRecord, str] | None:
    """Pick the same account new-api would give the top channel priority; return its Bailian key."""
    cfg = await newapi_config().get("singleton")
    mb = effective_min_coupon_balance_for_newapi(cfg) if cfg else 10.0
    accounts = await aliyun_accounts().list_items()
    best = pick_highest_priority_eligible_account(accounts, mb)
    if best is None:
        return None
    tok = (best.bailian_api_key or "").strip()
    if not tok:
        return None
    return (best, tok)
