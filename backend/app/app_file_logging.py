"""Application log file output and tail-read for the logs API."""

from __future__ import annotations

import logging
import logging.handlers
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATEFMT = "%Y-%m-%dT%H:%M:%S"
APP_LOG_MAX_LINES = 2000

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_HANDLER_INSTALLED = False

# Matches lines emitted by our Formatter (single-line messages).
_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}) \| "
    r"(DEBUG|INFO|WARNING|ERROR|CRITICAL) \| "
    r"([^|]+?) \| (.*)$"
)


def resolved_app_log_path() -> Path:
    s = get_settings()
    p = Path(s.app_log_file.strip())
    if p.is_absolute():
        return p
    return _BACKEND_DIR / p


def _has_rotating_handler_for_path(root: logging.Logger, target: Path) -> bool:
    try:
        want = target.resolve()
    except OSError:
        want = target
    for h in root.handlers:
        if isinstance(h, logging.handlers.RotatingFileHandler):
            try:
                if Path(h.baseFilename).resolve() == want:
                    return True
            except OSError:
                continue
    return False


def install_app_file_logging() -> None:
    """Write app + propagated logs to a rotating file; lower root level so INFO is recorded."""
    global _HANDLER_INSTALLED
    settings = get_settings()
    path = resolved_app_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)
    logging.getLogger("app").setLevel(logging.INFO)

    if not _has_rotating_handler_for_path(root, path):
        h = logging.handlers.RotatingFileHandler(
            path,
            maxBytes=max(1, settings.app_log_max_bytes),
            backupCount=max(0, settings.app_log_backup_count),
            encoding="utf-8",
        )
        h.setLevel(logging.DEBUG)
        h.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATEFMT))
        root.addHandler(h)

    log = logging.getLogger("app")
    if not _HANDLER_INSTALLED:
        log.info("Application file logging initialized at %s", path)
    _HANDLER_INSTALLED = True


def _parse_line(line: str) -> dict[str, Any]:
    s = line.strip()
    if not s:
        return {}
    m = _LOG_LINE_RE.match(s)
    if m:
        ts_raw, level, logger, message = m.groups()
        return {
            "ts": ts_raw,
            "level": level,
            "logger": logger.strip(),
            "message": f"{ts_raw} | {level} | {logger.strip()} | {message}",
        }
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": "INFO",
        "logger": "logfile",
        "message": s,
    }


def _read_tail_text(path: Path, max_bytes: int) -> tuple[str, bool]:
    """Return (text, started_mid_line). If started_mid_line, drop first line after split."""
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        if size == 0:
            return "", False
        if size <= max_bytes:
            f.seek(0)
            return f.read().decode("utf-8", errors="replace"), False
        f.seek(size - max_bytes)
        raw = f.read().decode("utf-8", errors="replace")
        return raw, True


def get_app_logs_from_file(
    *,
    limit: int = 500,
    level: str | None = None,
) -> list[dict[str, Any]]:
    """Newest entries first. Reads the tail of the active log file only (not rotated backups)."""
    path = resolved_app_log_path()
    if not path.is_file():
        return []

    cap = max(1, min(limit, APP_LOG_MAX_LINES))
    # Overscan: level filter may drop many lines.
    overscan = min(APP_LOG_MAX_LINES, max(cap * 4, 500))
    max_bytes = min(8 * 1024 * 1024, max(overscan * 400, 256_000))

    text, mid = _read_tail_text(path, max_bytes)
    lines = text.splitlines()
    if mid and lines:
        lines = lines[1:]

    want_level = level.upper().strip() if level else None
    out: list[dict[str, Any]] = []
    for line in reversed(lines):
        entry = _parse_line(line)
        if not entry:
            continue
        if want_level and entry.get("level") != want_level:
            continue
        out.append(entry)
        if len(out) >= cap:
            break
    return out
