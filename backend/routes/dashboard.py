from fastapi import APIRouter, Depends

from backend.dependencies import require_user
from backend.services.mcp_client import open_mcp_session

router = APIRouter()


@router.get("/dashboard")
async def dashboard(user_id: str = Depends(require_user)):
    async with open_mcp_session(user_id) as session:
        weekly_result = await session.call_tool("get_weekly_stats", {})
        recent_result = await session.call_tool("get_recent_runs", {"days": 7})

    return {
        "weekly_stats": weekly_result.structuredContent,
        "recent_runs": recent_result.structuredContent["result"],
    }
