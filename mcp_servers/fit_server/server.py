import logging
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
from mcp_servers.fit_server.helpers.common import current_user_id
from mcp_servers.fit_server.helpers.formatter import parse_run
from mcp_servers.fit_server.helpers.health_api import get_health_data
from mcp_servers.fit_server.mcp_auth import verify_bearer_token

setup_logging()

BASE_URL = "https://health.googleapis.com"


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
    "strides",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8001)),
    token_verifier=StridesTokenVerifier(),
    auth=AuthSettings(
        issuer_url="http://localhost:8000",
        resource_server_url="http://localhost:8001",
    ),
)


@mcp.tool()
def get_recent_runs(days: int = 7) -> list[dict[str, Any]]:
    """Get the user's runs from the last N days, with distance in km, duration in
    minutes, and pace in min/km already calculated. Use this for relative/recent
    queries like "how did I run this week" or "show my last 30 days" — use
    get_run_stats instead if the user gives explicit calendar dates. Returns a
    list of run dicts (empty list if no runs in the window, not an error).
    days=7 for 'this week', days=30 for 'this month', etc. Default 7 if
    unspecified."""
    user_id = current_user_id()
    health_access_token = get_valid_access_token(user_id)

    now = datetime.now(timezone.utc)
    past = now - timedelta(days=days)

    timestamp = past.strftime("%Y-%m-%dT%H:%M:%S")

    logging.info(f"Fetching runs since: {timestamp}")

    response = get_health_data(
        health_access_token,
        f"{BASE_URL}/v4/users/me/dataTypes/exercise/dataPoints",
        params={"filter": f'exercise.interval.civil_start_time>="{timestamp}"'},
    )

    logging.info(f"Response: {response}")
    if "error" in response:
        return response
    return parse_run(response)


@mcp.tool()
def get_run_stats(start_date: str, end_date: str) -> dict[str, Any]:
    """Get aggregated running statistics (total distance, total duration, average
    pace, run count) between start_date and end_date. Use this when the user
    gives explicit calendar dates (e.g. "how far did I run in January") rather
    than a relative window — get_recent_runs handles relative windows like "last
    7 days". Dates in YYYY-MM-DD format, e.g. 2023-01-01. end_date is exclusive.
    avg_pace_min_per_km is null when total_distance_km is 0 (no runs in range),
    not an error."""
    user_id = current_user_id()
    health_access_token = get_valid_access_token(user_id)

    start_timestamp = f"{start_date}T00:00:00"
    end_timestamp = f"{end_date}T00:00:00"

    response = get_health_data(
        health_access_token,
        f"{BASE_URL}/v4/users/me/dataTypes/exercise/dataPoints",
        params={
            "filter": f'exercise.interval.civil_start_time>="{start_timestamp}" AND exercise.interval.civil_start_time<"{end_timestamp}"'
        },
    )

    logging.info(f"Response: {response}")
    if "error" in response:
        return response
    runs = parse_run(response)

    total_distance_km = sum(run["distance_km"] for run in runs)
    total_duration_min = sum(run["duration_min"] for run in runs)

    return {
        "run_count": len(runs),
        "total_distance_km": round(total_distance_km, 2),
        "total_duration_min": round(total_duration_min, 1),
        "avg_pace_min_per_km": round(total_duration_min / total_distance_km, 2)
        if total_distance_km
        else None,
    }


@mcp.tool()
def get_weekly_stats() -> dict[str, Any]:
    """Get the user's aggregated running statistics for the current week so far
    (Monday through today, inclusive). Equivalent to calling get_run_stats with
    this week's Monday as start_date and tomorrow as end_date — use this
    shortcut instead of computing those dates yourself. Returns the same shape
    as get_run_stats: total distance, total duration, average pace, run count."""
    today = datetime.now(timezone.utc)
    monday = today - timedelta(days=today.weekday())
    end = today + timedelta(
        days=1
    )  # +1 because end_date is exclusive, this makes today included

    start_date = monday.strftime("%Y-%m-%d")
    end_date = end.strftime("%Y-%m-%d")

    return get_run_stats(start_date, end_date)


@mcp.tool()
def calculate(expression: str) -> str:
    """Safely evaluate a basic arithmetic expression (e.g. "5.2 * 7" or
    "(10+3)/2") with no access to builtins or imports — use only for numeric
    math the model shouldn't compute by hand, not for anything involving run
    data (those tools already return computed pace/distance/duration). Returns
    "Invalid expression." for any error (syntax error, division by zero,
    disallowed name) without distinguishing which."""
    try:
        return f"Result: {eval(expression, {'__builtins__': {}})}"
    except Exception:
        return "Invalid expression."


# Running the MCP server
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
