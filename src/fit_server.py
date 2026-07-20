import requests
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

    return response.json()


if __name__ == "__main__":
    mcp.run()
