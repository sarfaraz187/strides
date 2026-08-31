import base64
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from data.db import create_notification, create_session, find_or_create_user, init_db


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "TOKEN_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    init_db()


@pytest.fixture
def client():
    from backend.agent import app

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    return TestClient(app)


def _session_cookie_for_new_user(client) -> dict[str, str]:
    user_id = find_or_create_user("[EMAIL]", "google-sub-123", "Runner Example")
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    return {"session": token}, user_id


def test_get_notifications_requires_auth(client):
    response = client.get("/notifications")
    assert response.status_code == 401


def test_get_notifications_returns_unresolved_notifications(client):
    cookies, user_id = _session_cookie_for_new_user(client)
    create_notification(user_id, "health_reauth_required", "/connectors")

    response = client.get("/notifications", cookies=cookies)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["type"] == "health_reauth_required"
    assert body[0]["status"] == "unread"


def test_read_all_marks_notifications_read(client):
    cookies, user_id = _session_cookie_for_new_user(client)
    create_notification(user_id, "health_reauth_required", "/connectors")

    response = client.patch("/notifications/read-all", cookies=cookies)
    assert response.status_code == 200

    listed = client.get("/notifications", cookies=cookies).json()
    assert listed[0]["status"] == "read"