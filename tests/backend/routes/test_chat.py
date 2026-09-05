import base64
import json
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from data.db import (
    create_conversation,
    create_session,
    find_or_create_user,
    get_connection,
    init_db,
)


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

    async def fake_process_query(user_id, conversation_id, messages, usage=None):
        for chunk in ["mocked ", "reply"]:
            yield chunk

    monkeypatch.setattr(chat_route, "process_query", fake_process_query)

    async def fake_maybe_fold(conversation_id, system_prompt, rows, tools):
        return rows

    monkeypatch.setattr(chat_route, "maybe_fold", fake_maybe_fold)

    @asynccontextmanager
    async def fake_open_mcp_session(user_id, server_url):
        yield None

    monkeypatch.setattr(chat_route, "open_mcp_session", fake_open_mcp_session)
    monkeypatch.setattr(chat_route, "get_tool_schemas", AsyncMock(return_value=[]))

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    return TestClient(app)


def _session_cookie_for_new_user(client) -> str:
    from datetime import datetime, timedelta, timezone

    user_id = find_or_create_user(
        "runner@example.com", "google-sub-123", "Runner Example"
    )
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    client.cookies.set("session", token)
    return user_id


def _collect_sse_events(response) -> list[dict]:
    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


def _collect_sse_text(response) -> str:
    return "".join(e["text"] for e in _collect_sse_events(response) if "text" in e)


def test_post_chat_requires_auth(client):
    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 401


def test_post_chat_without_conversation_id_creates_a_new_conversation(client):
    _session_cookie_for_new_user(client)

    response = client.post("/chat", json={"message": "Marathon taper plan question"})

    assert response.status_code == 200
    events = _collect_sse_events(response)
    conversation_id = events[0]["conversation_id"]
    assert conversation_id

    conversations = client.get("/conversations").json()
    assert conversations[0]["id"] == conversation_id
    assert conversations[0]["title"] == "Marathon taper plan question"


def test_post_chat_truncates_long_first_message_into_title(client):
    _session_cookie_for_new_user(client)

    long_message = "x" * 80
    response = client.post("/chat", json={"message": long_message})

    conversation_id = _collect_sse_events(response)[0]["conversation_id"]
    conversations = client.get("/conversations").json()
    assert conversations[0]["id"] == conversation_id
    assert conversations[0]["title"] == ("x" * 60) + "…"


def test_post_chat_with_conversation_id_reuses_existing_conversation(client):
    user_id = _session_cookie_for_new_user(client)
    conversation_id = create_conversation(user_id, "Existing chat")

    response = client.post(
        "/chat", json={"message": "hi", "conversation_id": conversation_id}
    )

    assert response.status_code == 200
    assert _collect_sse_events(response)[0]["conversation_id"] == conversation_id

    history = client.get(f"/conversations/{conversation_id}/messages").json()
    contents = [m["content"] for m in history["messages"]]
    assert contents == ["mocked reply", "hi"]


def test_post_chat_returns_404_for_nonexistent_conversation_id(client):
    _session_cookie_for_new_user(client)

    response = client.post(
        "/chat",
        json={
            "message": "hi",
            "conversation_id": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert response.status_code == 404


def test_post_chat_calls_maybe_fold_with_rows_since_last_summary(client, monkeypatch):
    from backend.routes import chat as chat_route

    fold_mock = AsyncMock(
        side_effect=lambda conversation_id, system_prompt, rows, tools: rows
    )
    monkeypatch.setattr(chat_route, "maybe_fold", fold_mock)

    _session_cookie_for_new_user(client)
    response = client.post("/chat", json={"message": "hi"})

    assert response.status_code == 200
    fold_mock.assert_awaited_once()
    call_args = fold_mock.await_args
    rows_arg = call_args.args[2]
    assert [r["content"] for r in rows_arg] == ["hi"]


def test_chat_history_is_isolated_per_conversation(client):
    _session_cookie_for_new_user(client)

    first = client.post("/chat", json={"message": "first chat message"})
    first_id = _collect_sse_events(first)[0]["conversation_id"]

    second = client.post("/chat", json={"message": "second chat message"})
    second_id = _collect_sse_events(second)[0]["conversation_id"]

    assert first_id != second_id
    first_history = client.get(f"/conversations/{first_id}/messages").json()
    second_history = client.get(f"/conversations/{second_id}/messages").json()
    assert [m["content"] for m in first_history["messages"]] == [
        "mocked reply",
        "first chat message",
    ]
    assert [m["content"] for m in second_history["messages"]] == [
        "mocked reply",
        "second chat message",
    ]


def test_post_chat_rejects_message_over_500_chars(client):
    _session_cookie_for_new_user(client)
    response = client.post("/chat", json={"message": "x" * 501})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "message_too_long"


def test_post_chat_rejects_when_budget_exceeded(client, monkeypatch):
    monkeypatch.setenv("TOKEN_BUDGET_LIMIT", "1000")
    _session_cookie_for_new_user(client)

    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET tokens_used = 1000 WHERE email = %s",
            ("runner@example.com",),
        )
        conn.commit()

    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "budget_exceeded"


def test_post_chat_allowlisted_email_bypasses_budget_and_length(client, monkeypatch):
    monkeypatch.setenv("TOKEN_BUDGET_LIMIT", "1000")
    monkeypatch.setenv("UNRESTRICTED_EMAILS", "runner@example.com")
    _session_cookie_for_new_user(client)

    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET tokens_used = 999999 WHERE email = %s",
            ("runner@example.com",),
        )
        conn.commit()

    response = client.post("/chat", json={"message": "x" * 501})
    assert response.status_code == 200


def test_post_chat_increments_tokens_used_after_reply(client, monkeypatch):
    from backend.routes import chat as chat_route

    async def fake_process_query(user_id, conversation_id, messages, usage=None):
        if usage is not None:
            usage["input_tokens"] = 100
            usage["output_tokens"] = 50
        for chunk in ["mocked ", "reply"]:
            yield chunk

    monkeypatch.setattr(chat_route, "process_query", fake_process_query)
    _session_cookie_for_new_user(client)

    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 200

    with get_connection() as conn:
        row = conn.execute(
            "SELECT tokens_used FROM users WHERE email = %s", ("runner@example.com",)
        ).fetchone()
    assert row[0] == 150