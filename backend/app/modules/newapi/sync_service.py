"""Orchestrate new-api admin API calls and local JSON config for channel lifecycle.

**Pipeline overview** (`sync_all_channels`):

Each eligible Aliyun account receives one new-api channel **per template entry** in
``NewApiConfigRecord.template``.  Channels are identified by the remark
``awesome-token:{account_id}:{tpl_index}`` (0-based).

1. **Remark-based cleanup** — Delete remote channels whose remark belongs to an account
   not in the top-N eligible set, or whose template index no longer exists, or that carry
   the old single-channel remark format (will be recreated with the indexed format).

2. **Legacy name-only cleanup** — Accounts outside top-N may still have channels matched
   only by ``AT-`` + template name (no remark). ``delete_channel_for_account`` resolves
   and deletes all such channels.

3. **Upsert eligible** — Create or full-PUT channels for every top-N account × every
   template entry, using priorities from `priority_map_for_accounts`.

HTTP response normalisation stays here because it is tied to `NewApiClient`
list/create/update responses, not pure matching logic.
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
    account_and_index_from_remark,
    account_id_from_remark,
    apply_channel_name_template,
    channel_name_has_at_prefix,
    match_all_channel_rows_for_account,
    match_channel_row_for_account,
    match_channel_row_for_template_entry,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CHANNEL_NAME_PREFIX",
    "PRIORITY_BASE",
    "account_eligible_for_newapi_sync",
    "account_and_index_from_remark",
    "coupon_qualifies_for_newapi",
    "delete_channel_for_account",
    "delete_channel_if_exists",
    "effective_min_coupon_balance_for_newapi",
    "ensure_channel_for_aliyun_account",
    "fetch_all_channels",
    "find_channel_for_account",
    "get_optional_client",
    "get_or_create_config",
    "match_all_channel_rows_for_account",
    "match_channel_row_for_account",
    "priority_map_for_accounts",
    "resolve_newapi_channel_id",
    "resolve_newapi_channel_id_map",
    "save_config",
    "sync_all_channels",
]


def _build_channel_body(
    tpl_entry: dict[str, Any],
    account: AliyunAccountRecord,
    priority: int,
    tpl_index: int,
) -> dict[str, Any]:
    """Build PUT/POST body from a single template entry plus computed fields.

    Sets ``name``, ``priority``, ``key``, and ``remark`` (``awesome-token:{id}:{index}``).
    """
    remark = f"awesome-token:{account.id}:{tpl_index}"
    name_tpl = str(tpl_entry.get("name_template") or "Aliyun {username}")
    name = apply_channel_name_template(name_tpl, account)

    ch = tpl_entry.get("channel")
    if not isinstance(ch, dict) or not ch:
        raise ValueError(
            f"new-api config template[{tpl_index}].channel is empty — "
            "set it to the channel `data` object from new-api"
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
            "template": [
                {
                    "name_template": "Aliyun {username}",
                    "channel": {},
                }
            ],
            "min_coupon_balance_for_newapi": 10.0,
            "max_channels_for_newapi_sync": 5,
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
    """Return the first channel row found for this account (any template index)."""
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


# ---------------------------------------------------------------------------
# Per-template-entry upsert helpers
# ---------------------------------------------------------------------------

async def _ensure_single_template_channel(
    client: NewApiClient,
    account: AliyunAccountRecord,
    priority: int,
    tpl_entry: dict[str, Any],
    tpl_index: int,
    *,
    channel_rows: list[dict[str, Any]],
) -> None:
    """Create or update the channel for one account + one template entry."""
    try:
        channel_body = _build_channel_body(tpl_entry, account, priority, tpl_index)
    except ValueError as e:
        logger.warning("new-api channel sync skipped (template %s): %s", tpl_index, e)
        return

    name_tpl = str(tpl_entry.get("name_template") or "Aliyun {username}")
    found = match_channel_row_for_template_entry(channel_rows, account, tpl_index, name_tpl)

    if found and found.get("id"):
        cid = int(found["id"])
        payload = copy.deepcopy(channel_body)
        payload["id"] = cid
        await client.update_channel(payload)
        _replace_channel_row_in_cache(channel_rows, cid, payload)
        return

    create_resp = await client.create_channel({"mode": "single", "channel": channel_body})
    cid = _extract_channel_id_from_response(create_resp)
    row = _unwrap(create_resp)
    if isinstance(row, dict) and row.get("id") is not None and cid is None:
        try:
            cid = int(row["id"])
        except (TypeError, ValueError):
            pass
    if cid is not None:
        _replace_channel_row_in_cache(channel_rows, cid, channel_body)
    if cid is None:
        found2 = match_channel_row_for_template_entry(channel_rows, account, tpl_index, name_tpl)
        if found2 and found2.get("id"):
            cid = int(found2["id"])
    if cid is None:
        logger.warning(
            "new-api channel created but could not resolve id for account %s template %s"
            " — check AT- name / remark / list API",
            account.id,
            tpl_index,
        )


async def _ensure_channels_for_account(
    account: AliyunAccountRecord,
    priority: int,
    *,
    client: NewApiClient,
    templates: list[dict[str, Any]],
    channel_rows: list[dict[str, Any]],
) -> None:
    """Create or update all template channels for one account."""
    if not templates:
        logger.warning(
            "new-api: no templates configured, skipping sync for account %s", account.id
        )
        return
    for idx, tpl_entry in enumerate(templates):
        if not isinstance(tpl_entry, dict):
            continue
        await _ensure_single_template_channel(
            client, account, priority, tpl_entry, idx, channel_rows=channel_rows
        )


async def ensure_channel_for_aliyun_account(account: AliyunAccountRecord) -> AliyunAccountRecord:
    cfg = await get_or_create_config()
    mb = effective_min_coupon_balance_for_newapi(cfg)
    max_ch = max(1, cfg.max_channels_for_newapi_sync)
    col = aliyun_accounts()
    accounts_list = await col.list_items()
    eligible = [a for a in accounts_list if account_eligible_for_newapi_sync(a, mb)]
    pmap = priority_map_for_accounts(eligible, mb)
    top_eligible_ids = {
        a.id
        for a in sorted(eligible, key=lambda a: pmap.get(a.id, PRIORITY_BASE), reverse=True)[:max_ch]
    }
    if account.id not in top_eligible_ids:
        await delete_channel_for_account(account)
        updated = await col.get(account.id)
        return updated or account

    client = get_optional_client(cfg)
    if client is None:
        return account
    templates = cfg.template if isinstance(cfg.template, list) else []
    channel_rows = await fetch_all_channels(client)
    priority = pmap.get(account.id, PRIORITY_BASE)
    await _ensure_channels_for_account(
        account, priority, client=client, templates=templates, channel_rows=channel_rows
    )
    updated = await col.get(account.id)
    return updated or account


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
    """Delete ALL channels managed for this account (any template index).

    Collects channels via:
    1. Remark-based scan (``match_all_channel_rows_for_account``) — covers all indexed and
       legacy-remark channels.
    2. Name-based fallback — covers truly legacy channels that pre-date the remark system
       (``AT-`` prefix + expected name from any template entry).
    """
    cfg = await get_or_create_config()
    client = get_optional_client(cfg)
    if client is None:
        return
    rows = channel_rows if channel_rows is not None else await fetch_all_channels(client)

    # Collect channels to delete without duplicates.
    seen_ids: set[int] = set()
    to_delete: list[tuple[int | None, dict[str, Any]]] = []

    for tpl_idx, ch in match_all_channel_rows_for_account(rows, account):
        try:
            cid = int(ch["id"])
        except (TypeError, ValueError, KeyError):
            continue
        if cid not in seen_ids:
            seen_ids.add(cid)
            to_delete.append((tpl_idx, ch))

    # Name-based fallback for rows that have no remark at all (pre-remark era).
    templates = cfg.template if isinstance(cfg.template, list) else []
    for tpl_entry in templates:
        if not isinstance(tpl_entry, dict):
            continue
        name_tpl = str(tpl_entry.get("name_template") or "Aliyun {username}")
        expected = apply_channel_name_template(name_tpl, account).strip()
        for ch in rows:
            if not isinstance(ch, dict):
                continue
            if not channel_name_has_at_prefix(ch):
                continue
            if str(ch.get("name") or "").strip() != expected:
                continue
            try:
                cid = int(ch["id"])
            except (TypeError, ValueError, KeyError):
                continue
            if cid not in seen_ids:
                seen_ids.add(cid)
                to_delete.append((None, ch))

    for tpl_idx, ch in to_delete:
        cid = ch.get("id")
        if cid is None:
            continue
        try:
            ic = int(cid)
            await client.delete_channel(ic)
            if channel_rows is not None:
                _drop_channel_from_rows(channel_rows, ic)
            logger.info(
                "new-api: deleted channel id=%s for account id=%s (template %s)",
                ic,
                account.id,
                tpl_idx,
            )
        except Exception:
            logger.exception("delete channel for account %s template %s", account.id, tpl_idx)


async def sync_all_channels() -> None:
    """Align new-api channels with local eligible accounts (see module docstring).

    Only the top-N accounts by priority (``NewApiConfigRecord.max_channels_for_newapi_sync``,
    default 5) receive channels; each eligible account gets one channel per template entry.
    Channels outside the top-N window or belonging to removed template indices are deleted.
    """
    cfg = await get_or_create_config()
    mb = effective_min_coupon_balance_for_newapi(cfg)
    max_ch = max(1, cfg.max_channels_for_newapi_sync)
    templates = cfg.template if isinstance(cfg.template, list) else []
    n_templates = len(templates)
    client = get_optional_client(cfg)
    if client is None:
        return
    col = aliyun_accounts()
    accounts = await col.list_items()
    eligible = [a for a in accounts if account_eligible_for_newapi_sync(a, mb)]
    pmap = priority_map_for_accounts(eligible, mb)

    top_eligible = sorted(eligible, key=lambda a: pmap.get(a.id, PRIORITY_BASE), reverse=True)[:max_ch]
    top_eligible_ids = {a.id for a in top_eligible}

    channel_rows = await fetch_all_channels(client)

    # Phase 1 — remark-based cleanup.
    # Delete channels whose account is outside top-N, whose template index no longer exists,
    # or that carry the old single-channel remark format (will be recreated below).
    for ch in list(channel_rows):
        if not isinstance(ch, dict):
            continue
        aid, idx = account_and_index_from_remark(ch.get("remark"))
        if aid is None:
            continue

        if aid not in top_eligible_ids:
            reason = "account_ineligible_or_outside_top_n"
        elif idx is None:
            reason = "old_format_remark"
        elif idx >= n_templates:
            reason = "template_index_removed"
        else:
            continue  # Keep this channel.

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
                "new-api: removed channel id=%s (account=%s tpl_idx=%s reason=%s)",
                ic,
                aid,
                idx,
                reason,
            )
        except Exception:
            logger.exception(
                "new-api: failed to delete channel id=%s for account %s", ic, aid
            )

    # Phase 2 — legacy name-based cleanup for accounts outside top-N.
    for acc in accounts:
        if acc.id in top_eligible_ids:
            continue
        await delete_channel_for_account(acc, channel_rows=channel_rows)

    # Phase 3 — upsert: top-N accounts × N template entries.
    for acc in top_eligible:
        priority = pmap.get(acc.id, PRIORITY_BASE)
        await _ensure_channels_for_account(
            acc, priority, client=client, templates=templates, channel_rows=channel_rows
        )
