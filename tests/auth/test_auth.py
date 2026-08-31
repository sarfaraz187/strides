import base64
import os
from unittest.mock import patch

import pytest

from auth.auth import get_valid_access_token
from data.db import (
    create_notification,
    find_or_create_user,
    get_oauth_token,
    init_db,
    list_notifications,
    save_oauth_token,
)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv(
        "TOKEN_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    init_db()


def test_returns_stored_token_when_still_valid():
    import time

    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    save_oauth_token(
        user_id, "health", "valid-access", "refresh-1", int(time.time()) + 3600
    )

    assert get_valid_access_token(user_id) == "valid-access"


def test_refreshes_expired_token():
    import time

    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
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


def test_invalid_grant_deletes_token_and_creates_notification():
    import time
    import requests

    user_id = find_or_create_user("[EMAIL]", "google-sub-123", "Runner Example")
    save_oauth_token(
        user_id, "health", "expired-access", "dead-refresh", int(time.time()) - 10
    )

    response = requests.models.Response()
    response.status_code = 400
    response._content = b'{"error": "invalid_grant", "error_description": "Refresh token has been expired or revoked."}'

    with patch("auth.auth.refresh_access_token") as mock_refresh:
        mock_refresh.side_effect = requests.HTTPError(response=response)
        with pytest.raises(requests.HTTPError):
            get_valid_access_token(user_id)

    assert get_oauth_token(user_id, "health") is None
    notifications = list_notifications(user_id)
    assert len(notifications) == 1
    assert notifications[0].type == "health_reauth_required"
    assert notifications[0].action_href == "/connectors"


def test_concurrent_refresh_of_same_dead_token_raises_valueerror_not_httperror():
    # Simulates the dashboard's parallel health+calendar fetch both hitting
    # a dead health token: the first call's transaction (mocked here by
    # calling get_valid_access_token once, which deletes the row) leaves the
    # second call with no row to SELECT ... FOR UPDATE. That's expected and
    # harmless (the second caller's `except Exception` still catches it) —
    # asserted here only so the error shape is documented, not silent.
    import time
    import requests

    user_id = find_or_create_user("[EMAIL]", "google-sub-123", "Runner Example")
    save_oauth_token(
        user_id, "health", "expired-access", "dead-refresh", int(time.time()) - 10
    )

    response = requests.models.Response()
    response.status_code = 400
    response._content = b'{"error": "invalid_grant"}'

    with patch("auth.auth.refresh_access_token") as mock_refresh:
        mock_refresh.side_effect = requests.HTTPError(response=response)
        with pytest.raises(requests.HTTPError):
            get_valid_access_token(user_id)

    with pytest.raises(ValueError):
        get_valid_access_token(user_id)


def test_other_http_errors_do_not_delete_the_token_or_notify():
    import time
    import requests

    user_id = find_or_create_user("[EMAIL]", "google-sub-125", "Runner Example")
    save_oauth_token(
        user_id, "health", "expired-access", "refresh-1", int(time.time()) - 10
    )

    response = requests.models.Response()
    response.status_code = 500
    response._content = b"internal error"

    with patch("auth.auth.refresh_access_token") as mock_refresh:
        mock_refresh.side_effect = requests.HTTPError(response=response)
        with pytest.raises(requests.HTTPError):
            get_valid_access_token(user_id)

    assert get_oauth_token(user_id, "health") is not None
    assert list_notifications(user_id) == []
