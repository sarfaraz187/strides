import os
import urllib.parse

import requests

CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
CALLBACK_URL = os.environ.get(
    "GOOGLE_LOGIN_CALLBACK_URL", "http://localhost:8000/auth/callback"
)
IDENTITY_SCOPE = "openid email profile"

HEALTH_SCOPE = (
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly"
)
HEALTH_CALLBACK_URL = os.environ.get(
    "GOOGLE_HEALTH_CALLBACK_URL", "http://localhost:8000/auth/health/callback"
)


def build_login_url() -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": CALLBACK_URL,
        "response_type": "code",
        "scope": IDENTITY_SCOPE,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        params
    )


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

    user_info_response = requests.get(
        "https://www.googleapis.com/oauth2/v3/tokeninfo",
        params={"id_token": id_token_jwt},
    )
    user_info_response.raise_for_status()
    payload = user_info_response.json()

    return {"email": payload["email"], "google_sub": payload["sub"]}


def build_health_connect_url() -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": HEALTH_CALLBACK_URL,
        "response_type": "code",
        "scope": HEALTH_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        params
    )


def exchange_code_for_health_tokens(code: str) -> dict:
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": HEALTH_CALLBACK_URL,
            "grant_type": "authorization_code",
        },
    )
    response.raise_for_status()
    return response.json()
