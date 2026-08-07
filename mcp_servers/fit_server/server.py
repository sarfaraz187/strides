import logging
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
    host="127.0.0.1",
    port=8001,
    token_verifier=StridesTokenVerifier(),
    auth=AuthSettings(
        issuer_url="http://localhost:8000",
        resource_server_url="http://localhost:8001",
    ),
)


@mcp.tool()
def get_runs() -> dict[str, Any]:
    """Fetch the user's raw recent running activity data (unconverted units)."""
    user_id = current_user_id()
    health_access_token = get_valid_access_token(user_id)

    response = get_health_data(
        health_access_token, f"{BASE_URL}/v4/users/me/dataTypes/exercise/dataPoints"
    )

    logging.info(f"Fetching runs since: {response}")
    return response


@mcp.tool()
def get_recent_runs(days: int = 7) -> list[dict[str, Any]]:
    """Get the user's runs from the last N days, with distance in km, duration in
    minutes, and pace in min/km already calculated. Use days=7 for 'this week',
    days=30 for 'this month', etc. Default 7 if unspecified."""
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
    pace, run count) between start_date and end_date. Dates in YYYY-MM-DD format,
    e.g. 2023-01-01. end_date is exclusive."""
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
    """Get the user's aggregated running statistics for the current week (Monday
    through today). Returns total distance, total duration, average pace, and
    run count."""
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
    """Safely evaluate a basic math expression."""
    try:
        return f"Result: {eval(expression, {'__builtins__': {}})}"
    except:
        return "Invalid expression."


# Running the MCP server
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
