import logging
import os
import time

import requests
from dotenv import load_dotenv

from data.db import get_oauth_token, save_oauth_token
from logging_config import setup_logging

load_dotenv()
setup_logging()


CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]


def refresh_access_token(refresh_token: str) -> dict:
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )

    if not response.ok:
        logging.error(response.text)
    response.raise_for_status()

    return response.json()


def get_valid_access_token(user_id: str) -> str:
    token_row = get_oauth_token(user_id, "health")

    if token_row is None:
        raise ValueError(
            f"No Health token for user {user_id}; user must complete "
            "/auth/health/connect first"
        )

    access_token, refresh_token, expires_at = token_row

    if expires_at > time.time():
        return access_token

    response = refresh_access_token(refresh_token)
    new_expires_at = int(time.time()) + response["expires_in"]
    save_oauth_token(
        user_id, "health", response["access_token"], refresh_token, new_expires_at
    )
    return response["access_token"]
