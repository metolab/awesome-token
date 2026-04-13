from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from repo root (parent of `backend/`) and cwd — see `app/config.py` under `backend/app/`
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_REPO_ROOT / ".env"),
            str(_REPO_ROOT / "backend" / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    session_secret: str = "dev-change-me"
    cors_origins: str = "http://localhost:5173"

    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""
    oauth2_well_known_url: str = ""
    oauth2_redirect_uri: str = "http://localhost:5173/auth/callback"
    oauth2_scope: str = "openid email profile"
    frontend_origin: str = "http://localhost:5173"

    data_dir: str = "data"

    # Relative to backend/ unless absolute. Rotating file for API /api/logs tail read.
    app_log_file: str = "logs/app.log"
    app_log_max_bytes: int = 10 * 1024 * 1024
    app_log_backup_count: int = 3

    aliyun_sync_interval_minutes: int = 30
    newapi_sync_interval_minutes: int = 15

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolved_frontend_origin(self) -> str:
        """SPA origin for post-login redirect; prefer explicit frontend_origin, else derive from OAUTH2_REDIRECT_URI."""
        explicit = (self.frontend_origin or "").strip().rstrip("/")
        if explicit and explicit != "http://localhost:5173":
            return explicit
        ru = urlparse((self.oauth2_redirect_uri or "").strip())
        if ru.scheme and ru.netloc:
            return f"{ru.scheme}://{ru.netloc}".rstrip("/")
        return explicit or "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
