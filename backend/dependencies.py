from fastapi import Cookie, HTTPException

from data.db import get_session_user_id


def require_user(session: str | None = Cookie(default=None)) -> str:
    if session is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = get_session_user_id(session)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session expired")
    return user_id
