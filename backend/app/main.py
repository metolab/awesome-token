from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth.oauth2 import router as oauth_router
from app.config import get_settings
from app.app_file_logging import install_app_file_logging
from app.modules.aliyun.router import router as aliyun_router
from app.modules.logs.router import router as logs_router
from app.modules.newapi.router import router as newapi_router
from app.modules.openapi.public_router import router as openapi_public_router
from app.modules.openapi.router import router as openapi_admin_router
from app.modules.scheduler.service import apply_all_scheduled_jobs
from app.modules.scheduler.router import router as scheduler_router
from app.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    install_app_file_logging()
    start_scheduler()
    await apply_all_scheduled_jobs()
    yield
    shutdown_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="awesome-token", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(oauth_router)
    app.include_router(aliyun_router)
    app.include_router(newapi_router)
    app.include_router(scheduler_router)
    app.include_router(logs_router)
    app.include_router(openapi_admin_router)
    app.include_router(openapi_public_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # SPA (production image only): Vite output lives in /app/static next to the app package.
    # Mount last so /api, /auth, /docs, /openapi.json keep precedence over the catch-all.
    _static_root = Path(__file__).resolve().parents[1] / "static"
    if (_static_root / "index.html").is_file():
        app.mount(
            "/",
            StaticFiles(directory=str(_static_root), html=True),
            name="spa",
        )

    return app


app = create_app()
