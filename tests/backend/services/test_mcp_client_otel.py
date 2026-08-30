import httpx
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from backend.services.mcp_client import _build_session_headers, refresh_traceparent


def test_session_headers_include_traceparent_when_span_active():
    provider = TracerProvider()
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("outer"):
        headers = _build_session_headers(token="jwt-abc")

    assert headers["Authorization"] == "Bearer jwt-abc"
    assert "traceparent" in headers


def test_refresh_traceparent_updates_header_to_current_span():
    provider = TracerProvider()
    tracer = provider.get_tracer("test")
    http_client = httpx.AsyncClient(headers={"traceparent": "stale-value"})

    with tracer.start_as_current_span("new-span"):
        refresh_traceparent(http_client)
        updated = http_client.headers["traceparent"]

    assert updated != "stale-value"
