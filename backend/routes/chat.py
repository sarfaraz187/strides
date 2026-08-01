from fastapi import APIRouter
from pydantic import BaseModel

from backend.agent import app_state
from backend.services.chat_service import process_query

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
async def chat(request: ChatRequest):
    app_state["messages"].append({"role": "user", "content": request.message})

    reply = await process_query(
        app_state["session"], app_state["tools"], app_state["messages"]
    )

    return {"reply": reply}
