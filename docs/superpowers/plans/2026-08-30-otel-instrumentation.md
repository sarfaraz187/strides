# OpenTelemetry Instrumentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrument the FastAPI backend and both MCP servers (`fit_server`, `calendar_server`) with OpenTelemetry so a single user request produces one joined trace in Grafana Cloud Tempo, showing HTTP/DB timing (auto) plus internal business-logic steps (manual spans).

**Architecture:** Each of the 3 services gets its own OTel SDK setup via a shared, generic `observability/otel_setup.py` module (same pattern as the existing shared `logging_config.py` — no service imports another service's code). Auto-instrumentation covers FastAPI routes and psycopg queries in the backend. Manual spans cover MCP tool execution, external API calls, and chat-processing steps. Trace context crosses the backend→MCP HTTP boundary via manual W3C traceparent header injection/extraction (confirmed: FastMCP tool functions can read the raw incoming request via `ctx.request_context.request.headers` when a `ctx: Context` parameter is added).

**Tech Stack:** `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-psycopg`, Grafana Cloud (Tempo, OTLP ingest).

**Spec:** `docs/superpowers/specs/2026-08-29-observability-and-bug-agent-design.md` — this plan implements only the "Instrumentation scope" row of that spec's decision table (backend + both MCP servers). The cron bug-triage agent is a separate, later plan.

## Global Constraints

- No code in `mcp_servers/fit_server` or `mcp_servers/calendar_server` may import from `backend/` — each MCP server must remain independently usable. The shared `observability/` module is a generic, standalone util (like `logging_config.py`), not backend code.
- Instrumentation is manual for anything beyond raw HTTP in/out (per user decision) — auto-instrumentation is used only for FastAPI request spans and psycopg query spans in the backend.
- All logging/tracing setup follows the existing pattern: called once per entry point (`agent.py`, `fit_server/server.py`, `calendar_server/server.py`).
- OTel env vars use the SDK's standard names (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_SERVICE_NAME`) so no custom parsing code is needed — the SDK reads them itself.

---

## File Structure

- Create: `observability/otel_setup.py` — shared, generic tracer setup (`setup_tracing(service_name)`) usable by any Python service in the repo, plus `inject_traceparent`/`extract_context` helpers for manual cross-service propagation.
- Create: `tests/observability/test_otel_setup.py` — verifies spans are created/exported using OTel's `InMemorySpanExporter` test helper.
- Modify: `backend/agent.py` — call `setup_tracing("strides-backend")` and FastAPI/psycopg auto-instrumentors at startup.
- Modify: `backend/services/mcp_client.py` — inject `traceparent` header into the MCP session's HTTP headers so the child trace continues server-side.
- Modify: `backend/services/chat_service.py` — wrap the query-processing steps (tool loop, each tool call, final response assembly) in manual spans.
- Create: `tests/backend/test_otel_backend.py` — asserts spans appear for a sample request via `InMemorySpanExporter` + FastAPI `TestClient`.
- Modify: `mcp_servers/fit_server/server.py` — call `setup_tracing("strides-fit-server")` at startup; wrap each `@mcp.tool()` body in a manual span parented from the incoming `traceparent` header.
- Create: `tests/mcp_servers/fit_server/test_otel_fit_server.py`.
- Modify: `mcp_servers/calendar_server/server.py` — same pattern as fit_server.
- Create: `tests/mcp_servers/calendar_server/test_otel_calendar_server.py`.
- Modify: `pyproject.toml` — add OTel dependencies.
- Modify: `.github/workflows/deploy.yml` — add `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_EXPORTER_OTLP_HEADERS`/`OTEL_SERVICE_NAME` env vars to all three `gcloud run deploy` commands.
- Modify: `.env.example` — document the two new local env vars.

---

### Task 1: Add OTel dependencies and shared tracer setup module

**Files:**
- Modify: `pyproject.toml`
- Create: `observability/__init__.py` (empty)
- Create: `observability/otel_setup.py`
- Test: `tests/observability/test_otel_setup.py`

**Interfaces:**
- Produces: `setup_tracing(service_name: str) -> trace.Tracer` — configures the global `TracerProvider` with an OTLP HTTP exporter (reads endpoint/headers from standard `OTEL_EXPORTER_OTLP_*` env vars automatically) and returns a `Tracer` for the caller to use.
- Produces: `inject_traceparent(headers: dict[str, str]) -> dict[str, str]` — returns a new dict with the current span context's `traceparent` header added.
- Produces: `extract_context(headers: dict[str, str]) -> Context` — parses a `traceparent` header back into an OTel `Context` usable as a span's parent.

- [x] **Step 1: Add dependencies to `pyproject.toml`**

Add to the `dependencies` list in `pyproject.toml`:

```toml
"opentelemetry-sdk>=1.27.0",
"opentelemetry-exporter-otlp-proto-http>=1.27.0",
"opentelemetry-instrumentation-fastapi>=0.48b0",
"opentelemetry-instrumentation-psycopg>=0.48b0",
```

Run: `uv sync`
Expected: lockfile updates, no errors.

- [x] **Step 2: Write the failing test**

```python
# tests/observability/test_otel_setup.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from observability.otel_setup import extract_context, inject_traceparent


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
```

- [x] **Step 3: Run test to verify it fails**

Run: `pytest tests/observability/test_otel_setup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'observability'`

- [x] **Step 4: Write `observability/otel_setup.py`**

```python
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.propagate import extract as _propagate_extract
from opentelemetry.propagate import inject as _propagate_inject
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_tracing(service_name: str) -> trace.Tracer:
    """Configure the global TracerProvider for this process and return a
    Tracer scoped to service_name. Call once per entry point, at startup.

    Reads OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_EXPORTER_OTLP_HEADERS from the
    environment via the SDK's own env var handling — no custom parsing here.
    """
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def inject_traceparent(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of headers with the current span's traceparent added,
    for propagating trace context across an outgoing HTTP call."""
    headers = dict(headers)
    _propagate_inject(headers)
    return headers


def extract_context(headers: dict[str, str]) -> Context:
    """Parse a traceparent header (from an incoming request) back into an
    OTel Context usable as a new span's parent."""
    return _propagate_extract(headers)
```

- [x] **Step 5: Run test to verify it passes**

Run: `pytest tests/observability/test_otel_setup.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock observability/__init__.py observability/otel_setup.py tests/observability/test_otel_setup.py
git commit -m "feat: add shared OTel tracer setup and context propagation helpers"
```

---

### Task 2: Instrument the FastAPI backend (auto HTTP/DB spans)

**Files:**
- Modify: `backend/agent.py`
- Test: `tests/backend/test_otel_backend.py`

**Interfaces:**
- Consumes: `setup_tracing` from Task 1 (`observability/otel_setup.py`).

- [x] **Step 1: Write the failing test**

```python
# tests/backend/test_otel_backend.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from fastapi.testclient import TestClient

from backend.agent import app


def test_health_route_produces_a_span():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    client = TestClient(app)
    client.get("/auth/me")  # any existing route is fine; unauth 401 still spans

    spans = exporter.get_finished_spans()
    assert any(s.name.upper().startswith("GET") for s in spans)

    FastAPIInstrumentor.uninstrument_app(app)
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_otel_backend.py -v`
Expected: FAIL — no spans recorded (nothing instruments `app` yet at import time in a way that matters for this assertion; the test's own manual `instrument_app` call still exercises real middleware, so if it fails, note the actual error and fix in Step 3's code, not the test).

Note: this test instruments `app` directly, independent of the module-level startup code — it verifies FastAPI's OTel middleware works against our actual `app` object, not that startup wiring is correct. That gets covered by Step 3 wiring the same call into `agent.py`.

- [x] **Step 3: Wire auto-instrumentation into `backend/agent.py`**

Find the existing `app = FastAPI(lifespan=lifespan)` line (`backend/agent.py:92`) and the `lifespan` function above it (`backend/agent.py:85`). Add imports at the top:

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

from observability.otel_setup import setup_tracing
```

Immediately after `app = FastAPI(lifespan=lifespan)`, add:

```python
setup_tracing("strides-backend")
FastAPIInstrumentor.instrument_app(app)
PsycopgInstrumentor().instrument()
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/backend/test_otel_backend.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agent.py tests/backend/test_otel_backend.py
git commit -m "feat: auto-instrument backend FastAPI routes and psycopg queries with OTel"
```

---

### Task 3: Propagate trace context from backend to MCP servers

**Files:**
- Modify: `backend/services/mcp_client.py`
- Test: `tests/backend/services/test_mcp_client_otel.py`

**Interfaces:**
- Consumes: `inject_traceparent` from Task 1.
- Produces: `open_mcp_session` now yields `(session, http_client)` instead of just `session`, and exposes `refresh_traceparent(http_client)` so a caller can re-stamp the header immediately before each individual tool call — the mcp SDK's `ClientSession.call_tool()` has no per-call header parameter, and `httpx.AsyncClient`'s headers are otherwise fixed at construction, so a header set once when the session opens would stay stale (pointing at whatever span was active at session-open, not the specific span active for that call) across every tool call made on a long-lived session. `httpx.AsyncClient.headers` is mutable and read fresh per outgoing request, which is what makes this fix possible without re-authenticating or reconnecting.

- [x] **Step 1: Write the failing test**

```python
# tests/backend/services/test_mcp_client_otel.py
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/services/test_mcp_client_otel.py -v`
Expected: FAIL with `ImportError: cannot import name '_build_session_headers'`

- [x] **Step 3: Extract a headers-builder, add `refresh_traceparent`, and change `open_mcp_session` to yield the http_client too, in `backend/services/mcp_client.py`**

Replace the current inline header dict (`backend/services/mcp_client.py:24-26`) with:

```python
from observability.otel_setup import inject_traceparent

# ... existing imports/constants unchanged ...


def _build_session_headers(token: str) -> dict[str, str]:
    return inject_traceparent({"Authorization": f"Bearer {token}"})


def refresh_traceparent(http_client: httpx.AsyncClient) -> None:
    """Re-stamp the client's traceparent header from whatever span is current
    right now. Call this immediately before each tool_call — the header set
    at session-open time only reflects the span active back then, and a
    session is reused across every tool call in a request's tool-use loop."""
    http_client.headers.update(inject_traceparent({}))


@asynccontextmanager
async def open_mcp_session(user_id: str, server_url: str):
    """Open a fresh, per-caller MCP session authenticated as user_id.

    Short-lived by design, matching the 5-minute JWT it mints — a cached,
    long-lived session couldn't carry a fresh token per request anyway.

    Yields (session, http_client) — the caller needs http_client too, to call
    refresh_traceparent() before each individual tool call."""
    token = mint_token(user_id)
    async with httpx.AsyncClient(
        headers=_build_session_headers(token)
    ) as http_client:
        try:
            async with streamable_http_client(server_url, http_client=http_client) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session, http_client
        except* httpx.ConnectError as eg:
            raise HTTPException(
                status_code=503,
                detail=f"A data service is unavailable — is the MCP server running on {server_url}?",
            ) from eg
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/backend/services/test_mcp_client_otel.py -v`
Expected: PASS

- [x] **Step 5: Run the full backend test suite to check nothing else regressed**

Note: changing `open_mcp_session`'s yield shape from `session` to `(session, http_client)` breaks every existing caller — this step's "nothing else regressed" check depends on Task 4 updating `chat_service.py`'s two call sites in the same PR. Run the full suite only after Task 4's Step 4 is also in place; expect failures if run in isolation before that.

Run: `pytest tests/backend -v`
Expected: all PASS (once Task 4 is also applied)

- [ ] **Step 6: Commit**

```bash
git add backend/services/mcp_client.py tests/backend/services/test_mcp_client_otel.py
git commit -m "feat: propagate traceparent header from backend to MCP server calls"
```

---

### Task 4: Manual spans for backend chat-processing steps

**Files:**
- Modify: `backend/services/chat_service.py`
- Test: `tests/backend/services/test_chat_service_otel.py`

**Interfaces:**
- Consumes: `trace.get_tracer(__name__)` (standard OTel API, no new helper needed — the global provider was set in Task 2). Also consumes Task 3's updated `open_mcp_session` (now yields `(session, http_client)`) and `refresh_traceparent`.
- Produces: spans named `chat.process_query`, `chat.tool_call.<tool_name>` nested under each request's FastAPI span.
- Relationship to Langfuse (per `docs/superpowers/specs/2026-08-29-observability-and-bug-agent-design.md`): additive, not a replacement. Langfuse's existing `process_span`/`generation`/`tool` observations in this file (chat_service.py:129-224, 235-254) are LLM-specific (prompts, tokens, cache, cost) and stay exactly as-is. The new OTel spans are a separate, coexisting layer for infra/distributed tracing (this request's place in the HTTP→backend→MCP chain) — they nest as an *outer* wrapper around the existing Langfuse blocks, not a replacement for them.
- Span placement: `chat.process_query` wraps the **entire** `process_query` body — including both `open_mcp_session` calls and the whole `while True` tool-use loop — so its duration reflects true end-to-end time (session setup + every LLM round-trip + every tool call), and so Task 5/6's `mcp.tool.*` spans have a correctly-scoped ancestor to join under via trace-context propagation. The existing Langfuse `with` blocks stay untouched, just one indent level deeper.
- Per-call trace propagation: `call_tools` (chat_service.py:227-264) is where individual tool dispatch actually happens (`process_query` itself never sees a tool name) — this is also where the `chat.tool_call.<name>` span belongs, nested inside the Langfuse `tool_obs` block already there. Because a single MCP session is reused across every tool call in the loop, call `refresh_traceparent(http_client)` immediately before each `target_session.call_tool(...)` so that specific call's header reflects the `chat.tool_call.<name>` span active *right then*, not whatever span was active back when the session first opened.

- [x] **Step 1: Read the current implementation to find exact wrap points**

Read `backend/services/chat_service.py` in full before writing the test — this task's steps assume you can see the actual `process_query` generator (real signature: `async def process_query(user_id: str, messages: list[dict], usage: dict | None = None)`, chat_service.py:117) and `call_tools` (chat_service.py:227), including the existing Langfuse instrumentation already wrapping both.

- [x] **Step 2: Write the failing test**

```python
# tests/backend/services/test_chat_service_otel.py
from unittest.mock import AsyncMock, MagicMock

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry import trace

from backend.services import chat_service


def test_process_query_emits_a_span(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    chat_service.tracer = provider.get_tracer("strides-backend")

    # Stub the MCP session boundary — open_mcp_session now yields
    # (session, http_client); avoid any real network/auth.
    fake_http_client = MagicMock()
    fake_session = AsyncMock()
    fake_session.list_tools = AsyncMock(
        return_value=MagicMock(tools=[])
    )

    class _FakeSessionCtx:
        async def __aenter__(self):
            return fake_session, fake_http_client

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(
        chat_service, "open_mcp_session", lambda *a, **k: _FakeSessionCtx()
    )

    # Stub the Anthropic call so no live LLM request happens. process_query
    # imports `client`/`model`/`SYSTEM_PROMPT` from backend.agent locally
    # inside the function body — patch backend.agent.client directly.
    fake_response = MagicMock(
        content=[], stop_reason="end_turn", usage=MagicMock(
            input_tokens=1, output_tokens=1,
            cache_creation_input_tokens=0, cache_read_input_tokens=0,
        ),
    )

    class _FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        @property
        async def text_stream(self):
            return
            yield  # pragma: no cover - empty async generator

        async def get_final_message(self):
            return fake_response

    import backend.agent as agent_module

    monkeypatch.setattr(
        agent_module.client.messages, "stream", lambda **k: _FakeStream()
    )

    async def _run():
        async for _ in chat_service.process_query(
            user_id="test-user",
            messages=[{"role": "user", "content": "hello"}],
        ):
            pass

    import anyio

    anyio.run(_run)

    spans = exporter.get_finished_spans()
    assert any(s.name == "chat.process_query" for s in spans)
```

Note: this stub is deliberately verbose because `process_query` has real external dependencies (two MCP sessions, a streaming Anthropic call) with no existing seam — if `backend.agent.client` isn't easily monkeypatchable this way once Step 1's read is done, adjust the stub to match the actual import/call shape, but keep the goal the same: zero real network calls, one assertion on the span.

- [x] **Step 3: Run test to verify it fails**

Run: `pytest tests/backend/services/test_chat_service_otel.py -v`
Expected: FAIL — no span named `chat.process_query` recorded (also expect an `AttributeError` on `chat_service.tracer` until Step 4 adds it).

- [x] **Step 4: Add manual spans in `backend/services/chat_service.py`**

Add near the top of the file:

```python
from opentelemetry import trace

tracer = trace.get_tracer("strides-backend")
```

Wrap the **entire body** of `process_query` (from `with propagate_attributes(...)` through the end of the function) in `with tracer.start_as_current_span("chat.process_query") as span:`, setting `span.set_attribute("user_id", user_id)` right inside — this must be the outermost context manager, enclosing both `open_mcp_session` calls and the `while True` loop, with the existing Langfuse blocks nested inside it unchanged.

In `call_tools`, inside the `for block in content_blocks:` loop, wrap the `if block.name in LOCAL_TOOLS: ... else: ...` dispatch in its own nested span named `f"chat.tool_call.{block.name}"`, setting `span.set_attribute("tool_name", block.name)`. Immediately before the `target_session.call_tool(...)` line specifically (not before the `LOCAL_TOOLS` branch, which makes no MCP call), call `refresh_traceparent(target_http_client)` — this requires `call_tools` to also receive the http_client(s) now that `open_mcp_session` yields `(session, http_client)` (Task 3); update `call_tools`'s signature and its caller in `process_query` accordingly (mirroring how `sessions_by_tool` already maps tool name → session, add an equivalent map or pass-through for http_client). Keep all existing logic unchanged — only add the `with` blocks and the `refresh_traceparent` call.

- [x] **Step 5: Run test to verify it passes**

Run: `pytest tests/backend/services/test_chat_service_otel.py -v`
Expected: PASS

- [x] **Step 6: Run the full backend test suite**

Run: `pytest tests/backend -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add backend/services/chat_service.py tests/backend/services/test_chat_service_otel.py
git commit -m "feat: add manual OTel spans for chat query processing and tool calls"
```

---

### Task 5: Instrument `fit_server` MCP tools with manual spans joined to the caller's trace

**Files:**
- Modify: `mcp_servers/fit_server/server.py`
- Test: `tests/mcp_servers/fit_server/test_otel_fit_server.py`

**Interfaces:**
- Consumes: `setup_tracing`, `extract_context` from Task 1.
- Produces: each `@mcp.tool()` function emits a span named `mcp.tool.<name>`, parented from the caller's `traceparent` header when present.

- [x] **Step 1: Write the failing test**

```python
# tests/mcp_servers/fit_server/test_otel_fit_server.py
from unittest.mock import MagicMock

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from mcp_servers.fit_server.server import get_recent_runs


def test_get_recent_runs_emits_a_span(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    import mcp_servers.fit_server.server as server_module

    server_module.tracer = trace.get_tracer("strides-fit-server")
    monkeypatch.setattr(server_module, "current_user_id", lambda: "user-1")
    monkeypatch.setattr(
        server_module, "get_health_data", lambda *a, **k: {"exercises": []}
    )

    fake_ctx = MagicMock()
    fake_ctx.request_context.request.headers = {}

    get_recent_runs(days=7, ctx=fake_ctx)

    spans = exporter.get_finished_spans()
    assert any(s.name == "mcp.tool.get_recent_runs" for s in spans)
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/mcp_servers/fit_server/test_otel_fit_server.py -v`
Expected: FAIL — `get_recent_runs()` doesn't accept a `ctx` parameter yet, and no span is emitted.

- [x] **Step 3: Add tracing setup and a span helper in `mcp_servers/fit_server/server.py`**

Add imports:

```python
from mcp.server.fastmcp import Context

from observability.otel_setup import extract_context, setup_tracing
```

Right after `setup_logging()`, add:

```python
tracer = setup_tracing("strides-fit-server")
```

Add a small helper (place it above the tool definitions):

```python
def _parent_context_from(ctx: Context):
    """`ctx.request_context.request` is typed Optional and is genuinely None
    outside an HTTP-transported request (e.g. stdio transport, or a tool
    called directly with no live request) — guard it rather than assume it's
    always populated."""
    request = ctx.request_context.request
    if request is None:
        return None
    headers = dict(request.headers)
    return extract_context(headers)
```

- [x] **Step 4: Wrap each `@mcp.tool()` function to accept `ctx` and emit a span**

For `get_recent_runs` (and apply the identical pattern to `get_run_stats`, `get_weekly_stats`, `calculate`), add a `ctx: Context` parameter and wrap the existing body:

```python
@mcp.tool()
def get_recent_runs(days: int = 7, ctx: Context = None) -> list[dict[str, Any]]:
    """Get the user's runs from the last N days, with distance in km, duration in
    minutes, and pace in min/km already calculated. Use this for relative/recent
    queries like "how did I run this week" or "show my last 30 days" — use
    get_run_stats instead if the user gives explicit calendar dates. Returns a
    list of run dicts (empty list if no runs in the window, not an error)."""
    parent = _parent_context_from(ctx) if ctx is not None else None
    with tracer.start_as_current_span("mcp.tool.get_recent_runs", context=parent) as span:
        user_id = current_user_id()
        span.set_attribute("user_id", user_id)
        span.set_attribute("days", days)
        # ... existing function body unchanged, indented one level ...
```

Apply the same `with tracer.start_as_current_span("mcp.tool.<name>", context=parent):` wrapping to every other `@mcp.tool()` function in this file, each adding a `ctx: Context = None` parameter and computing `parent` the same way. Keep each function's existing body logic untouched, just indented under the `with` block.

- [x] **Step 5: Run test to verify it passes**

Run: `pytest tests/mcp_servers/fit_server/test_otel_fit_server.py -v`
Expected: PASS

- [x] **Step 6: Run the full fit_server test suite**

Run: `pytest tests/mcp_servers/fit_server -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add mcp_servers/fit_server/server.py tests/mcp_servers/fit_server/test_otel_fit_server.py
git commit -m "feat: add manual OTel spans to fit_server MCP tools, joined to caller trace"
```

---

### Task 6: Instrument `calendar_server` MCP tools with manual spans

**Files:**
- Modify: `mcp_servers/calendar_server/server.py`
- Test: `tests/mcp_servers/calendar_server/test_otel_calendar_server.py`

**Interfaces:**
- Consumes: `setup_tracing`, `extract_context` from Task 1. Identical pattern to Task 5.

- [x] **Step 1: Read `mcp_servers/calendar_server/server.py` in full** to get the exact current tool list and signatures (`create_run_event`, `update_run_event`, `delete_run_event`, and any others already there) before writing the test/implementation — this task's code applies the same wrapping shown in Task 5, not new logic.

- [x] **Step 2: Write the failing test**

```python
# tests/mcp_servers/calendar_server/test_otel_calendar_server.py
from unittest.mock import MagicMock

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from mcp_servers.calendar_server.server import delete_run_event


def test_delete_run_event_emits_a_span(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    import mcp_servers.calendar_server.server as server_module

    server_module.tracer = trace.get_tracer("strides-calendar-server")
    monkeypatch.setattr(server_module, "current_user_id", lambda: "user-1")
    monkeypatch.setattr(
        server_module, "get_valid_access_token", lambda *a, **k: "fake-token"
    )
    monkeypatch.setattr(server_module, "ensure_calendar", lambda *a, **k: "cal-1")
    monkeypatch.setattr(server_module, "delete_event", lambda *a, **k: None)

    fake_ctx = MagicMock()
    fake_ctx.request_context.request.headers = {}

    delete_run_event(event_id="evt-1", ctx=fake_ctx)

    spans = exporter.get_finished_spans()
    assert any(s.name == "mcp.tool.delete_run_event" for s in spans)
```

- [x] **Step 3: Run test to verify it fails**

Run: `pytest tests/mcp_servers/calendar_server/test_otel_calendar_server.py -v`
Expected: FAIL — `delete_run_event()` doesn't accept `ctx` yet.

- [x] **Step 4: Apply the same tracing setup and span-wrapping pattern as Task 5**

Add the same imports (`Context` from `mcp.server.fastmcp`, `extract_context`/`setup_tracing` from `observability.otel_setup`), call `tracer = setup_tracing("strides-calendar-server")` after this file's logger setup, add the same `_parent_context_from(ctx)` helper, and wrap every `@mcp.tool()` function (`create_run_event`, `update_run_event`, `delete_run_event`, and any others found in Step 1) the same way: add `ctx: Context = None`, wrap the body in `with tracer.start_as_current_span("mcp.tool.<name>", context=parent) as span:`, set `span.set_attribute("user_id", user_id)` and any other relevant identifiers (e.g. `event_id`) already available as function arguments.

- [x] **Step 5: Run test to verify it passes**

Run: `pytest tests/mcp_servers/calendar_server/test_otel_calendar_server.py -v`
Expected: PASS

- [x] **Step 6: Run the full calendar_server test suite**

Run: `pytest tests/mcp_servers/calendar_server -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add mcp_servers/calendar_server/server.py tests/mcp_servers/calendar_server/test_otel_calendar_server.py
git commit -m "feat: add manual OTel spans to calendar_server MCP tools, joined to caller trace"
```

---

### Task 7: Wire OTel env vars into local dev and Cloud Run deployment

**Files:**
- Modify: `.env.example`
- Modify: `.github/workflows/deploy.yml`

**Interfaces:** None — configuration only, no new code interfaces.

- [ ] **Step 1: Document local env vars in `.env.example`**

Add:

```
OTEL_EXPORTER_OTLP_ENDPOINT=
OTEL_EXPORTER_OTLP_HEADERS=
```

(Value for `OTEL_EXPORTER_OTLP_HEADERS` is `Authorization=Basic <base64(instance_id:api_token)>` — Grafana Cloud's OTLP gateway convention. Fill in from your existing Grafana Cloud account/token per your earlier answer that this is already provisioned.)

- [ ] **Step 2: Add two GitHub Actions repo secrets**

In GitHub repo settings → Secrets and variables → Actions, add:
- `OTEL_EXPORTER_OTLP_ENDPOINT` (Grafana Cloud OTLP gateway URL)
- `OTEL_EXPORTER_OTLP_HEADERS` (the `Authorization=Basic ...` value)

This is a manual step in the GitHub UI — no command to run.

- [ ] **Step 3: Add `OTEL_SERVICE_NAME`/`OTEL_EXPORTER_OTLP_*` to each `gcloud run deploy` command in `.github/workflows/deploy.yml`**

For `deploy-backend` (`.github/workflows/deploy.yml`, the `--set-env-vars=` line under `deploy-backend`), append to the existing comma-separated value:

```
,OTEL_EXPORTER_OTLP_ENDPOINT=${{ secrets.OTEL_EXPORTER_OTLP_ENDPOINT }},OTEL_EXPORTER_OTLP_HEADERS=${{ secrets.OTEL_EXPORTER_OTLP_HEADERS }}
```

For `deploy-mcp-server` and `deploy-calendar-server`, append the same two variables to their respective `--set-env-vars=` lines.

(`OTEL_SERVICE_NAME` is not set via env var here — each service already sets its service name explicitly in code via `setup_tracing("strides-backend")` / `setup_tracing("strides-fit-server")` / `setup_tracing("strides-calendar-server")`, so there's nothing to configure per-deployment for that part.)

- [ ] **Step 4: Commit**

```bash
git add .env.example .github/workflows/deploy.yml
git commit -m "chore: wire OTel OTLP exporter env vars into Cloud Run deploy"
```

Note: this step's changes only take effect on the next push to `main` that triggers the deploy workflow — actual deployment/verification happens in Task 8, not here.

---

### Task 8: Verify traces land in Grafana Tempo end-to-end

**Files:** None modified — this is a manual verification task.

- [ ] **Step 1: Push to `main` (or merge this branch) to trigger `.github/workflows/deploy.yml`**

Confirm via `gh run watch` or the Actions tab that all three `deploy-*` jobs succeed.

- [ ] **Step 2: Generate a real request that touches all three services**

From the deployed frontend (or `curl` against the backend with a valid session cookie), send a chat message that triggers at least one MCP tool call, e.g. "what's my weekly mileage" (hits `fit_server`) or "plan a run for Saturday" (hits `calendar_server`).

- [ ] **Step 3: Query Grafana Cloud Tempo for the trace**

In Grafana Cloud → Explore → Tempo data source, search by service name `strides-backend` over the last 5 minutes. Open the most recent trace.

Expected: one trace tree containing a `POST /chat` (or relevant route) span from `strides-backend`, a nested `chat.process_query` span, a nested `chat.tool_call.<name>` span, and — as a child of that — a `mcp.tool.<name>` span whose service is `strides-fit-server` or `strides-calendar-server`. All spans share one trace ID.

- [ ] **Step 4: If the MCP-server span is missing or shows as a separate trace**

This means context propagation (Task 3/5/6) isn't linking correctly — check that `ctx.request_context.request.headers` actually contains `traceparent` in production. Add a temporary debug log in `_parent_context_from` that logs **only** the `traceparent` value — e.g. `logging.info("traceparent: %s", request.headers.get("traceparent"))` — never the full `dict(request.headers)`, since that also contains the `Authorization` bearer token. Redeploy, re-test, then remove the log once confirmed. Do not mark this task done until spans are confirmed joined.

---

## Self-Review Notes

- **Spec coverage:** Implements the spec's "Instrumentation scope" decision (backend + both MCP servers) in full. Deliberately does not touch: Grafana dashboards for manual viewing, the cron bug-triage agent, sampling/retention config, or latency-based detection — all explicitly out of scope per the spec or deferred as open items for a later plan.
- **Placeholder scan:** No TBD/TODO markers; every step has concrete code or an exact command. Tasks 5 and 6 ask the implementer to read the current file before writing code (since those files evolve independently of this plan) but specify the exact pattern and wrapping to apply — not a vague "add tracing" instruction.
- **Type consistency:** `setup_tracing`, `inject_traceparent`, `extract_context` (Task 1) are used with identical signatures in Tasks 2–6. Span naming convention (`chat.process_query`, `chat.tool_call.<name>`, `mcp.tool.<name>`) is consistent across backend and both MCP servers for easy filtering in Grafana.
