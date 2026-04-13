from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.db.engine import DatabaseManager
from app.db.models import (
    AliyunAccountRecord,
    NewApiConfigRecord,
    OpenApiKeyRecord,
    ScheduledJobRecord,
)

_db: DatabaseManager | None = None


def get_db() -> DatabaseManager:
    global _db
    if _db is None:
        settings = get_settings()
        _db = DatabaseManager(Path(settings.data_dir))
    return _db


def aliyun_accounts():
    return get_db().collection("aliyun_accounts", AliyunAccountRecord)


def newapi_config():
    return get_db().collection("newapi_config", NewApiConfigRecord)


def scheduled_jobs():
    return get_db().collection("scheduled_jobs", ScheduledJobRecord)


def openapi_keys():
    return get_db().collection("openapi_keys", OpenApiKeyRecord)
