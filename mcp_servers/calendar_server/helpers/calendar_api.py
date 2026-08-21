from datetime import datetime, timedelta

import requests

from data.db import get_calendar_id, save_calendar_id

BASE_URL = "https://www.googleapis.com/calendar/v3"


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def ensure_calendar(access_token: str, user_id: str) -> str:
    """Return the user's dedicated 'Strides Runs' calendar ID, creating it on
    first use."""
    existing = get_calendar_id(user_id)
    if existing is not None:
        return existing

    response = requests.post(
        f"{BASE_URL}/calendars",
        headers=_headers(access_token),
        json={"summary": "Strides Runs"},
    )
    response.raise_for_status()
    calendar_id = response.json()["id"]
    save_calendar_id(user_id, calendar_id)
    return calendar_id


def list_events(
    access_token: str, calendar_id: str, time_min: str, time_max: str
) -> list[dict]:
    response = requests.get(
        f"{BASE_URL}/calendars/{calendar_id}/events",
        headers=_headers(access_token),
        params={
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime",
        },
    )
    response.raise_for_status()
    return response.json().get("items", [])


def create_event(
    access_token: str,
    calendar_id: str,
    title: str,
    start_time: str,
    duration_minutes: int,
    notes: str = "",
) -> dict:
    start = datetime.fromisoformat(start_time)
    end = start + timedelta(minutes=duration_minutes)

    response = requests.post(
        f"{BASE_URL}/calendars/{calendar_id}/events",
        headers=_headers(access_token),
        json={
            "summary": title,
            "description": notes,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        },
    )
    response.raise_for_status()
    return response.json()


def update_event(access_token: str, calendar_id: str, event_id: str, **fields) -> dict:
    response = requests.patch(
        f"{BASE_URL}/calendars/{calendar_id}/events/{event_id}",
        headers=_headers(access_token),
        json=fields,
    )
    response.raise_for_status()
    return response.json()


def delete_event(access_token: str, calendar_id: str, event_id: str) -> None:
    response = requests.delete(
        f"{BASE_URL}/calendars/{calendar_id}/events/{event_id}",
        headers=_headers(access_token),
    )
    response.raise_for_status()