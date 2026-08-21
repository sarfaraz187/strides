import inspect

from backend.services.mcp_client import CALENDAR_SERVER_URL, open_mcp_session


def test_open_mcp_session_accepts_a_server_url_override():
    params = inspect.signature(open_mcp_session).parameters
    assert "server_url" in params


def test_open_mcp_session_defaults_server_url_to_health_server():
    params = inspect.signature(open_mcp_session).parameters
    assert params["server_url"].default is not None


def test_calendar_server_url_has_a_default():
    assert CALENDAR_SERVER_URL.endswith("/mcp")