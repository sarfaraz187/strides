from unittest.mock import MagicMock, patch

from src.fit_server import get_runs


@patch("src.helpers.health_api.requests.get")
@patch("src.helpers.health_api.get_valid_access_token")
def test_get_runs_returns_json(mock_get_token, mock_requests_get):
    mock_get_token.return_value = "fake-access-token"

    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {"dataPoints": []}
    mock_requests_get.return_value = mock_response

    result = get_runs()

    assert result == {"dataPoints": []}
    mock_requests_get.assert_called_once_with(
        "https://health.googleapis.com/v4/users/me/dataTypes/exercise/dataPoints",
        params=None,
        headers={"Authorization": "Bearer fake-access-token"},
    )
