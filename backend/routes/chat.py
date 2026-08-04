from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.agent import conversations
from backend.dependencies import require_user
from backend.services.chat_service import process_query

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
async def chat(request: ChatRequest, user_id: str = Depends(require_user)):
    messages = conversations.setdefault(user_id, [])
    messages.append({"role": "user", "content": request.message})

    reply = await process_query(user_id, messages)

    return {"reply": reply}
