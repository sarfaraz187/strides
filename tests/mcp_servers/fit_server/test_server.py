from unittest.mock import patch

from mcp_servers.fit_server import server

ERROR_RESPONSE = {
    "error": "ACCOUNT_NOT_LINKED",
    "message": "The account is not linked to Google Health.",
    "redirect_uri": "https://fitbit.google.com/auth/signup",
}


@patch("mcp_servers.fit_server.server.get_valid_access_token", return_value="fake-token")
@patch("mcp_servers.fit_server.server.current_user_id", return_value="user-1")
@patch("mcp_servers.fit_server.server.get_health_data", return_value=ERROR_RESPONSE)
def test_get_recent_runs_returns_error_dict_instead_of_crashing_parse_run(
    mock_get_health_data, mock_user_id, mock_token
):
    result = server.get_recent_runs(days=7)
    assert result == ERROR_RESPONSE


@patch("mcp_servers.fit_server.server.get_valid_access_token", return_value="fake-token")
@patch("mcp_servers.fit_server.server.current_user_id", return_value="user-1")
@patch("mcp_servers.fit_server.server.get_health_data", return_value=ERROR_RESPONSE)
def test_get_run_stats_returns_error_dict_instead_of_crashing_aggregation(
    mock_get_health_data, mock_user_id, mock_token
):
    result = server.get_run_stats("2026-08-01", "2026-08-07")
    assert result == ERROR_RESPONSE
