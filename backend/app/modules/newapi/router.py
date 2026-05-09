from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.auth.dependencies import SessionUser
from app.db.store import aliyun_accounts
from app.modules.newapi.matching import match_all_channel_rows_for_account
from app.modules.newapi.schemas import ChannelDetailResponse, ChannelRow, NewApiConfigIn, NewApiConfigOut
from app.modules.newapi.sync_service import (
    fetch_all_channels,
    get_optional_client,
    get_or_create_config,
    save_config,
    sync_all_channels,
)

router = APIRouter(prefix="/api/newapi", tags=["newapi"])


def _mask_token(t: str) -> str:
    if len(t) <= 8:
        return "***"
    return t[:4] + "…" + t[-4:]


@router.get("/config", response_model=NewApiConfigOut)
async def get_cfg(_user: SessionUser) -> NewApiConfigOut:
    cfg = await get_or_create_config()
    out = NewApiConfigOut.model_validate(cfg.model_dump())
    if out.admin_token:
        out.admin_token = _mask_token(cfg.admin_token)
    return out


@router.put("/config", response_model=NewApiConfigOut)
async def put_cfg(body: NewApiConfigIn, _user: SessionUser) -> NewApiConfigOut:
    current = await get_or_create_config()
    patch = body.model_dump(exclude_unset=True)
    at = patch.get("admin_token") or ""
    if not at.strip() or "…" in at or at.startswith("***"):
        patch.pop("admin_token", None)
    updated = await save_config({**patch, "id": current.id})
    out = NewApiConfigOut.model_validate(updated.model_dump())
    if out.admin_token:
        out.admin_token = _mask_token(updated.admin_token)
    return out


@router.get("/channels", response_model=list[ChannelRow])
async def list_channels(_user: SessionUser) -> list[ChannelRow]:
    cfg = await get_or_create_config()
    client = get_optional_client(cfg)
    col = aliyun_accounts()
    accounts = await col.list_items()

    if client is None:
        return []

    channel_rows = await fetch_all_channels(client)
    out: list[ChannelRow] = []
    for acc in accounts:
        for tpl_idx, found in match_all_channel_rows_for_account(channel_rows, acc):
            if found.get("id") is None:
                continue
            try:
                cid = int(found["id"])
            except (TypeError, ValueError):
                continue
            try:
                raw = await client.get_channel(cid)
                data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
                if not isinstance(data, dict):
                    data = {}
                out.append(
                    ChannelRow(
                        id=int(data.get("id", cid)),
                        name=data.get("name"),
                        type=data.get("type"),
                        status=data.get("status"),
                        priority=data.get("priority"),
                        models=data.get("models"),
                        group=data.get("group"),
                        aliyun_account_id=acc.id,
                        template_index=tpl_idx,
                    )
                )
            except Exception:
                out.append(
                    ChannelRow(
                        id=cid,
                        name=found.get("name") or acc.username,
                        aliyun_account_id=acc.id,
                        template_index=tpl_idx,
                    )
                )
    return out


@router.get("/channels/{channel_id}/detail", response_model=ChannelDetailResponse)
async def get_channel_detail(channel_id: int, _user: SessionUser) -> ChannelDetailResponse:
    """Fetch current channel settings from new-api admin API (full response body)."""
    cfg = await get_or_create_config()
    client = get_optional_client(cfg)
    if client is None:
        raise HTTPException(status_code=400, detail="new-api not configured")
    try:
        body = await client.get_channel(channel_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    if not isinstance(body, dict):
        raise HTTPException(status_code=502, detail="Unexpected response from new-api")
    return ChannelDetailResponse(channel_id=channel_id, body=body)


@router.post("/sync")
async def sync(_user: SessionUser) -> dict[str, bool]:
    await sync_all_channels()
    return {"ok": True}
