from __future__ import annotations

from typing import Annotated, Any

from fastapi import Cookie, Depends, HTTPException, Request

from app.auth.oauth2 import SESSION_COOKIE, decode_session_token


async def require_session(
    request: Request,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict[str, Any]:
    token = session or request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return decode_session_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")


SessionUser = Annotated[dict[str, Any], Depends(require_session)]
