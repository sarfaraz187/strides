import logging
from datetime import datetime, timedelta

import requests

from data.db import get_calendar_id, save_calendar_id

logger = logging.getLogger(__name__)

BASE_URL = "https://www.googleapis.com/calendar/v3"


def _raise_for_status(response: requests.Response) -> None:
    if not response.ok:
        logger.error(
            "Google Calendar API error: %s %s -> %s %s",
            response.request.method,
            response.request.url,
            response.status_code,
            response.text,
        )
    response.raise_for_status()


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def get_account_timezone(access_token: str) -> str:
    """Return the IANA time zone (e.g. 'Europe/Berlin') the user's Google
    account is set to, per their Calendar settings."""
    response = requests.get(
        f"{BASE_URL}/users/me/settings/timezone",
        headers=_headers(access_token),
    )
    _raise_for_status(response)
    return response.json()["value"]


def find_existing_calendar(access_token: str) -> str | None:
    """Look up the user's Google account directly for a calendar named
    'Strides', in case the local cache is stale (e.g. wiped by a reauth
    cycle) while the calendar itself still exists."""
    response = requests.get(
        f"{BASE_URL}/users/me/calendarList",
        headers=_headers(access_token),
    )
    _raise_for_status(response)
    for item in response.json().get("items", []):
        if item.get("summary") == "Strides":
            return item["id"]
    return None


def ensure_calendar(access_token: str, user_id: str) -> str:
    """Return the user's dedicated 'Strides' calendar ID, creating it on
    first use. A newly created calendar is stamped with the account's own
    time zone, since Google otherwise defaults it to UTC."""
    existing = get_calendar_id(user_id)
    if existing is not None:
        return existing

    calendar_id = find_existing_calendar(access_token)
    if calendar_id is None:
        time_zone = get_account_timezone(access_token)
        response = requests.post(
            f"{BASE_URL}/calendars",
            headers=_headers(access_token),
            json={"summary": "Strides", "timeZone": time_zone},
        )
        _raise_for_status(response)
        calendar_id = response.json()["id"]

    save_calendar_id(user_id, calendar_id)
    return calendar_id


def get_calendar_timezone(access_token: str, calendar_id: str) -> str:
    """Return the IANA time zone (e.g. 'America/Los_Angeles') the calendar is
    set to, inherited from the Google account's Calendar settings."""
    response = requests.get(
        f"{BASE_URL}/calendars/{calendar_id}",
        headers=_headers(access_token),
    )
    _raise_for_status(response)
    return response.json()["timeZone"]


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
    _raise_for_status(response)
    return response.json().get("items", [])


def create_event(
    access_token: str,
    calendar_id: str,
    title: str,
    start_time: str,
    duration_minutes: int,
    time_zone: str,
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
            "start": {"dateTime": start.isoformat(), "timeZone": time_zone},
            "end": {"dateTime": end.isoformat(), "timeZone": time_zone},
        },
    )
    _raise_for_status(response)
    return response.json()


def update_event(access_token: str, calendar_id: str, event_id: str, **fields) -> dict:
    response = requests.patch(
        f"{BASE_URL}/calendars/{calendar_id}/events/{event_id}",
        headers=_headers(access_token),
        json=fields,
    )
    _raise_for_status(response)
    return response.json()


def delete_event(access_token: str, calendar_id: str, event_id: str) -> None:
    response = requests.delete(
        f"{BASE_URL}/calendars/{calendar_id}/events/{event_id}",
        headers=_headers(access_token),
    )
    _raise_for_status(response)
