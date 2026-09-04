import base64
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from data.db import (
    create_session,
    find_or_create_user,
    get_connection,
    get_user,
    init_db,
)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "TOKEN_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    init_db()
    yield
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM users WHERE email = %s", ("avatar-route@example.com",)
        )
        conn.commit()


@pytest.fixture
def client():
    from backend.agent import app

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    return TestClient(app)


def _session_cookie(client) -> str:
    user_id = find_or_create_user(
        "avatar-route@example.com", "avatar-route-sub", "Avatar Route"
    )
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    client.cookies.set("session", token)
    return user_id


def test_upload_avatar_requires_auth(client):
    response = client.post(
        "/profile/avatar", files={"file": ("pic.jpg", b"fake-bytes", "image/jpeg")}
    )
    assert response.status_code == 401


def test_upload_avatar_rejects_wrong_content_type(client):
    _session_cookie(client)
    response = client.post(
        "/profile/avatar",
        files={"file": ("pic.gif", b"fake-bytes", "image/gif")},
    )
    assert response.status_code == 400


def test_upload_avatar_rejects_oversized_file(client):
    _session_cookie(client)
    oversized = b"x" * (5 * 1024 * 1024 + 1)
    response = client.post(
        "/profile/avatar",
        files={"file": ("pic.jpg", oversized, "image/jpeg")},
    )
    assert response.status_code == 400


def test_upload_avatar_stores_path_and_returns_signed_url(client):
    user_id = _session_cookie(client)

    with (
        patch("backend.routes.profile.upload_avatar") as mock_upload,
        patch("backend.routes.profile.create_signed_url") as mock_sign,
    ):
        mock_upload.return_value = f"{user_id}.jpg"
        mock_sign.return_value = "https://project-ref.supabase.co/storage/v1/object/sign/avatars/x.jpg?token=abc"
        response = client.post(
            "/profile/avatar",
            files={"file": ("pic.jpg", b"fake-bytes", "image/jpeg")},
        )

    assert response.status_code == 200
    assert response.json()["avatar_url"] == (
        "https://project-ref.supabase.co/storage/v1/object/sign/avatars/x.jpg?token=abc"
    )
    _, _, _, stored_path = get_user(user_id)
    assert stored_path == f"{user_id}.jpg"


def test_upload_avatar_deletes_prior_file_when_replacing(client):
    _session_cookie(client)

    with (
        patch("backend.routes.profile.upload_avatar") as mock_upload,
        patch("backend.routes.profile.create_signed_url"),
        patch("backend.routes.profile.delete_avatar") as mock_delete,
    ):
        mock_upload.return_value = "first.jpg"
        client.post(
            "/profile/avatar",
            files={"file": ("pic.jpg", b"first-bytes", "image/jpeg")},
        )

        mock_upload.return_value = "second.jpg"
        client.post(
            "/profile/avatar",
            files={"file": ("pic.jpg", b"second-bytes", "image/jpeg")},
        )

    mock_delete.assert_called_once_with("first.jpg")
