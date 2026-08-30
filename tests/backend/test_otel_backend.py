from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from fastapi.testclient import TestClient

from backend.agent import app


def test_health_route_produces_a_span():
    # backend.agent already calls setup_tracing()/instrument_app() at import
    # time, which sets OTel's process-wide TracerProvider singleton — it
    # cannot be replaced from a test. Attach our exporter to the provider
    # that's already live instead of trying to install a new one.
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))

    client = TestClient(app)
    client.get("/auth/me")  # any existing route is fine; unauth 401 still spans

    spans = exporter.get_finished_spans()
    assert any(s.name.upper().startswith("GET") for s in spans)
