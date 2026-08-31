from fastapi import APIRouter, Depends

from backend.dependencies import require_user
from data.db import list_notifications, mark_all_read

router = APIRouter(prefix="/notifications")


@router.get("")
def get_notifications(user_id: str = Depends(require_user)):
    return list_notifications(user_id)


@router.patch("/read-all")
def read_all_notifications(user_id: str = Depends(require_user)):
    mark_all_read(user_id)
    return {"status": "ok"}