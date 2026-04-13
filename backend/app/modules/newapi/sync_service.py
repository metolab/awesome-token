"""Orchestrate new-api admin API calls and local JSON config for channel lifecycle.

**Pipeline overview** (`sync_all_channels`):

1. **Remark-based cleanup** — Delete remote channels whose `remark` contains
   `awesome-token:{id}` when `id` is not in the *eligible* account set (coupon rules in
   `eligibility`). Handles orphans (account removed locally) and ineligible accounts in one pass.

2. **Legacy name-only cleanup** — Ineligible local accounts may still have a channel matched
   only by `AT-` + template name (no remark). `delete_channel_for_account` resolves via
   `match_channel_row_for_account` and deletes.

3. **Upsert eligible** — Create or full-PUT channels for accounts that pass eligibility, using
   priorities from `priority_map_for_accounts`.

HTTP response normalization (`_channel_rows_from_list_response`, etc.) stays here because it
is tied to `NewApiClient` list/create/update responses, not pure matching logic.
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any

from app.db.models import AliyunAccountRecord, NewApiConfigRecord
from app.db.store import aliyun_accounts, newapi_config
from app.modules.newapi.client import NewApiClient
from app.modules.newapi.eligibility import (
    PRIORITY_BASE,
    account_eligible_for_newapi_sync,
    coupon_qualifies_for_newapi,
    effective_min_coupon_balance_for_newapi,
    priority_map_for_accounts,
)
from app.modules.newapi.matching import (
    CHANNEL_NAME_PREFIX,
    account_id_from_remark,
    apply_channel_name_template,
    match_channel_row_for_account,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CHANNEL_NAME_PREFIX",
    "PRIORITY_BASE",
    "account_eligible_for_newapi_sync",
    "coupon_qualifies_for_newapi",
    "delete_channel_for_account",
    "delete_channel_if_exists",
    "effective_min_coupon_balance_for_newapi",
    "ensure_channel_for_aliyun_account",
    "fetch_all_channels",
    "find_channel_for_account",
    "get_optional_client",
    "get_or_create_config",
    "match_channel_row_for_account",
    "priority_map_for_accounts",
    "resolve_newapi_channel_id",
    "resolve_newapi_channel_id_map",
    "save_config",
    "sync_all_channels",
]


def _build_channel_body(
    cfg: NewApiConfigRecord,
    account: AliyunAccountRecord,
    priority: int,
) -> dict[str, Any]:
    """Build PUT/POST body from template plus computed name, priority, key, remark."""
    remark = f"awesome-token:{account.id}"
    t = cfg.template or {}
    name_tpl = str(t.get("name_template") or "Aliyun {username}")
    name = apply_channel_name_template(name_tpl, account)

    ch = t.get("channel")
    if not isinstance(ch, dict) or not ch:
        raise ValueError(
            "new-api config template.channel is empty — set it to the channel `data` object from new-api"
        )
    body = copy.deepcopy(dict(ch))
    body.pop("id", None)
    body["name"] = name
    body["priority"] = int(priority)
    body["key"] = account.bailian_api_key
    body["remark"] = remark
    return body


async def get_or_create_config() -> NewApiConfigRecord:
    col = newapi_config()
    rows = await col.list_items()
    if rows:
        return rows[0]
    now = datetime.now(timezone.utc).isoformat()
    return await col.create(
        {
            "id": "singleton",
            "base_url": "",
            "admin_token": "",
            "admin_user_id": "",
            "template": {
                "name_template": "Aliyun {username}",
                "channel": {},
            },
            "min_coupon_balance_for_newapi": 10.0,
            "created_at": now,
            "updated_at": now,
        }
    )


async def save_config(body: dict[str, Any]) -> NewApiConfigRecord:
    col = newapi_config()
    current = await get_or_create_config()
    merged = current.model_dump()
    for key, val in body.items():
        if key == "id":
            continue
        merged[key] = val
    merged["updated_at"] = datetime.now(timezone.utc).isoformat()
    patch = {k: v for k, v in merged.items() if k != "id"}
    updated = await col.update(current.id, patch)
    assert updated is not None
    return updated


def get_optional_client(cfg: NewApiConfigRecord) -> NewApiClient | None:
    if not cfg.base_url or not cfg.admin_token or not cfg.admin_user_id:
        return None
    return NewApiClient(cfg.base_url, cfg.admin_token, cfg.admin_user_id)


def _unwrap(resp: dict[str, Any]) -> dict[str, Any]:
    data = resp.get("data")
    if isinstance(data, dict):
        return data
    return resp


def _channel_rows_from_list_response(res: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize new-api list/search JSON to a list of channel dicts."""
    root = res.get("data", res)
    if isinstance(root, list):
        lst = root
    elif isinstance(root, dict):
        lst = (
            root.get("items")
            or root.get("Items")
            or root.get("list")
            or root.get("data")
            or []
        )
        if isinstance(lst, dict):
            lst = lst.get("items") or lst.get("Items") or []
    else:
        lst = []
    if not isinstance(lst, list):
        return []
    return [x for x in lst if isinstance(x, dict)]


