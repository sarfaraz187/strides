import base64
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from data.db import (
    create_conversation,
    create_session,
    find_or_create_user,
    init_db,
    save_message,
)


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


def _session_cookie_for_new_user(client, email="runner@example.com") -> str:
    user_id = find_or_create_user(email, f"google-sub-{email}", "Runner Example")
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    client.cookies.set("session", token)
    return user_id


def test_list_conversations_requires_auth(client):
    response = client.get("/conversations")
    assert response.status_code == 401


def test_list_conversations_returns_users_conversations(client):
    user_id = _session_cookie_for_new_user(client)
    create_conversation(user_id, "Marathon taper plan")

    response = client.get("/conversations")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["title"] == "Marathon taper plan"


def test_list_conversations_filters_by_search(client):
    user_id = _session_cookie_for_new_user(client)
    create_conversation(user_id, "Marathon taper plan")
    create_conversation(user_id, "Shin pain advice")

    response = client.get("/conversations?search=shin")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["title"] == "Shin pain advice"


def test_get_conversation_messages_returns_404_for_other_users_conversation(client):
    user_id = _session_cookie_for_new_user(client, "owner@example.com")
    conversation_id = create_conversation(user_id, "Private chat")
    _session_cookie_for_new_user(client, "intruder@example.com")

    response = client.get(f"/conversations/{conversation_id}/messages")

    assert response.status_code == 404


def test_get_conversation_messages_returns_messages(client):
    user_id = _session_cookie_for_new_user(client)
    conversation_id = create_conversation(user_id, "New chat")
    save_message(conversation_id, "user", "hi")

    response = client.get(f"/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    body = response.json()
    assert [m["content"] for m in body["messages"]] == ["hi"]


def test_patch_conversation_renames_it(client):
    user_id = _session_cookie_for_new_user(client)
    conversation_id = create_conversation(user_id, "New chat")

    response = client.patch(
        f"/conversations/{conversation_id}", json={"title": "Renamed"}
    )

    assert response.status_code == 200
    assert client.get("/conversations").json()[0]["title"] == "Renamed"


def test_patch_conversation_rejects_empty_title(client):
    user_id = _session_cookie_for_new_user(client)
    conversation_id = create_conversation(user_id, "New chat")

    response = client.patch(f"/conversations/{conversation_id}", json={"title": "   "})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "empty_title"


def test_patch_conversation_pins_it(client):
    user_id = _session_cookie_for_new_user(client)
    conversation_id = create_conversation(user_id, "New chat")

    response = client.patch(f"/conversations/{conversation_id}", json={"pinned": True})

    assert response.status_code == 200
    assert client.get("/conversations").json()[0]["pinned"] is True


def test_patch_conversation_returns_404_for_other_users_conversation(client):
    user_id = _session_cookie_for_new_user(client, "owner@example.com")
    conversation_id = create_conversation(user_id, "Private chat")
    _session_cookie_for_new_user(client, "intruder@example.com")

    response = client.patch(
        f"/conversations/{conversation_id}", json={"title": "Hijacked"}
    )

    assert response.status_code == 404


def test_delete_conversation_removes_it(client):
    user_id = _session_cookie_for_new_user(client)
    conversation_id = create_conversation(user_id, "New chat")

    response = client.delete(f"/conversations/{conversation_id}")

    assert response.status_code == 200
    assert client.get("/conversations").json() == []


def test_delete_conversation_returns_404_for_other_users_conversation(client):
    user_id = _session_cookie_for_new_user(client, "owner@example.com")
    conversation_id = create_conversation(user_id, "Private chat")
    _session_cookie_for_new_user(client, "intruder@example.com")

    response = client.delete(f"/conversations/{conversation_id}")

    assert response.status_code == 404