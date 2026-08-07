import requests
import responses

from mcp_servers.fit_server.helpers.health_api import get_health_data

URL = "https://health.googleapis.com/v4/users/me/dataTypes/exercise/dataPoints"


@responses.activate
def test_account_not_linked_returns_tagged_error_with_redirect_uri():
    responses.add(
        responses.GET,
        URL,
        json={
            "error": {
                "code": 400,
                "message": "The account is not linked to Google Health.",
                "status": "FAILED_PRECONDITION",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": "ACCOUNT_NOT_LINKED",
                        "domain": "health.googleapis.com",
                        "metadata": {
                            "redirect_uri": "https://fitbit.google.com/auth/signup"
                        },
                    }
                ],
            }
        },
        status=400,
    )

    result = get_health_data("fake-token", URL)

    assert result == {
        "error": "ACCOUNT_NOT_LINKED",
        "message": "The account is not linked to Google Health.",
        "redirect_uri": "https://fitbit.google.com/auth/signup",
    }


@responses.activate
def test_http_error_without_error_info_shape_returns_unknown_error():
    responses.add(
        responses.GET,
        URL,
        json={"error": {"code": 401, "message": "Invalid credentials", "status": "UNAUTHENTICATED"}},
        status=401,
    )

    result = get_health_data("fake-token", URL)

    assert result == {"error": "UNKNOWN_ERROR", "message": "Invalid credentials"}
    assert "redirect_uri" not in result


def test_connection_failure_returns_request_failed(monkeypatch):
    def raise_connection_error(*args, **kwargs):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(requests, "get", raise_connection_error)

    result = get_health_data("fake-token", URL)

    assert result == {"error": "REQUEST_FAILED", "message": "network down"}


@responses.activate
def test_success_returns_parsed_json_unchanged():
    responses.add(responses.GET, URL, json={"point": [{"foo": "bar"}]}, status=200)

    result = get_health_data("fake-token", URL)

    assert result == {"point": [{"foo": "bar"}]}
