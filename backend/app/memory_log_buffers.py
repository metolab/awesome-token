"""In-memory ring buffer for scheduled job run history (UI: scheduler page)."""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

JOB_RUN_LOG_MAX = 20

_lock = threading.Lock()
_job_run_logs: deque[dict[str, Any]] = deque(maxlen=JOB_RUN_LOG_MAX)


def append_job_run(
    *,
    job_id: str,
    ok: bool,
    message: str,
    duration_ms: float,
) -> None:
    entry = {
        "job_id": job_id,
        "at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "message": message[:2000] if message else "",
        "duration_ms": round(duration_ms, 2),
    }
    with _lock:
        _job_run_logs.append(entry)


def get_job_run_logs() -> list[dict[str, Any]]:
    """Newest job runs last in deque — return newest first."""
    with _lock:
        items = list(_job_run_logs)
    return list(reversed(items))