def _extract_channel_id_from_response(resp: dict[str, Any]) -> int | None:
    """POST/PUT create channel responses often include data.id."""
    if not isinstance(resp, dict):
        return None
    for key in ("data", "Data", "channel", "Channel"):
        d = resp.get(key)
        if isinstance(d, dict) and d.get("id") is not None:
            try:
                return int(d["id"])
            except (TypeError, ValueError):
                continue
    return None


def _drop_channel_from_rows(rows: list[dict[str, Any]], channel_id: int) -> None:
    i = 0
    while i < len(rows):
        row = rows[i]
        if not isinstance(row, dict):
            i += 1
            continue
        try:
            if int(row.get("id", -1)) == channel_id:
                rows.pop(i)
                return
        except (TypeError, ValueError):
            i += 1


def _replace_channel_row_in_cache(
    rows: list[dict[str, Any]],
    channel_id: int,
    channel_fields: dict[str, Any],
) -> None:
    """Update or append one row so a single fetch_all snapshot stays consistent within sync_all."""
    merged = {**copy.deepcopy(channel_fields), "id": channel_id}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        try:
            if int(row.get("id", -1)) == channel_id:
                rows[i] = merged
                return
        except (TypeError, ValueError):
            continue
    rows.append(merged)


async def fetch_all_channels(client: NewApiClient) -> list[dict[str, Any]]:
    """Paginate GET /api/channel/ — used to match accounts without storing channel ids locally."""
    out: list[dict[str, Any]] = []
    page = 1
    while page <= 100:
        res = await client.list_channels(page=page, page_size=100)
        rows = _channel_rows_from_list_response(res)
        out.extend([r for r in rows if isinstance(r, dict)])
        if len(rows) < 100:
            break
        page += 1
    return out


