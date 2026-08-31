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


def get_valid_access_token(user_id: str, provider: str = "health") -> str:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT access_token, refresh_token, expires_at
            FROM oauth_tokens WHERE user_id = %s AND provider = %s
            FOR UPDATE
            """,
            (user_id, provider),
        ).fetchone()

        if row is None:
            raise ValueError(
                f"No {provider} token for user {user_id}; user must complete "
                f"/auth/{provider}/connect first"
            )

        access_token, refresh_token, expires_at = row

        if expires_at > time.time():
            return decrypt(access_token)

        try:
            response = refresh_access_token(decrypt(refresh_token))
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else ""
            if exc.response is not None and exc.response.status_code == 400 and "invalid_grant" in body:
                # Deliberately NOT calling data.db's delete_oauth_token /
                # create_notification here — those open their own pooled
                # connection, which would block trying to touch this same
                # row while this connection's FOR UPDATE lock is still held
                # (only released when this `with` block exits). Do both
                # writes on `conn` instead, in the same transaction.
                conn.execute(
                    "DELETE FROM oauth_tokens WHERE user_id = %s AND provider = %s",
                    (user_id, provider),
                )
                conn.execute(
                    """
                    INSERT INTO notifications (user_id, type, action_href)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, type) WHERE status != 'resolved' DO NOTHING
                    """,
                    (user_id, f"{provider}_reauth_required", "/connectors"),
                )
                conn.commit()
            raise

        new_expires_at = int(time.time()) + response["expires_in"]

        conn.execute(
            """
            UPDATE oauth_tokens SET access_token = %s, expires_at = %s
            WHERE user_id = %s AND provider = %s
            """,
            (encrypt(response["access_token"]), new_expires_at, user_id, provider),
        )
        conn.commit()
        return response["access_token"]
