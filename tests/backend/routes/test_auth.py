import base64
import os
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from data.db import init_db


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


def test_login_redirects_to_google_with_identity_scopes(client):
    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 307
    location = response.headers["location"]
    assert "accounts.google.com" in location
    assert "scope=openid" in location or "openid" in location
    assert "googlehealth" not in location


def test_callback_creates_user_and_sets_session_cookie(client):
    with patch("backend.services.auth_service.exchange_code_for_identity_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "email": "runner@example.com",
            "google_sub": "google-sub-123",
        }
        response = client.get(
            "/auth/callback?code=fake-code", follow_redirects=False
        )

    assert response.status_code == 307
    assert "session" in response.cookies


def test_logout_deletes_session_cookie(client):
    with patch("backend.services.auth_service.exchange_code_for_identity_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "email": "runner@example.com",
            "google_sub": "google-sub-123",
        }
        login_response = client.get(
            "/auth/callback?code=fake-code", follow_redirects=False
        )
    session_cookie = login_response.cookies["session"]

    logout_response = client.post(
        "/auth/logout", cookies={"session": session_cookie}
    )

    assert logout_response.status_code == 200


def _login(client) -> str:
    with patch("backend.services.auth_service.exchange_code_for_identity_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "email": "runner@example.com",
            "google_sub": "google-sub-123",
        }
        response = client.get("/auth/callback?code=fake-code", follow_redirects=False)
    return response.cookies["session"]


def test_health_connect_requires_session(client):
    response = client.get("/auth/health/connect", follow_redirects=False)
    assert response.status_code == 401


def test_health_connect_redirects_with_health_scope(client):
    session_cookie = _login(client)

    response = client.get(
        "/auth/health/connect",
        cookies={"session": session_cookie},
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert "googlehealth" in response.headers["location"]


def test_health_callback_stores_encrypted_token(client):
    session_cookie = _login(client)

    with patch("backend.services.auth_service.exchange_code_for_health_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "access_token": "health-access",
            "refresh_token": "health-refresh",
            "expires_in": 3600,
        }
        response = client.get(
            "/auth/health/callback?code=fake-code",
            cookies={"session": session_cookie},
            follow_redirects=False,
        )

    assert response.status_code == 307


def test_health_disconnect_removes_token(client):
    session_cookie = _login(client)
    with patch("backend.services.auth_service.exchange_code_for_health_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "access_token": "health-access",
            "refresh_token": "health-refresh",
            "expires_in": 3600,
        }
        client.get(
            "/auth/health/callback?code=fake-code",
            cookies={"session": session_cookie},
            follow_redirects=False,
        )

    response = client.post(
        "/auth/health/disconnect", cookies={"session": session_cookie}
    )

    assert response.status_code == 200
