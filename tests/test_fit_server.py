from unittest.mock import MagicMock, patch

from src.fit_server import get_runs


@patch("src.fit_server.requests.get")
@patch("src.fit_server.get_valid_access_token")
def test_get_runs_returns_json(mock_get_token, mock_requests_get):
    mock_get_token.return_value = "fake-access-token"

    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {"dataPoint": []}
    mock_requests_get.return_value = mock_response

    result = get_runs()

    assert result == {"dataPoint": []}
    mock_requests_get.assert_called_once_with(
        "https://health.googleapis.com/v4/users/me/dataTypes/exercise/dataPoints",
        headers={"Authorization": "Bearer fake-access-token"},
    )
