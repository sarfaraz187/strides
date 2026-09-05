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
TITLE_MAX_CHARS = 60


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


def _unrestricted_emails() -> set[str]:
    # Semicolon-separated, not comma: this value is injected into gcloud's
    # `--set-env-vars`, which itself uses commas to delimit KEY=VALUE pairs —
    # a comma inside the value breaks that syntax (see deploy failure from
    # the first attempt at this).
    raw = os.environ.get("UNRESTRICTED_EMAILS", "")
    return {e.strip() for e in raw.split(";") if e.strip()}


def _token_budget_limit() -> int:
    return int(os.environ.get("TOKEN_BUDGET_LIMIT", "50000"))


def _title_from_message(message: str) -> str:
    stripped = message.strip()
    if len(stripped) <= TITLE_MAX_CHARS:
        return stripped
    return stripped[:TITLE_MAX_CHARS].rstrip() + "…"


@router.post("/chat")
async def chat(request: ChatRequest, user_id: str = Depends(require_user)):
    from backend.agent import SYSTEM_PROMPT

    email, _, _, _ = db.get_user(user_id)
    is_unrestricted = email in _unrestricted_emails()

    if not is_unrestricted and len(request.message) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=400, detail={"error": "message_too_long"})

    if not is_unrestricted and db.get_tokens_used(user_id) >= _token_budget_limit():
        raise HTTPException(status_code=403, detail={"error": "budget_exceeded"})

    conversation_id = request.conversation_id
    if conversation_id is None:
        conversation_id = db.create_conversation(
            user_id, _title_from_message(request.message)
        )
    elif db.get_conversation(conversation_id, user_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.save_message(conversation_id, "user", request.message)

    summary = db.get_conversation_summary(conversation_id)
    cursor = summary["through_message_id"] if summary else 0
    rows = db.get_messages_since(conversation_id, after_id=cursor)

    system_prompt = _build_system_prompt(SYSTEM_PROMPT, user_id, conversation_id)

    async with open_mcp_session(user_id, server_url=HEALTH_SERVER_URL) as session:
        tools = await get_tool_schemas(session) + LOCAL_TOOL_SCHEMAS

    rows = await maybe_fold(conversation_id, system_prompt, rows, tools)

    messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    usage: dict = {}

    async def event_stream():
        yield f"data: {json.dumps({'conversation_id': conversation_id})}\n\n"
        full_reply = ""
        async for chunk in process_query(user_id, conversation_id, messages, usage=usage):
            full_reply += chunk
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        db.save_message(conversation_id, "assistant", full_reply)
        if not is_unrestricted:
            total = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            db.increment_tokens_used(user_id, total)

    return StreamingResponse(event_stream(), media_type="text/event-stream")