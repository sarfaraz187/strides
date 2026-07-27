import json
import logging
from datetime import datetime, timedelta, timezone

from mcp.server.fastmcp import FastMCP

from src.helpers.health_api import get_health_data
from src.logging_config import setup_logging

setup_logging()

# Both Tool Execution handler and the MCP server in this file
mcp = FastMCP("strides")

EMAIL = "sarfarazflame@gmail.com"
BASE_URL = "https://health.googleapis.com"


@mcp.tool()
def get_runs() -> dict:
    """Fetch the user's recent running activity data."""

    response = get_health_data(f"{BASE_URL}/v4/users/me/dataTypes/exercise/dataPoints")

    logging.info(f"Fetching runs since: {response}")
    return response


@mcp.tool()
def get_recent_runs(days: int = 7) -> list[dict]:
    """Get the user's runs from the last N days. Use days=7 for 'this week',
    days=30 for 'this month', etc. Default 7 if unspecified."""
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=days)

    timestamp = past.strftime("%Y-%m-%dT%H:%M:%SZ")

    logging.info(f"Fetching runs since: {timestamp}")

    response = get_health_data(
        f"{BASE_URL}/v4/users/me/dataTypes/exercise/dataPoints?filter=exercise.interval.start_time>='{timestamp}'"
    )

    logging.info(f"Response status code: {response.status_code}")


@mcp.tool()
def calculate(expression: str) -> str:
    """Safely evaluate a basic math expression."""
    try:
        return f"Result: {eval(expression, {'__builtins__': {}})}"
    except:
        return "Invalid expression."


# Running the MCP server
if __name__ == "__main__":
    mcp.run(transport="stdio")
