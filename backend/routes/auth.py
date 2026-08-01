import os
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, Cookie, HTTPException
from fastapi.responses import RedirectResponse

from data.db import create_session, delete_session, find_or_create_user

router = APIRouter(prefix="/auth")

CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
CALLBACK_URL = os.environ.get(
    "GOOGLE_LOGIN_CALLBACK_URL", "http://localhost:8000/auth/callback"
)
IDENTITY_SCOPE = "openid email profile"
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
SESSION_DURATION = timedelta(days=7)


@router.get("/login")
def login():
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": CALLBACK_URL,
        "response_type": "code",
        "scope": IDENTITY_SCOPE,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        params
    )
    return RedirectResponse(auth_url)


def exchange_code_for_identity_tokens(code: str) -> dict:
    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": CALLBACK_URL,
            "grant_type": "authorization_code",
        },
    )
    token_response.raise_for_status()
    id_token_jwt = token_response.json()["id_token"]

    userinfo_response = requests.get(
        "https://www.googleapis.com/oauth2/v3/tokeninfo",
        params={"id_token": id_token_jwt},
    )
    userinfo_response.raise_for_status()
    payload = userinfo_response.json()

    return {"email": payload["email"], "google_sub": payload["sub"]}


@router.get("/callback")
def callback(code: str):
    identity = exchange_code_for_identity_tokens(code)
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
