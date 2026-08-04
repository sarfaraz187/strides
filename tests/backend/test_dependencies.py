import pytest
from fastapi import HTTPException

from backend.dependencies import require_user
from data.db import create_session, find_or_create_user, init_db


@pytest.fixture(autouse=True)
def db():
    init_db()


def test_require_user_returns_user_id_for_valid_session():
    from datetime import datetime, timedelta, timezone

    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=1))

    assert require_user(token) == user_id


def test_require_user_raises_401_for_missing_session():
    with pytest.raises(HTTPException) as exc_info:
        require_user(None)
    assert exc_info.value.status_code == 401


def test_require_user_raises_401_for_invalid_session():
    with pytest.raises(HTTPException) as exc_info:
        require_user("not-a-real-token")
    assert exc_info.value.status_code == 401
