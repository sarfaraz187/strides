import os
import urllib.parse

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REDIRECT_URI = "https://www.google.com"
SCOPE = "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly"


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

    print("1. Open this URL, log in, and approve access:\n")
    print(auth_url)
    print("\n2. You'll land on google.com with a broken-looking page — that's fine.")
    print(
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
        print(response.text)
    response.raise_for_status()
    return response.json()


def fetch_activity_data(access_token: str) -> dict:
    response = requests.get(
        "https://health.googleapis.com/v4/users/me/dataTypes/exercise/dataPoints",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if not response.ok:
        print(response.text)
    response.raise_for_status()
    return response.json()


def main() -> None:
    code = get_authorization_code()
    tokens = exchange_code_for_tokens(code)
    access_token = tokens["access_token"]

    print("\nAccess token acquired. Fetching activity data...\n")
    data = fetch_activity_data(access_token)
    print(data)


if __name__ == "__main__":
    main()
