import base64
import os
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from data.db import find_or_create_user, get_connection, init_db


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
def client():
    from backend.agent import app

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    return TestClient(app)


def _session_cookie_for_new_user(client) -> None:
    from datetime import datetime, timedelta, timezone

    from data.db import create_session

    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    client.cookies.set("session", token)


def test_get_preferences_requires_auth(client):
    response = client.get("/preferences")
    assert response.status_code == 401


def test_get_preferences_returns_defaults_for_new_user(client):
    _session_cookie_for_new_user(client)

    response = client.get("/preferences")

    assert response.status_code == 200
    assert response.json() == {
        "weekly_goal_km": 30,
        "units": "km",
        "notifications_enabled": True,
        "language": "en",
        "location_lat": None,
        "location_lon": None,
    }


def test_put_preferences_requires_auth(client):
    response = client.put("/preferences", json={"language": "de"})
    assert response.status_code == 401


def test_put_preferences_partial_update_round_trips_through_get(client):
    _session_cookie_for_new_user(client)

    put_response = client.put("/preferences", json={"language": "de"})
    assert put_response.status_code == 200
    assert put_response.json()["language"] == "de"
    assert put_response.json()["units"] == "km"

    get_response = client.get("/preferences")
    assert get_response.json()["language"] == "de"


def test_put_preferences_accepts_location(client):
    _session_cookie_for_new_user(client)

    response = client.put(
        "/preferences",
        json={"location_lat": 17.385, "location_lon": 78.4867},
    )

    assert response.status_code == 200
    assert response.json()["location_lat"] == 17.385
    assert response.json()["location_lon"] == 78.4867

    get_response = client.get("/preferences")
    assert get_response.json()["location_lat"] == 17.385
    assert get_response.json()["location_lon"] == 78.4867
