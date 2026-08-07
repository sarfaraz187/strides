from fastapi import APIRouter, Depends

from backend.dependencies import require_user
from backend.services.mcp_client import open_mcp_session
from data.db import get_oauth_token

router = APIRouter()


@router.get("/dashboard")
async def dashboard(user_id: str = Depends(require_user)):
    health_connected = get_oauth_token(user_id, "health") is not None
    weekly_stats, recent_runs = None, []

    if health_connected:
        try:
            async with open_mcp_session(user_id) as session:
                weekly_result = await session.call_tool("get_weekly_stats", {})
                recent_result = await session.call_tool("get_recent_runs", {"days": 7})
            weekly_stats = weekly_result.structuredContent
            recent_runs = recent_result.structuredContent["result"]
        except Exception:
            health_connected = False

    return {
        "weekly_stats": weekly_stats,
        "recent_runs": recent_runs,
        "health_connected": health_connected,
    }
