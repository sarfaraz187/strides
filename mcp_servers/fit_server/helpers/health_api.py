import logging

import requests


def get_health_data(
    access_token: str, url: str, params: dict | None = None
) -> dict | str:
    """Make a request to the Google Health API with proper error handling."""
    try:
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
