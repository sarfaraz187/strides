from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.dependencies import require_user
from data.db import (
    EmptyTitleError,
    delete_conversation,
    get_conversation,
    get_messages,
    list_conversations,
    rename_conversation,
    set_pinned,
)

router = APIRouter(prefix="/conversations")


class ConversationUpdateRequest(BaseModel):
    title: str | None = None
    pinned: bool | None = None


def _require_owned_conversation(conversation_id: str, user_id: str) -> None:
    if get_conversation(conversation_id, user_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("")
def list_conversations_route(
    search: str | None = None, user_id: str = Depends(require_user)
):
    return list_conversations(user_id, search=search)


@router.get("/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: str,
    before_id: int | None = None,
    limit: int = 20,
    user_id: str = Depends(require_user),
):
    _require_owned_conversation(conversation_id, user_id)
    messages, has_more = get_messages(conversation_id, before_id=before_id, limit=limit)
    return {"messages": messages, "has_more": has_more}


@router.patch("/{conversation_id}")
def update_conversation_route(
    conversation_id: str,
    request: ConversationUpdateRequest,
    user_id: str = Depends(require_user),
):
    _require_owned_conversation(conversation_id, user_id)
    if request.title is not None:
        try:
            rename_conversation(conversation_id, user_id, request.title)
        except EmptyTitleError:
            raise HTTPException(status_code=400, detail={"error": "empty_title"})
    if request.pinned is not None:
        set_pinned(conversation_id, user_id, request.pinned)
    return {"status": "ok"}


@router.delete("/{conversation_id}")
def delete_conversation_route(
    conversation_id: str, user_id: str = Depends(require_user)
):
    _require_owned_conversation(conversation_id, user_id)
    delete_conversation(conversation_id, user_id)
    return {"status": "ok"}
