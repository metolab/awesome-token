from __future__ import annotations

import logging

from app.db.store import aliyun_accounts
from app.modules.aliyun.service import format_sync_error, sync_aliyun_account_data

logger = logging.getLogger(__name__)


async def sync_all_aliyun_accounts() -> None:
    col = aliyun_accounts()
    accounts = await col.list_items()
    n = len(accounts)
    logger.info("Aliyun BSS sync started: accounts=%s", n)
    ok_n = 0
    err_n = 0
    for acc in accounts:
        try:
            synced = await sync_aliyun_account_data(acc)
            await col.update(acc.id, synced.model_dump(exclude={"id"}))
            ok_n += 1
            logger.info(
                "Aliyun BSS sync ok: account_id=%s username=%s",
                acc.id,
                acc.username,
            )
        except Exception as e:
            err_n += 1
            try:
                await col.update(acc.id, {"last_sync_error": format_sync_error(e)})
            except Exception:
                logger.exception("Failed to persist sync error for account_id=%s", acc.id)
            logger.warning(
                "Aliyun BSS sync failed: account_id=%s username=%s",
                acc.id,
                acc.username,
                exc_info=True,
            )
    logger.info(
        "Aliyun BSS sync finished: accounts=%s ok=%s failed=%s",
        n,
        ok_n,
        err_n,
    )
