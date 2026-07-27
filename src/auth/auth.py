import json
import logging
import os
import time
import urllib.parse

import requests
from dotenv import load_dotenv

from data.db import get_token, save_token
from src.logging_config import setup_logging

load_dotenv()
setup_logging()


CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REDIRECT_URI = "https://www.google.com"
SCOPE = "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly"


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


def get_authorization_code() -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        params
    )

    logging.info("1. Open this URL, log in, and approve access:\n")
    logging.info(auth_url)
    logging.info(
        "\n2. You'll land on google.com with a broken-looking page — that's fine."
    )
    logging.info(
        "   Copy the 'code' value from the address bar (after code= and before &scope)."
    )

    return input("\nPaste the code here: ").strip()


def exchange_code_for_tokens(code: str) -> dict:
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
    )
    if not response.ok:
        logging.error(response.text)
    response.raise_for_status()
    return response.json()


def get_valid_access_token(email):
    dbResponse = get_token(email)

    # logging.info(f"DB Response: {dbResponse}")
    # Token doesn't exist
    if dbResponse is None:
        logging.info("We have no token with this user. creating a new OAuth flow")
        code = get_authorization_code()
        response = exchange_code_for_tokens(code)

        logging.info(json.dumps(response, indent=2))
        expires_at = int(time.time()) + response["expires_in"]

        save_token(
            email,
            response["access_token"],
            response["refresh_token"],
            expires_at,
        )

        return response["access_token"]

    access_token, refresh_token, expires_at = dbResponse

    logging.info(access_token)
    # Token still valid
    if expires_at > time.time():
        return access_token

    # Token has expired
    else:
        try:
            response = refresh_access_token(refresh_token)
        except requests.HTTPError:
            logging.info("Refresh token expired/revoked — starting new OAuth flow")
            code = get_authorization_code()
            response = exchange_code_for_tokens(code)
            expires_at = int(time.time()) + response["expires_in"]
            save_token(
                email, response["access_token"], response["refresh_token"], expires_at
            )
            return response["access_token"]

        expires_at = int(time.time()) + response["expires_in"]
        save_token(email, response["access_token"], refresh_token, expires_at)
        return response["access_token"]


if __name__ == "__main__":
    get_valid_access_token("sarfarazflame@gmail.com")
