from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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

    _static_root = Path(__file__).resolve().parents[1] / "static"
    _static_root = _static_root.resolve()
    _spa_index = (_static_root / "index.html").resolve()

    # SPA (production image only): Vite output lives in /app/static next to the app package.
    # Serve existing files directly and fall back to index.html for client-side routes like /new-api.
    if _spa_index.is_file():
        reserved_roots = frozenset({"api", "auth", "docs", "redoc", "health"})
        reserved_exact = frozenset({"openapi.json"})

        def _resolve_static_candidate(path: str) -> Path | None:
            candidate = (_static_root / path.lstrip("/")).resolve()
            if candidate == _static_root or _static_root in candidate.parents:
                return candidate
            return None

        def _is_reserved_path(path: str) -> bool:
            normalized = path.strip("/")
            if not normalized:
                return False
            if normalized in reserved_exact or normalized in reserved_roots:
                return True
            head = normalized.split("/", 1)[0]
            return head in reserved_roots

        @app.get("/", include_in_schema=False)
        async def spa_index() -> FileResponse:
            return FileResponse(_spa_index)

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            if _is_reserved_path(full_path):
                raise HTTPException(status_code=404)

            candidate = _resolve_static_candidate(full_path)
            if candidate is None:
                raise HTTPException(status_code=404)

            if candidate.is_file():
                return FileResponse(candidate)
            if candidate.is_dir():
                nested_index = (candidate / "index.html").resolve()
                if nested_index.is_file() and (_static_root in nested_index.parents):
                    return FileResponse(nested_index)

            # Missing asset-like paths should stay 404; route-like paths fall back to the SPA entry.
            if "." in Path(full_path).name:
                raise HTTPException(status_code=404)
            return FileResponse(_spa_index)

    return app


app = create_app()