async def find_channel_for_account(
    client: NewApiClient,
    cfg: NewApiConfigRecord,
    account: AliyunAccountRecord,
    *,
    channel_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    rows = channel_rows
    if rows is None:
        rows = await fetch_all_channels(client)
    return match_channel_row_for_account(rows, cfg, account)


async def resolve_newapi_channel_id(account: AliyunAccountRecord) -> int | None:
    cfg = await get_or_create_config()
    client = get_optional_client(cfg)
    if client is None:
        return None
    ch = await find_channel_for_account(client, cfg, account)
    if ch and ch.get("id") is not None:
        try:
            return int(ch["id"])
        except (TypeError, ValueError):
            return None
    return None


async def resolve_newapi_channel_id_map(
    accounts: list[AliyunAccountRecord],
) -> dict[str, int | None]:
    cfg = await get_or_create_config()
    client = get_optional_client(cfg)
    if client is None:
        return {a.id: None for a in accounts}
    rows = await fetch_all_channels(client)
    out: dict[str, int | None] = {}
    for a in accounts:
        ch = match_channel_row_for_account(rows, cfg, a)
        if ch and ch.get("id") is not None:
            try:
                out[a.id] = int(ch["id"])
            except (TypeError, ValueError):
                out[a.id] = None
        else:
            out[a.id] = None
    return out


async def _ensure_channel_single(
    account: AliyunAccountRecord,
    priority: int,
    *,
    channel_rows: list[dict[str, Any]] | None = None,
) -> AliyunAccountRecord:
    cfg = await get_or_create_config()
    client = get_optional_client(cfg)
    if client is None:
        return account

    try:
        channel_body = _build_channel_body(cfg, account, priority)
    except ValueError as e:
        logger.warning("new-api channel sync skipped: %s", e)
        return account

    col = aliyun_accounts()
    local_rows = channel_rows
    found = await find_channel_for_account(client, cfg, account, channel_rows=local_rows)

    if found and found.get("id"):
        cid = int(found["id"])
        payload = copy.deepcopy(channel_body)
        payload["id"] = cid
        await client.update_channel(payload)
        if local_rows is not None:
            _replace_channel_row_in_cache(local_rows, cid, payload)
        updated = await col.get(account.id)
        return updated or account

    create_resp = await client.create_channel({"mode": "single", "channel": channel_body})
    cid = _extract_channel_id_from_response(create_resp)
    row = _unwrap(create_resp)
    if isinstance(row, dict) and row.get("id") is not None and cid is None:
        try:
            cid = int(row["id"])
        except (TypeError, ValueError):
            pass
    if local_rows is not None and cid is not None:
        _replace_channel_row_in_cache(local_rows, cid, channel_body)
    if cid is None:
        found2 = await find_channel_for_account(client, cfg, account, channel_rows=local_rows)
        if found2 and found2.get("id"):
            cid = int(found2["id"])
    if cid is None:
        logger.warning(
            "new-api channel created but could not resolve id for account %s — check AT- name / remark / list API",
            account.id,
        )
    updated = await col.get(account.id)
    return updated or account


async def ensure_channel_for_aliyun_account(account: AliyunAccountRecord) -> AliyunAccountRecord:
    cfg = await get_or_create_config()
    mb = effective_min_coupon_balance_for_newapi(cfg)
    col = aliyun_accounts()
    accounts = await col.list_items()
    eligible = [a for a in accounts if account_eligible_for_newapi_sync(a, mb)]
    pmap = priority_map_for_accounts(eligible, mb)
    if not account_eligible_for_newapi_sync(account, mb):
        await delete_channel_for_account(account)
        updated = await col.get(account.id)
        return updated or account
    priority = pmap.get(account.id, PRIORITY_BASE)
    return await _ensure_channel_single(account, priority)


async def delete_channel_if_exists(channel_id: int) -> None:
    cfg = await get_or_create_config()
    client = get_optional_client(cfg)
    if client is None:
        return
    await client.delete_channel(channel_id)


async def delete_channel_for_account(
    account: AliyunAccountRecord,
    *,
    channel_rows: list[dict[str, Any]] | None = None,
) -> None:
    """Resolve channel on new-api and delete; no local id stored."""
    cfg = await get_or_create_config()
    client = get_optional_client(cfg)
    if client is None:
        return
    ch = await find_channel_for_account(client, cfg, account, channel_rows=channel_rows)
    if ch and ch.get("id") is not None:
        try:
            cid = int(ch["id"])
            await client.delete_channel(cid)
            if channel_rows is not None:
                _drop_channel_from_rows(channel_rows, cid)
            logger.info(
                "new-api: deleted channel id=%s for ineligible account id=%s",
                cid,
                account.id,
            )
        except Exception:
            logger.exception("delete channel for account %s", account.id)


async def sync_all_channels() -> None:
    """Align new-api channels with local eligible accounts (see module docstring)."""
    cfg = await get_or_create_config()
    mb = effective_min_coupon_balance_for_newapi(cfg)
    client = get_optional_client(cfg)
    if client is None:
        return
    col = aliyun_accounts()
    accounts = await col.list_items()
    eligible = [a for a in accounts if account_eligible_for_newapi_sync(a, mb)]
    eligible_ids = {a.id for a in eligible}
    pmap = priority_map_for_accounts(eligible, mb)
    channel_rows = await fetch_all_channels(client)

    # Phase 1 — remark-based: drop managed rows whose account id is not eligible.
    for ch in list(channel_rows):
        if not isinstance(ch, dict):
            continue
        rid = account_id_from_remark(ch.get("remark"))
        if rid is None:
            continue
        if rid in eligible_ids:
            continue
        cid = ch.get("id")
        if cid is None:
            continue
        try:
            ic = int(cid)
        except (TypeError, ValueError):
            continue
        try:
            await client.delete_channel(ic)
            _drop_channel_from_rows(channel_rows, ic)
            logger.info(
                "new-api: removed channel id=%s (account %s not active: coupon balance rule)",
                ic,
                rid,
            )
        except Exception:
            logger.exception(
                "new-api: failed to delete channel id=%s for account %s",
                ic,
                rid,
            )

    # Phase 2 — legacy rows without remark: ineligible local accounts only.
    for acc in accounts:
        if account_eligible_for_newapi_sync(acc, mb):
            continue
        await delete_channel_for_account(acc, channel_rows=channel_rows)

    # Phase 3 — upsert for eligible accounts.
    for acc in eligible:
        await _ensure_channel_single(
            acc,
            pmap.get(acc.id, PRIORITY_BASE),
            channel_rows=channel_rows,
        )
