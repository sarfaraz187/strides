import base64
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from data.db import create_session, find_or_create_user, get_connection, init_db


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "TOKEN_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    init_db()
    yield
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE email = %s", ("runner@example.com",))
        conn.commit()


@pytest.fixture
def client(monkeypatch):
    from backend.agent import app
    from backend.routes import chat as chat_route

    monkeypatch.setattr(chat_route, "process_query", AsyncMock(return_value="mocked reply"))

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    return TestClient(app)


def _session_cookie_for_new_user(client) -> dict[str, str]:
    from datetime import datetime, timedelta, timezone

    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    return {"session": token}


def test_post_chat_requires_auth(client):
    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 401


def test_post_chat_persists_user_and_assistant_messages(client):
    cookies = _session_cookie_for_new_user(client)

    response = client.post("/chat", json={"message": "hi"}, cookies=cookies)
    assert response.status_code == 200
    assert response.json() == {"reply": "mocked reply"}

    history = client.get("/chat/history", cookies=cookies)
    contents = [m["content"] for m in history.json()["messages"]]
    assert contents == ["mocked reply", "hi"]


def test_get_chat_history_requires_auth(client):
    response = client.get("/chat/history")
    assert response.status_code == 401


def test_get_chat_history_paginates(client):
    cookies = _session_cookie_for_new_user(client)
    for i in range(3):
        client.post("/chat", json={"message": f"message {i}"}, cookies=cookies)

    first_page = client.get("/chat/history?limit=2", cookies=cookies).json()
    assert len(first_page["messages"]) == 2
    assert first_page["has_more"] is True

    oldest_id_on_first_page = first_page["messages"][-1]["id"]
    second_page = client.get(
        f"/chat/history?before_id={oldest_id_on_first_page}&limit=2", cookies=cookies
    ).json()
    assert second_page["has_more"] is True
