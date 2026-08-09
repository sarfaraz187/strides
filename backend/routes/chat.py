from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.agent import conversations
from backend.dependencies import require_user
from backend.services.chat_service import process_query
from data.db import get_messages, save_message

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
async def chat(request: ChatRequest, user_id: str = Depends(require_user)):
    messages = conversations.setdefault(user_id, [])
    messages.append({"role": "user", "content": request.message})
    save_message(user_id, "user", request.message)

    reply = await process_query(user_id, messages)
    save_message(user_id, "assistant", reply)

    return {"reply": reply}


@router.get("/chat/history")
def get_chat_history(
    before_id: int | None = None, limit: int = 20, user_id: str = Depends(require_user)
):
    messages, has_more = get_messages(user_id, before_id=before_id, limit=limit)
    return {"messages": messages, "has_more": has_more}