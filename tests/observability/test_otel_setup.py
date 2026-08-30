from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from observability.otel_setup import extract_context, inject_traceparent, setup_tracing


def test_inject_traceparent_adds_header_when_span_is_active():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("parent-span"):
        headers = inject_traceparent({"Authorization": "Bearer x"})

    assert "traceparent" in headers
    assert headers["Authorization"] == "Bearer x"


def test_extract_context_recovers_trace_id_from_header():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("parent-span") as parent_span:
        expected_trace_id = parent_span.get_span_context().trace_id
        headers = inject_traceparent({})

    ctx = extract_context(headers)
    span_ctx = trace.get_current_span(ctx).get_span_context()
    assert span_ctx.trace_id == expected_trace_id


def test_setup_tracing_skips_otlp_exporter_when_endpoint_not_set(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    tracer = setup_tracing("test-service-no-endpoint")

    # Should not raise/attempt a real network export, and should still hand
    # back a usable tracer that can start spans locally.
    with tracer.start_as_current_span("local-only-span") as span:
        assert span.is_recording()
