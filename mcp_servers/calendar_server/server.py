import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP

from auth.auth import get_valid_access_token
from logging_config import setup_logging
from mcp_servers.calendar_server.helpers.calendar_api import (
    create_event,
    delete_event,
    ensure_calendar,
    get_calendar_timezone,
    list_events,
    update_event,
)
from mcp_servers.calendar_server.helpers.common import current_user_id
from mcp_servers.calendar_server.mcp_auth import verify_bearer_token
from observability.otel_setup import extract_context, setup_tracing

setup_logging()
tracer = setup_tracing("strides-calendar-server")

logger = logging.getLogger(__name__)


def _parent_context_from(ctx: Context):
    """`ctx.request_context.request` is typed Optional and is genuinely None
    outside an HTTP-transported request (e.g. stdio transport, or a tool
    called directly with no live request) — guard it rather than assume it's
    always populated."""
    request = ctx.request_context.request
    if request is None:
        return None
    headers = dict(request.headers)
    return extract_context(headers)


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
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8002)),
    token_verifier=StridesTokenVerifier(),
    auth=AuthSettings(
        issuer_url="http://localhost:8000",
        resource_server_url="http://localhost:8002",
    ),
)


@mcp.tool()
def list_upcoming_runs(
    days_ahead: int = 7, ctx: Context = None
) -> list[dict[str, Any]]:
    """List planned runs from the user's dedicated 'Strides' Google Calendar
    for the next N days (default 7). Returns raw Calendar event dicts (empty list
    if none scheduled, not an error)."""
    parent = _parent_context_from(ctx) if ctx is not None else None
    with tracer.start_as_current_span(
        "mcp.tool.list_upcoming_runs", context=parent
    ) as span:
        user_id = current_user_id()
        span.set_attribute("user_id", user_id)
        access_token = get_valid_access_token(user_id, provider="calendar")
        calendar_id = ensure_calendar(access_token, user_id)

        now = datetime.now(timezone.utc)
        time_min = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        time_max = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ")

        return list_events(access_token, calendar_id, time_min, time_max)


@mcp.tool()
def create_run_event(
    title: str,
    start_time: str,
    duration_minutes: int,
    notes: str = "",
    ctx: Context = None,
) -> dict[str, Any]:
    """Create a planned run on the user's dedicated 'Strides' Google Calendar.
    Only call this after the user has explicitly confirmed a proposed plan — never
    schedule proactively without confirmation. start_time is an ISO 8601 local
    datetime, e.g. '2026-08-25T07:00:00'."""
    parent = _parent_context_from(ctx) if ctx is not None else None
    with tracer.start_as_current_span(
        "mcp.tool.create_run_event", context=parent
    ) as span:
        user_id = current_user_id()
        span.set_attribute("user_id", user_id)
        logger.info(
            "create_run_event: user=%s title=%r start=%s", user_id, title, start_time
        )

        try:
            access_token = get_valid_access_token(user_id, provider="calendar")
            calendar_id = ensure_calendar(access_token, user_id)
            time_zone = get_calendar_timezone(access_token, calendar_id)
            event = create_event(
                access_token,
                calendar_id,
                title,
                start_time,
                duration_minutes,
                time_zone,
                notes,
            )
        except Exception:
            logger.exception(
                "create_run_event failed: user=%s title=%r", user_id, title
            )
            raise

        logger.info(
            "create_run_event: user=%s created event id=%s", user_id, event.get("id")
        )
        return event


@mcp.tool()
def update_run_event(
    event_id: str, fields: dict[str, Any], ctx: Context = None
) -> dict[str, Any]:
    """Update a planned run (e.g. reschedule) on the user's dedicated Calendar.
    fields are any Google Calendar event fields to patch, e.g. summary, start, end."""
    parent = _parent_context_from(ctx) if ctx is not None else None
    with tracer.start_as_current_span(
        "mcp.tool.update_run_event", context=parent
    ) as span:
        user_id = current_user_id()
        span.set_attribute("user_id", user_id)
        span.set_attribute("event_id", event_id)
        access_token = get_valid_access_token(user_id, provider="calendar")
        calendar_id = ensure_calendar(access_token, user_id)

        return update_event(access_token, calendar_id, event_id, **fields)


@mcp.tool()
def delete_run_event(event_id: str, ctx: Context = None) -> dict[str, str]:
    """Cancel a planned run by deleting its Calendar event."""
    parent = _parent_context_from(ctx) if ctx is not None else None
    with tracer.start_as_current_span(
        "mcp.tool.delete_run_event", context=parent
    ) as span:
        user_id = current_user_id()
        span.set_attribute("user_id", user_id)
        span.set_attribute("event_id", event_id)
        access_token = get_valid_access_token(user_id, provider="calendar")
        calendar_id = ensure_calendar(access_token, user_id)

        delete_event(access_token, calendar_id, event_id)
        return {"status": "deleted"}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
