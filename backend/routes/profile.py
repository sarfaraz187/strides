from fastapi import APIRouter, Depends, HTTPException, UploadFile

from backend.dependencies import require_user
from backend.storage import create_signed_url, delete_avatar, upload_avatar
from data.db import get_user, update_avatar_path

router = APIRouter(prefix="/profile")

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
_MAX_SIZE_BYTES = 5 * 1024 * 1024


@router.post("/avatar")
async def upload_avatar_route(
    file: UploadFile, user_id: str = Depends(require_user)
):
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Must be a JPEG or PNG image")

    content = await file.read()
    if len(content) > _MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File must be 5MB or smaller")

    _, _, _, existing_avatar_path = get_user(user_id)

    new_path = upload_avatar(user_id, content, file.content_type)

    if existing_avatar_path is not None:
        delete_avatar(existing_avatar_path)

    update_avatar_path(user_id, new_path)
    return {"avatar_url": create_signed_url(new_path)}
