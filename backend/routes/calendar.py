from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.dependencies import require_user
from backend.services.mcp_client import CALENDAR_SERVER_URL, open_mcp_session

router = APIRouter(prefix="/calendar")


class PlanRunRequest(BaseModel):
    title: str
    start_time: str
    duration_minutes: int
    notes: str = ""


@router.post("/events")
async def plan_run(body: PlanRunRequest, user_id: str = Depends(require_user)):
    async with open_mcp_session(user_id, server_url=CALENDAR_SERVER_URL) as session:
        result = await session.call_tool(
            "create_run_event",
            {
                "title": body.title,
                "start_time": body.start_time,
                "duration_minutes": body.duration_minutes,
                "notes": body.notes,
            },
        )
    return result.structuredContent