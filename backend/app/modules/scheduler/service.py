"""Register periodic jobs from persisted config and execute with run logging."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.config import get_settings
from app.db.models import ScheduledJobRecord
from app.db.store import scheduled_jobs
from app.memory_log_buffers import append_job_run
from app.scheduler import get_scheduler

logger = logging.getLogger(__name__)

JobHandler = Callable[[], Awaitable[None]]
_JOB_HANDLERS: dict[str, JobHandler] = {}


def _register_handlers() -> None:
    if _JOB_HANDLERS:
        return

    async def _aliyun() -> None:
        from app.modules.aliyun.tasks import sync_all_aliyun_accounts

        await sync_all_aliyun_accounts()

    async def _newapi_sync() -> None:
        from app.modules.newapi.sync_service import sync_all_channels

        await sync_all_channels()

    _JOB_HANDLERS["aliyun_sync"] = _aliyun
    _JOB_HANDLERS["newapi_sync"] = _newapi_sync


async def ensure_scheduled_job_records_async() -> list[ScheduledJobRecord]:
    _register_handlers()
    col = scheduled_jobs()
    existing = await col.list_items()
    by_id = {r.id: r for r in existing}

    # Legacy job id: migrate persisted row to newapi_sync.
    if "newapi_channel_test" in by_id and "newapi_sync" not in by_id:
        legacy = by_id["newapi_channel_test"]
        await col.delete("newapi_channel_test")
        now_mig = datetime.now(timezone.utc).isoformat()
        await col.create(
            {
                "id": "newapi_sync",
                "name": "New-API channel sync",
                "interval_minutes": max(0, int(legacy.interval_minutes)),
                "enabled": bool(legacy.enabled),
                "created_at": legacy.created_at or now_mig,
                "updated_at": now_mig,
            }
        )
        existing = await col.list_items()
        by_id = {r.id: r for r in existing}

    settings = get_settings()
    now = datetime.now(timezone.utc).isoformat()

    defaults: list[tuple[str, str, int]] = [
        ("aliyun_sync", "Aliyun account sync (BSS)", max(1, int(settings.aliyun_sync_interval_minutes or 30))),
        (
            "newapi_sync",
            "New-API channel sync",
            max(1, int(settings.newapi_sync_interval_minutes or 15)),
        ),
    ]

    for job_id, name, interval in defaults:
        if job_id in by_id:
            continue
        await col.create(
            {
                "id": job_id,
                "name": name,
                "interval_minutes": interval,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
        )

    return await col.list_items()


async def execute_job(job_id: str) -> None:
    _register_handlers()
    handler = _JOB_HANDLERS.get(job_id)
    if handler is None:
        raise ValueError(f"Unknown job: {job_id}")
    logger.info("Scheduled job started: job_id=%s", job_id)
    t0 = time.perf_counter()
    msg = ""
    ok = True
    try:
        await handler()
    except Exception as e:
        ok = False
        msg = str(e)
        logger.exception("Scheduled job failed: job_id=%s", job_id)
    finally:
        ms = (time.perf_counter() - t0) * 1000
        if ok:
            logger.info(
                "Scheduled job finished: job_id=%s duration_ms=%.2f",
                job_id,
                ms,
            )
        append_job_run(job_id=job_id, ok=ok, message=msg, duration_ms=ms)


def _job_runner_factory(jid: str):
    async def _run() -> None:
        await execute_job(jid)

    return _run


async def apply_all_scheduled_jobs() -> None:
    """Sync APScheduler from DB."""
    _register_handlers()
    rows = await ensure_scheduled_job_records_async()
    sched = get_scheduler()

    for jid in list(_JOB_HANDLERS.keys()):
        try:
            sched.remove_job(jid)
        except Exception:
            pass

    by_id = {r.id: r for r in rows}
    for jid in _JOB_HANDLERS:
        rec = by_id.get(jid)
        if rec is None:
            continue
        if not rec.enabled:
            logger.info("Job %s disabled, not scheduled", jid)
            continue
        minutes = int(rec.interval_minutes)
        if minutes <= 0:
            logger.info("Job %s interval 0, not scheduled", jid)
            continue
        sched.add_job(
            _job_runner_factory(jid),
            "interval",
            minutes=minutes,
            id=jid,
            replace_existing=True,
        )
        logger.info("Scheduled job %s every %s minutes", jid, minutes)


async def list_job_records() -> list[ScheduledJobRecord]:
    await ensure_scheduled_job_records_async()
    col = scheduled_jobs()
    rows = await col.list_items()
    return sorted(rows, key=lambda r: r.id)


async def update_job_record(
    job_id: str,
    *,
    interval_minutes: int | None = None,
    enabled: bool | None = None,
) -> ScheduledJobRecord:
    col = scheduled_jobs()
    rec = await col.get(job_id)
    if not rec:
        raise ValueError("job not found")
    patch: dict[str, Any] = {}
    if interval_minutes is not None:
        patch["interval_minutes"] = max(0, int(interval_minutes))
    if enabled is not None:
        patch["enabled"] = bool(enabled)
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = await col.update(job_id, patch)
    assert updated is not None
    await apply_all_scheduled_jobs()
    return updated
