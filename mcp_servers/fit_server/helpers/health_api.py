import logging
from typing import Any

import requests

_ERROR_INFO_TYPE = "type.googleapis.com/google.rpc.ErrorInfo"


def get_health_data(
    access_token: str, url: str, params: dict | None = None
) -> dict[str, Any]:
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
        return _parse_error(e.response)
    except Exception as e:
        logging.error(f"Health API request failed: {e}")
        return {"error": "REQUEST_FAILED", "message": str(e)}


def _parse_error(response: requests.Response) -> dict[str, Any]:
    try:
        error = response.json()["error"]
        for detail in error.get("details", []):
            if detail.get("@type") == _ERROR_INFO_TYPE:
                result = {"error": detail["reason"], "message": error["message"]}
                redirect_uri = detail.get("metadata", {}).get("redirect_uri")
                if redirect_uri:
                    result["redirect_uri"] = redirect_uri
                return result
        return {
            "error": "UNKNOWN_ERROR",
            "message": error.get("message", "Unknown error"),
        }
    except (ValueError, KeyError):
        return {"error": "UNKNOWN_ERROR", "message": "Health API request failed."}
