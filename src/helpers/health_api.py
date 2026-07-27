import requests

from src.auth.auth import get_valid_access_token

EMAIL = "sarfarazflame@gmail.com"


def get_health_data(url: str) -> dict | None:
    """Make a request to the Google Health API with proper error handling."""
    try:
        access_token = get_valid_access_token(EMAIL)
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        response.raise_for_status()
        return response.json()
    except Exception:
        return None
