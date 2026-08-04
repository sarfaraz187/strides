import logging
import os
import time

import requests
from dotenv import load_dotenv

from backend.encryption import decrypt, encrypt
from data.db import get_connection
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
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT access_token, refresh_token, expires_at
            FROM oauth_tokens WHERE user_id = %s AND provider = %s
            FOR UPDATE
            """,
            (user_id, "health"),
        ).fetchone()

        if row is None:
            raise ValueError(
                f"No Health token for user {user_id}; user must complete "
                "/auth/health/connect first"
            )

        access_token, refresh_token, expires_at = row

        if expires_at > time.time():
            return decrypt(access_token)

        response = refresh_access_token(decrypt(refresh_token))
        new_expires_at = int(time.time()) + response["expires_in"]

        conn.execute(
            """
            UPDATE oauth_tokens SET access_token = %s, expires_at = %s
            WHERE user_id = %s AND provider = %s
            """,
            (encrypt(response["access_token"]), new_expires_at, user_id, "health"),
        )
        conn.commit()
        return response["access_token"]
