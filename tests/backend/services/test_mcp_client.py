import inspect

from backend.services.mcp_client import (
    CALENDAR_SERVER_URL,
    HEALTH_SERVER_URL,
    open_mcp_session,
)


def test_open_mcp_session_accepts_a_server_url_override():
    params = inspect.signature(open_mcp_session).parameters
    assert "server_url" in params


def test_open_mcp_session_requires_an_explicit_server_url():
    params = inspect.signature(open_mcp_session).parameters
    assert params["server_url"].default is inspect.Parameter.empty


def test_calendar_server_url_has_a_default():
    assert CALENDAR_SERVER_URL.endswith("/mcp")


def test_health_server_url_has_a_default():
    assert HEALTH_SERVER_URL.endswith("/mcp")