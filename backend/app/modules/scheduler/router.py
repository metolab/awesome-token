from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.auth.dependencies import SessionUser
from app.memory_log_buffers import get_job_run_logs
from app.modules.scheduler.schemas import JobRunLogEntry, ScheduledJobOut, ScheduledJobPatch
from app.modules.scheduler.service import apply_all_scheduled_jobs, execute_job, list_job_records, update_job_record

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/jobs", response_model=list[ScheduledJobOut])
async def list_jobs(_user: SessionUser) -> list[ScheduledJobOut]:
    rows = await list_job_records()
    return [
        ScheduledJobOut(
            id=r.id,
            name=r.name,
            interval_minutes=r.interval_minutes,
            enabled=r.enabled,
        )
        for r in rows
    ]


@router.put("/jobs/{job_id}", response_model=ScheduledJobOut)
async def patch_job(job_id: str, body: ScheduledJobPatch, _user: SessionUser) -> ScheduledJobOut:
    try:
        r = await update_job_record(
            job_id,
            interval_minutes=body.interval_minutes,
            enabled=body.enabled,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="job not found") from None
    return ScheduledJobOut(
        id=r.id,
        name=r.name,
        interval_minutes=r.interval_minutes,
        enabled=r.enabled,
    )


@router.post("/jobs/{job_id}/run")
async def run_job_now(job_id: str, _user: SessionUser) -> dict[str, bool]:
    try:
        await execute_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown job") from None
    return {"ok": True}


@router.post("/reload")
async def reload_schedule(_user: SessionUser) -> dict[str, bool]:
    await apply_all_scheduled_jobs()
    return {"ok": True}


@router.get("/job-runs", response_model=list[JobRunLogEntry])
async def job_runs(_user: SessionUser) -> list[JobRunLogEntry]:
    raw = get_job_run_logs()
    return [JobRunLogEntry.model_validate(x) for x in raw]
