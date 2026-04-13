from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query

from app.auth.dependencies import SessionUser
from app.db.store import aliyun_accounts
from app.modules.newapi.sync_service import (
    delete_channel_for_account,
    resolve_newapi_channel_id,
    resolve_newapi_channel_id_map,
)
from app.modules.aliyun.bss_client import fetch_query_bill
from app.modules.aliyun.schemas import (
    AliyunAccountCreate,
    AliyunAccountDetail,
    AliyunAccountPublic,
    AliyunAccountUpdate,
    BillLineRow,
    QueryBillLiveResponse,
)
from app.modules.aliyun.service import (
    detail_from_record,
    extract_query_bill_from_bss_body,
    format_sync_error,
    public_from_record,
    sync_aliyun_account_data,
)

router = APIRouter(prefix="/api/aliyun/accounts", tags=["aliyun"])

_BILLING_CYCLE_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("/", response_model=list[AliyunAccountPublic])
async def list_accounts(_user: SessionUser) -> list[AliyunAccountPublic]:
    col = aliyun_accounts()
    rows = await col.list_items()
    id_map = await resolve_newapi_channel_id_map(rows)
    return [public_from_record(r, newapi_channel_id=id_map.get(r.id)) for r in rows]


@router.post("/", response_model=AliyunAccountPublic)
async def create_account(body: AliyunAccountCreate, _user: SessionUser) -> AliyunAccountPublic:
    col = aliyun_accounts()
    created = await col.create(
        {
            "username": body.username,
            "access_key_id": body.access_key_id,
            "access_key_secret": body.access_key_secret,
            "bailian_api_key": body.bailian_api_key,
            "remark": body.remark,
        }
    )
    try:
        synced = await sync_aliyun_account_data(created)
        await col.update(created.id, synced.model_dump(exclude={"id"}))
        created = synced
    except Exception as e:
        await col.update(created.id, {"last_sync_error": format_sync_error(e)})

    # Sync to new-api channel (best effort)
    try:
        from app.modules.newapi.sync_service import ensure_channel_for_aliyun_account

        await ensure_channel_for_aliyun_account(created)
    except Exception:
        pass

    final = await col.get(created.id)
    assert final is not None
    nid = await resolve_newapi_channel_id(final)
    return public_from_record(final, newapi_channel_id=nid)


@router.get("/{account_id}/bills", response_model=QueryBillLiveResponse)
async def get_account_bills_live(
    account_id: str,
    _user: SessionUser,
    billing_cycle: str = Query(..., description="Billing month YYYY-MM"),
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(50, ge=1, le=300),
) -> QueryBillLiveResponse:
    """Fetch bill lines via BSS QueryBill (real time, not persisted)."""
    if not _BILLING_CYCLE_RE.match(billing_cycle):
        raise HTTPException(status_code=400, detail="billing_cycle must be YYYY-MM")
    col = aliyun_accounts()
    rec = await col.get(account_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        raw = await fetch_query_bill(
            rec.access_key_id,
            rec.access_key_secret,
            billing_cycle=billing_cycle,
            page_num=page,
            page_size=page_size,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BSS QueryBill failed: {e!s}") from e
    if isinstance(raw, dict) and raw.get("Success") is False:
        raise HTTPException(
            status_code=502,
            detail=str(raw.get("Message") or raw.get("Code") or "BSS query failed"),
        )
    rows_plain, meta = extract_query_bill_from_bss_body(raw if isinstance(raw, dict) else None)
    items = [BillLineRow.model_validate(r) for r in rows_plain]
    return QueryBillLiveResponse(
        account_id=rec.id,
        username=rec.username,
        billing_cycle=billing_cycle,
        page_num=meta.get("page_num"),
        page_size=meta.get("page_size"),
        total_count=meta.get("total_count"),
        bss_account_id=meta.get("bss_account_id"),
        bss_account_name=meta.get("account_name"),
        items=items,
        bss_success=meta.get("bss_success"),
        bss_code=meta.get("bss_code"),
        bss_message=meta.get("bss_message"),
        request_id=meta.get("request_id"),
    )


@router.get("/{account_id}", response_model=AliyunAccountDetail)
async def get_account(account_id: str, _user: SessionUser) -> AliyunAccountDetail:
    col = aliyun_accounts()
    rec = await col.get(account_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    nid = await resolve_newapi_channel_id(rec)
    return detail_from_record(rec, newapi_channel_id=nid)


@router.put("/{account_id}", response_model=AliyunAccountPublic)
async def update_account(account_id: str, body: AliyunAccountUpdate, _user: SessionUser) -> AliyunAccountPublic:
    col = aliyun_accounts()
    rec = await col.get(account_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    patch: dict = {}
    if body.username is not None:
        patch["username"] = body.username
    if body.remark is not None:
        patch["remark"] = body.remark
    if body.access_key_id is not None:
        patch["access_key_id"] = body.access_key_id
    if body.access_key_secret is not None:
        patch["access_key_secret"] = body.access_key_secret
    if body.bailian_api_key is not None:
        patch["bailian_api_key"] = body.bailian_api_key
    updated = await col.update(account_id, patch)
    if not updated:
        raise HTTPException(status_code=500, detail="Update failed")
    try:
        from app.modules.newapi.sync_service import ensure_channel_for_aliyun_account

        await ensure_channel_for_aliyun_account(updated)
    except Exception:
        pass
    nid = await resolve_newapi_channel_id(updated)
    return public_from_record(updated, newapi_channel_id=nid)


@router.delete("/{account_id}")
async def delete_account(account_id: str, _user: SessionUser) -> dict[str, bool]:
    col = aliyun_accounts()
    rec = await col.get(account_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await delete_channel_for_account(rec)
    except Exception:
        pass
    ok = await col.delete(account_id)
    return {"ok": ok}


@router.post("/{account_id}/sync", response_model=AliyunAccountPublic)
async def sync_account(account_id: str, _user: SessionUser) -> AliyunAccountPublic:
    col = aliyun_accounts()
    rec = await col.get(account_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        synced = await sync_aliyun_account_data(rec)
        await col.update(account_id, synced.model_dump(exclude={"id"}))
    except Exception as e:
        await col.update(account_id, {"last_sync_error": format_sync_error(e)})
        raise HTTPException(status_code=502, detail=f"BSS sync failed: {e!s}") from e
    final = await col.get(account_id)
    assert final is not None
    nid = await resolve_newapi_channel_id(final)
    return public_from_record(final, newapi_channel_id=nid)
