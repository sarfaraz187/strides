import logging
import os

import requests
from dotenv import load_dotenv

from auth.auth import get_valid_access_token

load_dotenv()

EMAIL = os.environ["USER_EMAIL"]


def get_health_data(url: str, params: dict | None = None) -> dict | str:
    """Make a request to the Google Health API with proper error handling."""
    try:
        access_token = get_valid_access_token(EMAIL)
        response = requests.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        logging.error(f"Health API request failed: {e} — {e.response.text}")
        return "Error fetching health data. Please check your credentials and network connection."
    except Exception as e:
        logging.error(f"Health API request failed: {e}")
        return "Error fetching health data. Please check your credentials and network connection."
