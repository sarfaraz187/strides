import base64
import os
from unittest.mock import patch

import pytest

from auth.auth import get_valid_access_token
from data.db import find_or_create_user, init_db, save_oauth_token


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv(
        "TOKEN_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    init_db()


def test_returns_stored_token_when_still_valid():
    import time

    user_id = find_or_create_user("runner@example.com", "google-sub-123")
    save_oauth_token(
        user_id, "health", "valid-access", "refresh-1", int(time.time()) + 3600
    )

    assert get_valid_access_token(user_id) == "valid-access"


def test_refreshes_expired_token():
    import time

    user_id = find_or_create_user("runner@example.com", "google-sub-123")
    save_oauth_token(
        user_id, "health", "expired-access", "refresh-1", int(time.time()) - 10
    )

    with patch("auth.auth.refresh_access_token") as mock_refresh:
        mock_refresh.return_value = {
            "access_token": "new-access",
            "expires_in": 3600,
        }
        result = get_valid_access_token(user_id)

    assert result == "new-access"
