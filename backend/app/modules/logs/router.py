from __future__ import annotations

from fastapi import APIRouter, Query

from app.auth.dependencies import SessionUser
from app.app_file_logging import APP_LOG_MAX_LINES, get_app_logs_from_file
from app.modules.scheduler.schemas import AppLogEntry

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/", response_model=list[AppLogEntry])
async def query_logs(
    _user: SessionUser,
    limit: int = Query(500, ge=1, le=APP_LOG_MAX_LINES),
    level: str | None = Query(None, description="Filter by level, e.g. INFO, WARNING, ERROR"),
) -> list[AppLogEntry]:
    rows = get_app_logs_from_file(limit=limit, level=level)
    return [AppLogEntry.model_validate(x) for x in rows]
