"""Match remote new-api channel rows to local Aliyun accounts (without HTTP).

new-api returns a flat list of channels. We locate the row for an account using:

1. **Remark binding** — we set `remark` to `awesome-token:{account_id}:{tpl_index}` on sync.
   Checked first: survives renames of the channel `name` or edits to `name_template` in config.
   Legacy single-channel format (`awesome-token:{account_id}` with no index) is also recognised
   for backward-compatibility during migration.

2. **Name + prefix fallback** — channels we manage use names derived from the configured
   template, prefixed with `AT-` (`CHANNEL_NAME_PREFIX`). If remark is missing (legacy rows),
   we match by exact expected name so old channels still resolve.

`account_id_from_remark` / `account_and_index_from_remark` are the inverse: parse the remark
to implement bulk cleanup in `sync_all_channels` phase 1.
"""

from __future__ import annotations

from typing import Any

from app.db.models import AliyunAccountRecord, NewApiConfigRecord

# Only treat channels whose name starts with this as ours when matching by name (second pass).
CHANNEL_NAME_PREFIX = "AT-"


def apply_channel_name_template(tpl: str, account: AliyunAccountRecord) -> str:
    """Fill `{username}` and `{id}` placeholders for the configured name template."""
    s = (tpl or "Aliyun {username}").strip()
    return s.replace("{username}", account.username).replace("{id}", account.id)


def expected_channel_name(cfg: NewApiConfigRecord, account: AliyunAccountRecord) -> str:
    """Return expected channel name using the first template entry (backward compat helper)."""
    templates = cfg.template if isinstance(cfg.template, list) else []
    if templates and isinstance(templates[0], dict):
        name_tpl = str(templates[0].get("name_template") or "Aliyun {username}")
    else:
        name_tpl = "Aliyun {username}"
    return apply_channel_name_template(name_tpl, account)


def channel_name_has_at_prefix(ch: dict[str, Any]) -> bool:
    name = str(ch.get("name") or "").strip()
    return name.startswith(CHANNEL_NAME_PREFIX)


# ---------------------------------------------------------------------------
# Remark parsing
# ---------------------------------------------------------------------------

def account_and_index_from_remark(remark: str | None) -> tuple[str | None, int | None]:
    """Parse ``awesome-token:{account_id}:{tpl_index}`` from a remark string.

    Returns ``(account_id, tpl_index)`` where *tpl_index* is ``None`` for old-format
    remarks that carry no index suffix (``awesome-token:{account_id}``).
    """
    s = str(remark or "")
    key = "awesome-token:"
    i = s.find(key)
    if i < 0:
        return None, None
    tail = s[i + len(key):].strip()
    if not tail:
        return None, None
    # Take the first whitespace/comma-separated token.
    token = tail.split()[0].split(",")[0].strip()
    if not token:
        return None, None
    # Split once on ":" to separate account_id from optional index.
    parts = token.split(":", 1)
    account_id = parts[0] or None
    if account_id is None:
        return None, None
    if len(parts) > 1:
        try:
            return account_id, int(parts[1])
        except (ValueError, TypeError):
            pass
    return account_id, None


def account_id_from_remark(remark: str | None) -> str | None:
    """Parse account id from remark, stripping any `:{index}` suffix."""
    account_id, _ = account_and_index_from_remark(remark)
    return account_id


# ---------------------------------------------------------------------------
# Multi-channel matching
# ---------------------------------------------------------------------------

def match_channel_row_for_template_entry(
    rows: list[dict[str, Any]],
    account: AliyunAccountRecord,
    tpl_index: int,
    name_tpl: str,
) -> dict[str, Any] | None:
    """Find the channel for a specific account + template entry index.

    Lookup order:
    1. Exact indexed remark ``awesome-token:{account_id}:{tpl_index}``.
    2. Legacy remark ``awesome-token:{account_id}`` (no index) — only for *tpl_index* 0,
       to migrate old single-channel rows to the new indexed format.
    3. ``AT-`` prefix + exact expected name (legacy rows with no remark).
    """
    new_token = f"awesome-token:{account.id}:{tpl_index}"
    expected_name = apply_channel_name_template(name_tpl, account).strip()

    # Pass 1: indexed remark
    for ch in rows:
        if not isinstance(ch, dict):
            continue
        if new_token in str(ch.get("remark") or ""):
            return ch

    # Pass 2: legacy remark (no index) matched only for index 0
    if tpl_index == 0:
        for ch in rows:
            if not isinstance(ch, dict):
                continue
            aid, idx = account_and_index_from_remark(ch.get("remark"))
            if aid == account.id and idx is None:
                return ch

    # Pass 3: AT- prefix + name match
    for ch in rows:
        if not isinstance(ch, dict):
            continue
        if not channel_name_has_at_prefix(ch):
            continue
        name = str(ch.get("name") or "").strip()
        if name == expected_name:
            return ch

    return None


def match_all_channel_rows_for_account(
    rows: list[dict[str, Any]],
    account: AliyunAccountRecord,
) -> list[tuple[int | None, dict[str, Any]]]:
    """Return all channels managed for this account as ``(template_index, channel_row)`` pairs.

    Matches channels with remark ``awesome-token:{account_id}:{index}`` or the legacy
    ``awesome-token:{account_id}`` format (returned with *template_index* ``None``).
    """
    prefix = f"awesome-token:{account.id}"
    out: list[tuple[int | None, dict[str, Any]]] = []
    for ch in rows:
        if not isinstance(ch, dict):
            continue
        remark = str(ch.get("remark") or "")
        if prefix not in remark:
            continue
        aid, idx = account_and_index_from_remark(remark)
        if aid != account.id:
            continue
        out.append((idx, ch))
    return out


# ---------------------------------------------------------------------------
# Backward-compat single-channel matcher (used by resolve_newapi_channel_id*)
# ---------------------------------------------------------------------------

def match_channel_row_for_account(
    rows: list[dict[str, Any]],
    cfg: NewApiConfigRecord,
    account: AliyunAccountRecord,
) -> dict[str, Any] | None:
    """Return the first channel row found for this account (any template index).

    Order: remark contains ``awesome-token:{id}`` first; then AT- prefix + exact name
    from any configured template entry.
    """
    token = f"awesome-token:{account.id}"

    for ch in rows:
        if not isinstance(ch, dict):
            continue
        if token in str(ch.get("remark") or ""):
            return ch

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
            if str(ch.get("name") or "").strip() == expected:
                return ch

    return None
