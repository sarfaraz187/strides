import asyncio
import base64
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from data.db import (
    create_session,
    find_or_create_user,
    get_connection,
    init_db,
    save_oauth_token,
    upsert_preferences,
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
        conn.execute("DELETE FROM users WHERE email = %s", ("dashboard-route@example.com",))
        conn.commit()


@pytest.fixture
def client():
    from backend.agent import app

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    return TestClient(app)


def _session_cookie(client) -> dict[str, str]:
    user_id = find_or_create_user(
        "dashboard-route@example.com", "dashboard-route-sub", "Dashboard Route"
    )
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    return {"session": token}


def _mock_session(weekly_stats: dict, recent_runs: list[dict]):
    session = AsyncMock()

    async def call_tool(name, args):
        result = AsyncMock()
        if name == "get_weekly_stats":
            result.structuredContent = weekly_stats
        elif name == "get_recent_runs":
            result.structuredContent = {"result": recent_runs}
        return result

    session.call_tool.side_effect = call_tool

    @asynccontextmanager
    async def open_mcp_session(user_id, server_url):
        yield session

    return open_mcp_session


def _mock_session_with_error(error_dict: dict):
    session = AsyncMock()

    async def call_tool(name, args):
        result = AsyncMock()
        if name == "get_weekly_stats":
            result.structuredContent = error_dict
        elif name == "get_recent_runs":
            result.structuredContent = error_dict
        return result

    session.call_tool.side_effect = call_tool

    @asynccontextmanager
    async def open_mcp_session(user_id, server_url):
        yield session

    return open_mcp_session


def test_dashboard_requires_auth(client):
    response = client.get("/dashboard")
    assert response.status_code == 401


def test_dashboard_health_not_connected_skips_mcp_and_returns_flag(client):
    cookies = _session_cookie(client)

    def open_mcp_session_should_not_be_called(user_id):
        raise AssertionError("MCP session should not be opened when Health is not connected")

    with patch(
        "backend.routes.dashboard.open_mcp_session",
        open_mcp_session_should_not_be_called,
    ):
        response = client.get("/dashboard", cookies=cookies)

    assert response.status_code == 200
    body = response.json()
    assert body["health_connected"] is False
    assert body["weekly_stats"] is None
    assert body["recent_runs"] == []


def test_dashboard_connected_but_account_not_linked_returns_health_error(client):
    cookies = _session_cookie(client)
    user_id = find_or_create_user(
        "dashboard-route@example.com", "dashboard-route-sub", "Dashboard Route"
    )
    save_oauth_token(user_id, "health", "access-token", "refresh-token", 9999999999)

    health_error = {
        "error": "ACCOUNT_NOT_LINKED",
        "message": "The account is not linked to Google Health.",
        "redirect_uri": "https://fitbit.google.com/auth/signup",
    }

    with patch(
        "backend.routes.dashboard.open_mcp_session",
        _mock_session_with_error(health_error),
    ):
        response = client.get("/dashboard", cookies=cookies)

    assert response.status_code == 200
    body = response.json()
    assert body["health_connected"] is True
    assert body["health_error"] == health_error
    assert body["weekly_stats"] is None
    assert body["recent_runs"] == []


def test_dashboard_returns_weekly_stats_and_recent_runs(client):
    """weekly_stats is now derived from recent_runs client-side (not a separate
    MCP call) — a run from last week must be excluded from the weekly totals
    even though it's still returned in recent_runs."""
    cookies = _session_cookie(client)
    user_id = find_or_create_user(
        "dashboard-route@example.com", "dashboard-route-sub", "Dashboard Route"
    )
    save_oauth_token(user_id, "health", "access-token", "refresh-token", 9999999999)

    now = datetime.now(timezone.utc)
    this_monday = now - timedelta(days=now.weekday())
    this_week_run = {
        "date": (this_monday + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S"),
        "distance_km": 6.1,
        "duration_min": 33.4,
        "pace_min_per_km": 5.47,
    }
    last_week_run = {
        "date": (this_monday - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        "distance_km": 10.0,
        "duration_min": 60.0,
        "pace_min_per_km": 6.0,
    }
    recent_runs = [this_week_run, last_week_run]

    with patch(
        "backend.routes.dashboard.open_mcp_session",
        _mock_session({}, recent_runs),
    ):
        response = client.get("/dashboard", cookies=cookies)

    assert response.status_code == 200
    body = response.json()
    assert body["weekly_stats"] == {
        "run_count": 1,
        "total_distance_km": 6.1,
        "total_duration_min": 33.4,
        "avg_pace_min_per_km": round(33.4 / 6.1, 2),
    }
    assert body["recent_runs"] == recent_runs
    assert body["health_connected"] is True


def test_dashboard_connected_but_mcp_call_fails_returns_flag(client):
    cookies = _session_cookie(client)
    user_id = find_or_create_user(
        "dashboard-route@example.com", "dashboard-route-sub", "Dashboard Route"
    )
    save_oauth_token(user_id, "health", "access-token", "refresh-token", 9999999999)

    @asynccontextmanager
    async def broken_mcp_session(user_id):
        raise RuntimeError("Health API unavailable")
        yield  # pragma: no cover - unreachable, makes this an async generator

    with patch(
        "backend.routes.dashboard.open_mcp_session",
        broken_mcp_session,
    ):
        response = client.get("/dashboard", cookies=cookies)

    assert response.status_code == 200
    body = response.json()
    assert body["health_connected"] is False
    assert body["weekly_stats"] is None
    assert body["recent_runs"] == []


def _delayed_session(weekly_stats: dict, recent_runs: list[dict], upcoming_runs: list[dict], delay: float):
    session = AsyncMock()

    async def call_tool(name, args):
        await asyncio.sleep(delay)
        result = AsyncMock()
        if name == "get_weekly_stats":
            result.structuredContent = weekly_stats
        elif name == "get_recent_runs":
            result.structuredContent = {"result": recent_runs}
        elif name == "list_upcoming_runs":
            result.structuredContent = {"result": upcoming_runs}
        return result

    session.call_tool.side_effect = call_tool

    @asynccontextmanager
    async def open_mcp_session(user_id, server_url):
        await asyncio.sleep(delay)
        yield session

    return open_mcp_session


def test_dashboard_fetches_health_calendar_and_weather_concurrently(client):
    """Health, calendar, and weather are independent — the endpoint should fire them
    concurrently rather than awaiting each in turn. Each mocked branch sleeps 0.3s;
    two calls per MCP session means a fully sequential health block alone takes 0.6s,
    plus 0.3s+0.3s sequential weather calls, plus the calendar session — comfortably
    over 1s if nothing runs in parallel. A concurrent implementation should finish
    in roughly one branch's worth of latency (~0.6s)."""
    cookies = _session_cookie(client)
    user_id = find_or_create_user(
        "dashboard-route@example.com", "dashboard-route-sub", "Dashboard Route"
    )
    save_oauth_token(user_id, "health", "access-token", "refresh-token", 9999999999)
    save_oauth_token(user_id, "calendar", "access-token", "refresh-token", 9999999999)
    upsert_preferences(user_id, location_lat=12.9716, location_lon=77.5946)

    weekly_stats = {"run_count": 1, "total_distance_km": 5.0, "total_duration_min": 30.0, "avg_pace_min_per_km": 6.0}
    delay = 0.3

    async def delayed_conditions(lat, lon):
        await asyncio.sleep(delay)
        return {"temp": 20, "feels_like": 19, "humidity": 50, "wind": 10, "condition": "clear", "hourly": []}

    async def delayed_air_quality(lat, lon):
        await asyncio.sleep(delay)
        return {"aqi": 42}

    with (
        patch(
            "backend.routes.dashboard.open_mcp_session",
            _delayed_session(weekly_stats, [], [], delay),
        ),
        patch("backend.services.weather_service.get_current_conditions", delayed_conditions),
        patch("backend.services.weather_service.get_air_quality", delayed_air_quality),
    ):
        start = time.monotonic()
        response = client.get("/dashboard", cookies=cookies)
        elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert elapsed < 1.0, (
        f"dashboard took {elapsed:.2f}s — branches appear to be running sequentially, not concurrently"
    )
