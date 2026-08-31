from unittest.mock import MagicMock

from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from mcp_servers.calendar_server.server import delete_run_event


def test_delete_run_event_emits_a_span(monkeypatch):
    # server.py already calls setup_tracing() at import time, which sets
    # OTel's process-wide TracerProvider singleton — it cannot be replaced
    # from a test. Attach our exporter to the provider that's already live.
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))

    import mcp_servers.calendar_server.server as server_module

    monkeypatch.setattr(server_module, "current_user_id", lambda: "user-1")
    monkeypatch.setattr(
        server_module, "get_valid_access_token", lambda *a, **k: "fake-token"
    )
    monkeypatch.setattr(server_module, "ensure_calendar", lambda *a, **k: "cal-1")
    monkeypatch.setattr(server_module, "delete_event", lambda *a, **k: None)

    fake_ctx = MagicMock()
    fake_ctx.request_context.request = None

    delete_run_event(event_id="evt-1", ctx=fake_ctx)

    spans = exporter.get_finished_spans()
    assert any(s.name == "mcp.tool.delete_run_event" for s in spans)


def test_delete_run_event_works_without_ctx(monkeypatch):
    """ctx defaults to None (e.g. called directly, not via MCP transport) —
    must not crash."""
    import mcp_servers.calendar_server.server as server_module

    monkeypatch.setattr(server_module, "current_user_id", lambda: "user-1")
    monkeypatch.setattr(
        server_module, "get_valid_access_token", lambda *a, **k: "fake-token"
    )
    monkeypatch.setattr(server_module, "ensure_calendar", lambda *a, **k: "cal-1")
    monkeypatch.setattr(server_module, "delete_event", lambda *a, **k: None)

    result = delete_run_event(event_id="evt-1")

    assert result == {"status": "deleted"}
