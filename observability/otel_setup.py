import os

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract as _propagate_extract
from opentelemetry.propagate import inject as _propagate_inject
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor


def setup_tracing(service_name: str) -> trace.Tracer:
    """Configure the global TracerProvider for this process and return a Tracer scoped to service_name. Call once per entry point, at startup.

    If OTEL_EXPORTER_OTLP_ENDPOINT isn't set (e.g. local dev with no Grafana/OTLP creds configured), no exporter is attached — spans are still created and can be asserted on in tests, but nothing is sent over the network and nothing spams connection-refused errors.

    Set OTEL_DEBUG_CONSOLE=1 to also (or instead) print every finished span as JSON to stderr — useful for seeing exactly what a span looks like while running the app locally, before wiring up Grafana."""  # noqa: E501
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

    if os.environ.get("OTEL_DEBUG_CONSOLE") == "1":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def inject_traceparent(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of headers with the current span's traceparent added, for propagating trace context across an outgoing HTTP call."""
    headers = dict(headers)
    _propagate_inject(headers)
    return headers


def extract_context(headers: dict[str, str]) -> Context:
    """Parse a traceparent header (from an incoming request) back into an OTel Context usable as a new span's parent."""
    return _propagate_extract(headers)
