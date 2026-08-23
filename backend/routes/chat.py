import json
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import data.db as db
from backend.dependencies import require_user
from backend.services.chat_service import (
    LOCAL_TOOL_SCHEMAS,
    _build_system_prompt,
    process_query,
)
from backend.services.mcp_client import (
    HEALTH_SERVER_URL,
    get_tool_schemas,
    open_mcp_session,
)
from backend.services.summarization_service import maybe_fold

router = APIRouter()

MAX_MESSAGE_CHARS = 500


class ChatRequest(BaseModel):
    message: str


def _unrestricted_emails() -> set[str]:
    # Semicolon-separated, not comma: this value is injected into gcloud's
    # `--set-env-vars`, which itself uses commas to delimit KEY=VALUE pairs —
    # a comma inside the value breaks that syntax (see deploy failure from
    # the first attempt at this).
    raw = os.environ.get("UNRESTRICTED_EMAILS", "")
    return {e.strip() for e in raw.split(";") if e.strip()}


def _token_budget_limit() -> int:
    return int(os.environ.get("TOKEN_BUDGET_LIMIT", "50000"))


@router.post("/chat")
async def chat(request: ChatRequest, user_id: str = Depends(require_user)):
    from backend.agent import SYSTEM_PROMPT

    email, _, _, _ = db.get_user(user_id)
    is_unrestricted = email in _unrestricted_emails()

    if not is_unrestricted and len(request.message) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=400, detail={"error": "message_too_long"})

    if not is_unrestricted and db.get_tokens_used(user_id) >= _token_budget_limit():
        raise HTTPException(status_code=403, detail={"error": "budget_exceeded"})

    db.save_message(user_id, "user", request.message)

    summary = db.get_conversation_summary(user_id)
    cursor = summary["through_message_id"] if summary else 0
    rows = db.get_messages_since(user_id, after_id=cursor)

    system_prompt = _build_system_prompt(SYSTEM_PROMPT, user_id)

    async with open_mcp_session(user_id, server_url=HEALTH_SERVER_URL) as session:
        tools = await get_tool_schemas(session) + LOCAL_TOOL_SCHEMAS

    rows = await maybe_fold(user_id, system_prompt, rows, tools)

    messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    usage: dict = {}

    async def event_stream():
        full_reply = ""
        async for chunk in process_query(user_id, messages, usage=usage):
            full_reply += chunk
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        db.save_message(user_id, "assistant", full_reply)
        if not is_unrestricted:
            total = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            db.increment_tokens_used(user_id, total)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/chat/history")
def get_chat_history(
    before_id: int | None = None, limit: int = 20, user_id: str = Depends(require_user)
):
    messages, has_more = db.get_messages(user_id, before_id=before_id, limit=limit)
    return {"messages": messages, "has_more": has_more}
