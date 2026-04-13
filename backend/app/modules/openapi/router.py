from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.auth.dependencies import SessionUser
from app.db.store import openapi_keys
from app.modules.openapi.schemas import (
    OpenApiKeyCreate,
    OpenApiKeyCreated,
    OpenApiKeyListItem,
)
from app.modules.openapi.service import generate_api_secret, hash_api_secret, key_prefix_from_secret

router = APIRouter(prefix="/api/openapi", tags=["openapi"])


@router.get("/keys", response_model=list[OpenApiKeyListItem])
async def list_keys(_user: SessionUser) -> list[OpenApiKeyListItem]:
    col = openapi_keys()
    rows = await col.list_items()
    return [
        OpenApiKeyListItem(
            id=r.id,
            label=r.label,
            key_prefix=r.key_prefix,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/keys", response_model=OpenApiKeyCreated)
async def create_key(body: OpenApiKeyCreate, _user: SessionUser) -> OpenApiKeyCreated:
    secret = generate_api_secret()
    prefix = key_prefix_from_secret(secret)
    col = openapi_keys()
    created = await col.create(
        {
            "label": (body.label or "").strip()[:200],
            "key_hash": hash_api_secret(secret),
            "key_prefix": prefix,
        },
    )
    return OpenApiKeyCreated(
        id=created.id,
        label=created.label,
        key_prefix=created.key_prefix,
        secret=secret,
        created_at=created.created_at,
    )


@router.delete("/keys/{key_id}")
async def delete_key(key_id: str, _user: SessionUser) -> dict[str, bool]:
    col = openapi_keys()
    ok = await col.delete(key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}
