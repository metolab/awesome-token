from __future__ import annotations

from pydantic import BaseModel, Field


class ScheduledJobOut(BaseModel):
    id: str
    name: str
    interval_minutes: int
    enabled: bool


class ScheduledJobPatch(BaseModel):
    interval_minutes: int | None = None
    enabled: bool | None = None


class JobRunLogEntry(BaseModel):
    job_id: str
    at: str
    ok: bool
    message: str = ""
    duration_ms: float = 0


class AppLogEntry(BaseModel):
    ts: str
    level: str
    logger: str
    message: str
