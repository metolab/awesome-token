"""OIDC Authorization Code + PKCE; session cookie for API access."""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt

from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])

PKCE_COOKIE = "oauth_pkce"
STATE_COOKIE = "oauth_state"
SESSION_COOKIE = "session"
RETURN_COOKIE = "oauth_return"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


async def _discover(well_known: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(well_known)
        r.raise_for_status()
        return r.json()


async def _jwks(jwks_uri: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(jwks_uri)
        r.raise_for_status()
        return r.json()


def _display_username_from_claims(claims: dict[str, Any]) -> str:
    for key in ("preferred_username", "name", "nickname"):
        v = claims.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    email = claims.get("email")
    if isinstance(email, str) and "@" in email:
        return email.split("@", 1)[0].strip() or "User"
    sub = str(claims.get("sub", "")).strip()
    if sub:
        return sub[:32] + ("…" if len(sub) > 32 else "")
    return "User"


def _gravatar_url(email: str | None) -> str | None:
    if not email or not isinstance(email, str):
        return None
    em = email.strip().lower()
    if not em:
        return None
    digest = hashlib.md5(em.encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?d=identicon&s=128"


def _issue_session_token(sub: str, email: str | None, username: str | None) -> str:
    settings = get_settings()
    from datetime import datetime, timedelta, timezone

    exp = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {
        "sub": sub,
        "email": email,
        "username": username,
        "exp": exp,
    }
    return jwt.encode(payload, settings.session_secret, algorithm="HS256")


def decode_session_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.session_secret, algorithms=["HS256"])


def _sanitize_return_path(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if not raw.startswith("/") or raw.startswith("//"):
        return None
    return raw[:512]


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    settings = get_settings()
    if not settings.oauth2_well_known_url or not settings.oauth2_client_id:
        raise HTTPException(status_code=500, detail="OAuth2 is not configured")

    meta = await _discover(settings.oauth2_well_known_url)
    auth_ep = meta["authorization_endpoint"]
    token_ep = meta.get("token_endpoint", "")

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)

    params = {
        "client_id": settings.oauth2_client_id,
        "redirect_uri": settings.oauth2_redirect_uri,
        "response_type": "code",
        "scope": settings.oauth2_scope,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = f"{auth_ep}?{urlencode(params)}"

    resp = RedirectResponse(url=url, status_code=302)
    # Short-lived cookies for PKCE/state (10 min)
    resp.set_cookie(
        PKCE_COOKIE,
        verifier,
        httponly=True,
        samesite="lax",
        max_age=600,
        path="/",
    )
    resp.set_cookie(
        STATE_COOKIE,
        state,
        httponly=True,
        samesite="lax",
        max_age=600,
        path="/",
    )
    nxt = _sanitize_return_path(request.query_params.get("next"))
    if nxt:
        resp.set_cookie(
            RETURN_COOKIE,
            nxt,
            httponly=True,
            samesite="lax",
            max_age=600,
            path="/",
        )
    return resp


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    settings = get_settings()
    stored_state = request.cookies.get(STATE_COOKIE)
    verifier = request.cookies.get(PKCE_COOKIE)
    if not stored_state or state != stored_state or not verifier:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    meta = await _discover(settings.oauth2_well_known_url)
    token_ep = meta["token_endpoint"]
    jwks_uri = meta["jwks_uri"]
    issuer = meta.get("issuer")

    async with httpx.AsyncClient(timeout=30.0) as client:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.oauth2_redirect_uri,
            "client_id": settings.oauth2_client_id,
            "code_verifier": verifier,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if settings.oauth2_client_secret:
            data["client_secret"] = settings.oauth2_client_secret

        tr = await client.post(token_ep, data=data, headers=headers)
        if tr.status_code >= 400:
            raise HTTPException(status_code=400, detail=tr.text)
        tokens = tr.json()

    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="No id_token in response")

    # Verify signature via JWKS
    jwks_data = await _jwks(jwks_uri)
    header = jwt.get_unverified_header(id_token)
    kid = header.get("kid")
    key = None
    for k in jwks_data.get("keys", []):
        if kid and k.get("kid") == kid:
            key = k
            break
    if key is None and jwks_data.get("keys"):
        key = jwks_data["keys"][0]

    from jose import jwk

    if key is None:
        raise HTTPException(status_code=400, detail="No signing key in JWKS")

    alg = header.get("alg", "RS256")
    public_key = jwk.construct(key, algorithm=alg)
    pem = public_key.to_pem().decode("utf-8")
    decode_kw: dict[str, Any] = {
        "algorithms": [alg],
        "audience": settings.oauth2_client_id,
        "options": {"verify_aud": True, "verify_at_hash": False},
    }
    if issuer:
        decode_kw["issuer"] = issuer
    try:
        claims = jwt.decode(id_token, pem, **decode_kw)
    except JWTError:
        decode_kw.pop("issuer", None)
        claims = jwt.decode(
            id_token,
            pem,
            algorithms=[alg],
            audience=settings.oauth2_client_id,
            options={"verify_aud": True, "verify_at_hash": False, "verify_iss": False},
        )

    sub = str(claims.get("sub", ""))
    email = claims.get("email")
    if email is not None and not isinstance(email, str):
        email = str(email)
    username = _display_username_from_claims(claims)
    session_jwt = _issue_session_token(sub, email, username)

    settings_fb = get_settings()
    next_path = request.query_params.get("next")
    if not next_path:
        ck = request.cookies.get(RETURN_COOKIE)
        next_path = _sanitize_return_path(ck) or "/"
    else:
        next_path = _sanitize_return_path(next_path) or "/"
    base = settings_fb.resolved_frontend_origin()
    if next_path.startswith("http"):
        target = next_path
    else:
        target = f"{base}{next_path if next_path.startswith('/') else '/' + next_path}"
    resp = RedirectResponse(url=target, status_code=302)
    resp.set_cookie(
        SESSION_COOKIE,
        session_jwt,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/",
    )
    resp.delete_cookie(PKCE_COOKIE, path="/")
    resp.delete_cookie(STATE_COOKIE, path="/")
    resp.delete_cookie(RETURN_COOKIE, path="/")
    return resp


@router.post("/logout")
async def logout() -> Response:
    from fastapi.responses import JSONResponse

    r = JSONResponse({"ok": True})
    r.delete_cookie(SESSION_COOKIE, path="/")
    return r


@router.get("/me")
async def me(request: Request) -> dict[str, Any]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_session_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")
    email = payload.get("email")
    username = payload.get("username")
    if not isinstance(username, str) or not username.strip():
        if isinstance(email, str) and "@" in email:
            username = email.split("@", 1)[0].strip() or "User"
        else:
            sub = str(payload.get("sub", "")).strip()
            username = (sub[:32] + ("…" if len(sub) > 32 else "")) if sub else "User"
    avatar_url = _gravatar_url(email if isinstance(email, str) else None)
    return {
        "sub": payload.get("sub"),
        "email": email,
        "username": username.strip(),
        "avatar_url": avatar_url,
    }
