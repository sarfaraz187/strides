from fastapi import APIRouter, Depends
from pydantic import BaseModel

import data.db as db
from backend.dependencies import require_user
from backend.services.chat_service import (
    LOCAL_TOOL_SCHEMAS,
    _build_system_prompt,
    process_query,
)
from backend.services.mcp_client import get_tool_schemas, open_mcp_session
from backend.services.summarization_service import maybe_fold

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
async def chat(request: ChatRequest, user_id: str = Depends(require_user)):
    from backend.agent import SYSTEM_PROMPT

    db.save_message(user_id, "user", request.message)

    summary = db.get_conversation_summary(user_id)
    cursor = summary["through_message_id"] if summary else 0
    rows = db.get_messages_since(user_id, after_id=cursor)

    system_prompt = _build_system_prompt(SYSTEM_PROMPT, user_id)

    async with open_mcp_session(user_id) as session:
        tools = await get_tool_schemas(session) + LOCAL_TOOL_SCHEMAS

    rows = await maybe_fold(user_id, system_prompt, rows, tools)

    messages = [{"role": r["role"], "content": r["content"]} for r in rows]
    reply = await process_query(user_id, messages)
    db.save_message(user_id, "assistant", reply)

    return {"reply": reply}


@router.get("/chat/history")
def get_chat_history(
    before_id: int | None = None, limit: int = 20, user_id: str = Depends(require_user)
):
    messages, has_more = db.get_messages(user_id, before_id=before_id, limit=limit)
    return {"messages": messages, "has_more": has_more}
