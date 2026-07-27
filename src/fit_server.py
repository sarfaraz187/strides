import json
import sys
import requests
from datetime import datetime, timedelta, timezone
from mcp.server.fastmcp import FastMCP
from src.auth import get_valid_access_token

mcp = FastMCP("strides")
EMAIL = "sarfarazflame@gmail.com"


@mcp.tool()
def get_runs() -> dict:
    """Fetch the user's recent running activity data."""
    access_token = get_valid_access_token(EMAIL)

    response = requests.get(
        "https://health.googleapis.com/v4/users/me/dataTypes/exercise/dataPoints",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if not response.ok:
        print(response.text)
    response.raise_for_status()

    data = response.json()
    print(json.dumps(data, indent=2), file=sys.stderr)

    return data


@mcp.tool()
def get_recent_runs(days: int = 7) -> list[dict]:
    """Get the user's runs from the last N days. Use days=7 for 'this week',
    days=30 for 'this month', etc. Default 7 if unspecified."""
    access_token = get_valid_access_token(EMAIL)

    now = datetime.now(timezone.utc)
    past = now - timedelta(days=days)

    timestamp = past.strftime("%Y-%m-%dT%H:%M:%SZ")
    print(timestamp)
    response = requests.get(
        f"https://health.googleapis.com/v4/users/me/dataTypes/exercise/dataPoints?filter=exercise.interval.start_time>='{timestamp}'",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    print("Status :", response.status_code)


@mcp.tool()
def calculate(expression: str) -> str:
    """Safely evaluate a basic math expression."""
    try:
        return f"Result: {eval(expression, {'__builtins__': {}})}"
    except:
        return "Invalid expression."


if __name__ == "__main__":
    mcp.run()
