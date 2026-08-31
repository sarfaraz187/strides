import os
import time
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, Cookie, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse

from backend.services import auth_service
from backend.storage import create_signed_url
from data.db import (
    create_session,
    delete_oauth_token,
    delete_session,
    find_or_create_user,
    get_oauth_token,
    get_session_user_id,
    get_user,
    resolve_notification,
    save_oauth_token,
)

router = APIRouter(prefix="/auth")

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000/en/connectors")
SESSION_DURATION = timedelta(days=7)
IS_PROD = FRONTEND_URL.startswith("https://")


@router.get("/login")
def login():
    return RedirectResponse(auth_service.build_login_url())


@router.get("/callback")
def callback(code: str):
    identity = auth_service.exchange_code_for_identity_tokens(code)
    user_id = find_or_create_user(
        identity["email"], identity["google_sub"], identity["name"]
    )

    expires_at = datetime.now(timezone.utc) + SESSION_DURATION
    session_token = create_session(user_id, expires_at)

    response = RedirectResponse(FRONTEND_URL)
    response.set_cookie(
        "session",
        session_token,
        httponly=True,
        secure=IS_PROD,
        samesite="none" if IS_PROD else "lax",
        expires=int(SESSION_DURATION.total_seconds()),
    )
    return response


@router.post("/logout")
def logout(session: str | None = Cookie(default=None)):
    if session is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    delete_session(session)
    response = JSONResponse({"success": True})
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
def health_callback(
    code: str | None = None,
    error: str | None = None,
    session: str | None = Cookie(default=None),
):
    user_id = _require_user_id(session)
    if error is not None:
        return RedirectResponse(f"{FRONTEND_URL}?health_connect_error=1")
    try:
        tokens = auth_service.exchange_code_for_health_tokens(code)
    except requests.HTTPError:
        return RedirectResponse(f"{FRONTEND_URL}?health_connect_error=1")

    expires_at = int(time.time()) + tokens["expires_in"]

    save_oauth_token(
        user_id,
        "health",
        tokens["access_token"],
        tokens["refresh_token"],
        expires_at,
    )
    resolve_notification(user_id, "health_reauth_required")
    return RedirectResponse(FRONTEND_URL)


@router.post("/health/disconnect")
def health_disconnect(session: str | None = Cookie(default=None)):
    user_id = _require_user_id(session)
    delete_oauth_token(user_id, "health")
    return {"status": "disconnected"}


@router.get("/calendar/connect")
def calendar_connect(session: str | None = Cookie(default=None)):
    _require_user_id(session)
    return RedirectResponse(auth_service.build_calendar_connect_url())


@router.get("/calendar/callback")
def calendar_callback(
    code: str | None = None,
    error: str | None = None,
    session: str | None = Cookie(default=None),
):
    user_id = _require_user_id(session)
    if error is not None:
        return RedirectResponse(f"{FRONTEND_URL}?calendar_connect_error=1")
    try:
        tokens = auth_service.exchange_code_for_calendar_tokens(code)
    except requests.HTTPError:
        return RedirectResponse(f"{FRONTEND_URL}?calendar_connect_error=1")

    expires_at = int(time.time()) + tokens["expires_in"]

    save_oauth_token(
        user_id,
        "calendar",
        tokens["access_token"],
        tokens["refresh_token"],
        expires_at,
    )
    resolve_notification(user_id, "calendar_reauth_required")
    return RedirectResponse(FRONTEND_URL)


@router.post("/calendar/disconnect")
def calendar_disconnect(session: str | None = Cookie(default=None)):
    user_id = _require_user_id(session)
    delete_oauth_token(user_id, "calendar")
    return {"status": "disconnected"}


@router.get("/me")
def me(session: str | None = Cookie(default=None)):
    user_id = _require_user_id(session)
    email, name, created_at, avatar_path = get_user(user_id)
    health_token = get_oauth_token(user_id, "health")
    calendar_token = get_oauth_token(user_id, "calendar")

    avatar_url = create_signed_url(avatar_path) if avatar_path is not None else None
    return {
        "email": email,
        "name": name,
        "created_at": created_at,
        "avatar_url": avatar_url,
        "health_connected": health_token is not None,
        "calendar_connected": calendar_token is not None,
    }
