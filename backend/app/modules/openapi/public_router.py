from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.modules.openapi.schemas import BailianTokenResponse
from app.modules.openapi.service import resolve_best_bailian_token, verify_api_secret

router = APIRouter(prefix="/openapi/v1", tags=["openapi-public"])


def _extract_secret(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    x = request.headers.get("x-api-key")
    if x:
        return x.strip()
    return ""


@router.get("/bailian-token", response_model=BailianTokenResponse)
async def get_bailian_token(request: Request) -> BailianTokenResponse:
    raw = _extract_secret(request)
    if not raw:
        raise HTTPException(
            status_code=401,
            detail="Send Authorization: Bearer <key> or X-Api-Key",
        )
    if await verify_api_secret(raw) is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    resolved = await resolve_best_bailian_token()
    if resolved is None:
        raise HTTPException(
            status_code=503,
            detail="No eligible account with a Bailian API key (same rules as new-api sync).",
        )
    account, token = resolved
    return BailianTokenResponse(
        token=token,
        account_id=account.id,
        username=account.username,
    )
