import os
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, HTTPException
from fastapi.responses import RedirectResponse
from backend.jwt_issuer import get_jwks

from backend.services import auth_service
from data.db import (
    create_session,
    delete_oauth_token,
    delete_session,
    find_or_create_user,
    get_session_user_id,
    save_oauth_token,
)

router = APIRouter(prefix="/auth")

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
SESSION_DURATION = timedelta(days=7)


@router.get("/login")
def login():
    return RedirectResponse(auth_service.build_login_url())


@router.get("/callback")
def callback(code: str):
    identity = auth_service.exchange_code_for_identity_tokens(code)
    user_id = find_or_create_user(identity["email"], identity["google_sub"])

    expires_at = datetime.now(timezone.utc) + SESSION_DURATION
    session_token = create_session(user_id, expires_at)

    response = RedirectResponse(FRONTEND_URL)
    response.set_cookie(
        "session",
        session_token,
        httponly=True,
        expires=int(SESSION_DURATION.total_seconds()),
    )
    return response


@router.post("/logout")
def logout(session: str | None = Cookie(default=None)):
    if session is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    delete_session(session)
    response = RedirectResponse(FRONTEND_URL, status_code=200)
    response.delete_cookie("session")
    return response


def _require_user_id(session: str | None) -> str:
    if session is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = get_session_user_id(session)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session expired")
    return user_id


@router.get("/health/connect")
def health_connect(session: str | None = Cookie(default=None)):
    _require_user_id(session)
    return RedirectResponse(auth_service.build_health_connect_url())


@router.get("/health/callback")
def health_callback(code: str, session: str | None = Cookie(default=None)):
    user_id = _require_user_id(session)
    tokens = auth_service.exchange_code_for_health_tokens(code)
    expires_at = int(time.time()) + tokens["expires_in"]

    save_oauth_token(
        user_id, "health", tokens["access_token"], tokens["refresh_token"], expires_at
    )
    return RedirectResponse(FRONTEND_URL)


@router.post("/health/disconnect")
def health_disconnect(session: str | None = Cookie(default=None)):
    user_id = _require_user_id(session)
    delete_oauth_token(user_id, "health")
    return {"status": "disconnected"}


@router.get("/.well-known/jwks.json")
def jwks():
    return get_jwks()
