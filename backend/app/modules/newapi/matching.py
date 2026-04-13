"""Match remote new-api channel rows to local Aliyun accounts (without HTTP).

new-api returns a flat list of channels. We locate the row for an account using:

1. **Remark binding** — we set `remark` to `awesome-token:{account_id}` on sync. This is
   checked first: it survives renames of the channel `name` or edits to `name_template`
   in config.

2. **Name + prefix fallback** — channels we manage use names derived from the configured
   template, prefixed with `AT-` (`CHANNEL_NAME_PREFIX`). If remark is missing (legacy
   rows), we match exact expected name so old channels still resolve.

`account_id_from_remark` is the inverse: parse `awesome-token:` from a remark string to
implement bulk cleanup of rows whose account is no longer eligible (see `sync_all_channels`
phase 1 in `sync_service`).
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
    t = cfg.template or {}
    name_tpl = str(t.get("name_template") or "Aliyun {username}")
    return apply_channel_name_template(name_tpl, account)


def channel_name_has_at_prefix(ch: dict[str, Any]) -> bool:
    name = str(ch.get("name") or "").strip()
    return name.startswith(CHANNEL_NAME_PREFIX)


def match_channel_row_for_account(
    rows: list[dict[str, Any]],
    cfg: NewApiConfigRecord,
    account: AliyunAccountRecord,
) -> dict[str, Any] | None:
    """Return the channel dict for this account, or None.

    Order: remark contains `awesome-token:{id}` first; else AT- prefix + exact template name.
    """
    token = f"awesome-token:{account.id}"
    expected = expected_channel_name(cfg, account).strip()

    for ch in rows:
        if not isinstance(ch, dict):
            continue
        if token in str(ch.get("remark") or ""):
            return ch

    for ch in rows:
        if not isinstance(ch, dict):
            continue
        if not channel_name_has_at_prefix(ch):
            continue
        name = str(ch.get("name") or "").strip()
        if name == expected:
            return ch
    return None


def account_id_from_remark(remark: str | None) -> str | None:
    """Parse account id after `awesome-token:` (first token)."""
    s = str(remark or "")
    key = "awesome-token:"
    i = s.find(key)
    if i < 0:
        return None
    tail = s[i + len(key) :].strip()
    if not tail:
        return None
    return tail.split()[0].split(",")[0].strip() or None
