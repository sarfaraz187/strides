import base64
import json
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

    async def fake_process_query(user_id, messages):
        for chunk in ["mocked ", "reply"]:
            yield chunk

    monkeypatch.setattr(chat_route, "process_query", fake_process_query)

    async def fake_maybe_fold(user_id, system_prompt, rows, tools):
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


def _session_cookie_for_new_user(client) -> dict[str, str]:
    from datetime import datetime, timedelta, timezone

    user_id = find_or_create_user(
        "runner@example.com", "google-sub-123", "Runner Example"
    )
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    return {"session": token}


def test_post_chat_requires_auth(client):
    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 401


def _collect_sse_text(response) -> str:
    text = ""
    for line in response.text.splitlines():
        if line.startswith("data: "):
            text += json.loads(line[len("data: ") :])["text"]
    return text


def test_post_chat_streams_sse_and_persists_full_reply(client):
    cookies = _session_cookie_for_new_user(client)

    response = client.post("/chat", json={"message": "hi"}, cookies=cookies)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert _collect_sse_text(response) == "mocked reply"

    history = client.get("/chat/history", cookies=cookies)
    contents = [m["content"] for m in history.json()["messages"]]
    assert contents == ["mocked reply", "hi"]


def test_get_chat_history_requires_auth(client):
    response = client.get("/chat/history")
    assert response.status_code == 401


def test_post_chat_calls_maybe_fold_with_rows_since_last_summary(client, monkeypatch):
    from backend.routes import chat as chat_route

    fold_mock = AsyncMock(side_effect=lambda user_id, system_prompt, rows, tools: rows)
    monkeypatch.setattr(chat_route, "maybe_fold", fold_mock)

    cookies = _session_cookie_for_new_user(client)
    response = client.post("/chat", json={"message": "hi"}, cookies=cookies)

    assert response.status_code == 200
    fold_mock.assert_awaited_once()
    call_args = fold_mock.await_args
    rows_arg = call_args.args[2]
    assert [r["content"] for r in rows_arg] == ["hi"]


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
