import os
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from auth.auth import get_valid_access_token
from logging_config import setup_logging
from mcp_servers.calendar_server.helpers.calendar_api import (
    create_event,
    delete_event,
    ensure_calendar,
    list_events,
    update_event,
)
from mcp_servers.calendar_server.helpers.common import current_user_id
from mcp_servers.calendar_server.mcp_auth import verify_bearer_token

setup_logging()


class StridesTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            user_id = verify_bearer_token(token)
        except Exception:
            return None
        return AccessToken(
            token=token, client_id="strides-backend", scopes=[], subject=user_id
        )


mcp = FastMCP(
    "strides-calendar",
    host="127.0.0.1",
    port=int(os.environ.get("PORT", 8002)),
    token_verifier=StridesTokenVerifier(),
    auth=AuthSettings(
        issuer_url="http://localhost:8000",
        resource_server_url="http://localhost:8002",
    ),
)


@mcp.tool()
def list_upcoming_runs(days_ahead: int = 7) -> list[dict[str, Any]]:
    """List planned runs from the user's dedicated 'Strides Runs' Google Calendar
    for the next N days (default 7). Returns raw Calendar event dicts (empty list
    if none scheduled, not an error)."""
    user_id = current_user_id()
    access_token = get_valid_access_token(user_id, provider="calendar")
    calendar_id = ensure_calendar(access_token, user_id)

    now = datetime.now(timezone.utc)
    time_min = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_max = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ")

    return list_events(access_token, calendar_id, time_min, time_max)


@mcp.tool()
def create_run_event(
    title: str, start_time: str, duration_minutes: int, notes: str = ""
) -> dict[str, Any]:
    """Create a planned run on the user's dedicated 'Strides Runs' Google Calendar.
    Only call this after the user has explicitly confirmed a proposed plan — never
    schedule proactively without confirmation. start_time is an ISO 8601 local
    datetime, e.g. '2026-08-25T07:00:00'."""
    user_id = current_user_id()
    access_token = get_valid_access_token(user_id, provider="calendar")
    calendar_id = ensure_calendar(access_token, user_id)

    return create_event(
        access_token, calendar_id, title, start_time, duration_minutes, notes
    )


@mcp.tool()
def update_run_event(event_id: str, **fields: Any) -> dict[str, Any]:
    """Update a planned run (e.g. reschedule) on the user's dedicated Calendar.
    fields are any Google Calendar event fields to patch, e.g. summary, start, end."""
    user_id = current_user_id()
    access_token = get_valid_access_token(user_id, provider="calendar")
    calendar_id = ensure_calendar(access_token, user_id)

    return update_event(access_token, calendar_id, event_id, **fields)


@mcp.tool()
def delete_run_event(event_id: str) -> dict[str, str]:
    """Cancel a planned run by deleting its Calendar event."""
    user_id = current_user_id()
    access_token = get_valid_access_token(user_id, provider="calendar")
    calendar_id = ensure_calendar(access_token, user_id)

    delete_event(access_token, calendar_id, event_id)
    return {"status": "deleted"}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
