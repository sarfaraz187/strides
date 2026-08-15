# Streaming Chat Responses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project override:** This repo's `CLAUDE.md` defines its own per-task loop (Claude writes the failing test, user implements, Claude reviews the diff, then tests are run green). That loop takes precedence over the generic subagent-driven/executing-plans flow — see the Execution Handoff section at the bottom.

**Goal:** Stream Claude's reply to the browser token-by-token instead of blocking until the full response is generated.

**Architecture:** `process_query` becomes an async generator yielding text chunks (using `client.messages.stream()` instead of `.create()`). The `/chat` route wraps that generator in a `StreamingResponse` emitting Server-Sent Events (SSE), and persists the full assistant message to Postgres only after the stream completes. The frontend reads the SSE body via the Fetch Streams API and appends each chunk to the in-progress message bubble as it arrives. During tool-call gaps (no text chunks arriving because Claude is waiting on `get_recent_runs`/`save_memory`/etc.), the frontend shows a generic "thinking" indicator based purely on elapsed time since the last chunk — no backend changes, no tool-specific messaging (that's a deliberate follow-up, not part of this plan).

**Tech Stack:** FastAPI `StreamingResponse`, Anthropic SDK `client.messages.stream()`, SSE (`text/event-stream`), browser `ReadableStream`/`TextDecoder`.

## Global Constraints

- Tool-calling loop in `process_query` must keep working: Claude can still request `get_weekly_stats`/`get_recent_runs`/`save_memory` mid-conversation, and intermediate tool turns must still be persisted via `db.save_message` (existing behavior in `backend/services/chat_service.py:107,111`).
- The final assistant message must still be saved to Postgres exactly once per turn, matching current `db.save_message(user_id, "assistant", reply)` call in `backend/routes/chat.py:40`.
- Existing Langfuse `observe()`/`start_as_current_observation()` instrumentation in `process_query` must not be silently dropped — the streaming variant still records model, input, output, and usage.
- No new dependencies — `client.messages.stream()` ships in the `anthropic` SDK already installed.

---

## File Structure

- Modify `backend/services/chat_service.py` — `process_query` changes from `async def -> str` to `async def -> AsyncIterator[str]` (an async generator). `call_tools` and `_build_system_prompt` are unchanged.
- Modify `backend/routes/chat.py` — `/chat` route returns `StreamingResponse` over SSE-framed chunks instead of a JSON dict.
- Modify `tests/backend/services/test_chat_service.py` — existing tests mock `client.messages.create`; they must mock `client.messages.stream` (an async context manager) instead, and drain the generator with `async for`.
- Modify `tests/backend/routes/test_chat.py` — the `process_query` mock changes from `AsyncMock(return_value="mocked reply")` to something that yields chunks; assertions change from parsing one JSON body to parsing SSE frames.
- Modify `frontend/lib/api.ts` — add a new `apiStream` helper alongside `apiFetch`, since `apiFetch` always calls `response.json()`.
- Modify `frontend/components/chat-screen.tsx` — replace the `useMutation`-based `sendMessage` with a hand-rolled async function that reads the SSE stream and updates the in-progress coach message on every chunk.
- Modify `frontend/tests/chat-screen.test.tsx` — update the mocked fetch to return a streamed body instead of a JSON response.

---

### Task 1: `process_query` becomes a streaming async generator

**Files:**
- Modify: `backend/services/chat_service.py:62-111`
- Test: `tests/backend/services/test_chat_service.py`

**Interfaces:**
- Consumes: `backend.agent.client` (Anthropic SDK client), `backend.agent.model`, `backend.agent.SYSTEM_PROMPT` — unchanged.
- Produces: `process_query(user_id: str, messages: list[dict]) -> AsyncIterator[str]` — an async generator. Callers must do `async for chunk in process_query(...)`. The generator's chunks are plain text deltas (not JSON, not SSE-framed — that framing happens in Task 2). `call_tools(user_id, session, content_blocks) -> list[dict]` signature is unchanged.

The Anthropic SDK's `client.messages.stream(...)` returns an async context manager exposing `.text_stream` (an async iterator of text deltas) and `.get_final_message()` (awaitable, returns the same shape as today's `.create()` response — has `.content` and `.stop_reason`). This lets the existing tool-calling loop structure survive: the loop still inspects `stop_reason` and `content` to decide whether to call tools again, it just gets there by draining a stream instead of one `await`.

- [x] **Step 1: Write the failing tests**

Replace the two tests in `tests/backend/services/test_chat_service.py` that call `mock_client.messages.create` for `process_query` — `test_process_query_merges_local_tool_schemas_with_mcp_tools`, `test_process_query_injects_memories_into_system_prompt`, `test_process_query_injects_conversation_summary_into_system_prompt`, `test_process_query_omits_summary_section_when_none_exists`, and `test_process_query_persists_intermediate_tool_turns` — with versions that mock `.stream()` instead of `.create()`, and drain the async generator. Add a helper at the top of the file:

```python
def _mock_stream(final_response, text_chunks: list[str]):
    """Build a fake client.messages.stream(...) async context manager."""

    class FakeStreamCM:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        @property
        async def text_stream(self):
            for chunk in text_chunks:
                yield chunk

        async def get_final_message(self):
            return final_response

    return MagicMock(return_value=FakeStreamCM())
```

Note: `text_stream` must be an async generator, not a coroutine returning one — the SDK exposes it as an async-iterable attribute you use with `async for chunk in stream.text_stream`. Fix the helper so `text_stream` is a plain method/property returning an async generator directly (no `async def` on the property getter itself — properties can't be async). Use this shape instead:

```python
def _mock_stream(final_response, text_chunks: list[str]):
    class FakeStreamCM:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def _gen(self):
            for chunk in text_chunks:
                yield chunk

        def __init__(self):
            self.text_stream = self._gen()

        async def get_final_message(self):
            return final_response

    return MagicMock(return_value=FakeStreamCM())
```

Rewrite `test_process_query_merges_local_tool_schemas_with_mcp_tools`:

```python
def test_process_query_merges_local_tool_schemas_with_mcp_tools():
    from backend.services.chat_service import LOCAL_TOOL_SCHEMAS, process_query

    open_mcp_session, mock_session = _mock_session(["get_weekly_stats"])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]

    with (
        patch("backend.services.chat_service.open_mcp_session", open_mcp_session),
        patch("backend.services.chat_service.db.get_memories", return_value=[]),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=None,
        ),
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.stream = _mock_stream(fake_response, ["done"])

        async def drain():
            chunks = []
            async for chunk in process_query("user-123", [{"role": "user", "content": "hi"}]):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(drain())

        assert "".join(chunks) == "done"
        called_tools = mock_client.messages.stream.call_args.kwargs["tools"]
        local_names = {t["name"] for t in LOCAL_TOOL_SCHEMAS}
        called_names = {t["name"] for t in called_tools}
        assert local_names.issubset(called_names)
        assert "get_weekly_stats" in called_names
```

Apply the same pattern (swap `.create` for `.stream` via `_mock_stream`, drain with the `drain()` helper, assert on joined chunks and on `system_prompt = mock_client.messages.stream.call_args.kwargs["system"]`) to `test_process_query_injects_memories_into_system_prompt`, `test_process_query_injects_conversation_summary_into_system_prompt`, and `test_process_query_omits_summary_section_when_none_exists`.

Rewrite `test_process_query_persists_intermediate_tool_turns` (needs two stream calls, matching the two `.create()` calls it used before):

```python
def test_process_query_persists_intermediate_tool_turns():
    from backend.services.chat_service import process_query

    open_mcp_session, mock_session = _mock_session(["get_weekly_stats"])
    mock_session.call_tool.side_effect = lambda name, args: "42km this week"

    tool_use_block = MagicMock(type="tool_use", id="call-1")
    tool_use_block.name = "get_weekly_stats"
    tool_use_block.input = {}
    tool_use_block.model_dump.return_value = {
        "type": "tool_use",
        "id": "call-1",
        "name": "get_weekly_stats",
        "input": {},
    }
    tool_call_response = MagicMock(stop_reason="tool_use", content=[tool_use_block])

    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    final_response = MagicMock(stop_reason="end_turn", content=[text_block])

    with (
        patch("backend.services.chat_service.open_mcp_session", open_mcp_session),
        patch("backend.services.chat_service.db.get_memories", return_value=[]),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=None,
        ),
        patch("backend.services.chat_service.db.save_message") as mock_save_message,
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.stream = MagicMock(
            side_effect=[
                _mock_stream(tool_call_response, [])(),
                _mock_stream(final_response, ["done"])(),
            ]
        )

        async def drain():
            chunks = []
            async for chunk in process_query("user-123", [{"role": "user", "content": "hi"}]):
                chunks.append(chunk)
            return "".join(chunks)

        reply = asyncio.run(drain())

    assert reply == "done"
    assert mock_save_message.call_count == 2
    mock_save_message.assert_any_call(
        "user-123",
        "assistant",
        [{"type": "tool_use", "id": "call-1", "name": "get_weekly_stats", "input": {}}],
    )
    mock_save_message.assert_any_call(
        "user-123",
        "user",
        [{"type": "tool_result", "tool_use_id": "call-1", "content": "42km this week"}],
    )
```

`test_call_tools_still_routes_unknown_tool_names_to_mcp_session`, `test_save_memory_tool_is_registered_locally`, `test_save_memory_tool_writes_to_db`, `test_call_tools_truncates_large_tool_results`, and `test_call_tools_leaves_small_tool_results_untouched` are untouched — they exercise `call_tools`/`LOCAL_TOOLS`, not `process_query`.

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/backend/services/test_chat_service.py -v`
Expected: the rewritten `test_process_query_*` tests FAIL — `process_query` currently returns a coroutine yielding a `str`, so `async for chunk in process_query(...)` raises `TypeError: 'async for' requires an object with __aiter__ method, got coroutine`. The untouched `call_tools`/`LOCAL_TOOLS` tests still PASS.

- [x] **Step 3: Implement — user writes the code**

Per this project's workflow, the user implements this step; the guidance below is what to aim for, not code to paste unreviewed:

```python
async def process_query(user_id: str, messages: list[dict]):
    """Call Claude, executing any requested tools, until it gives a final answer.

    Yields text chunks as they stream in. The final assistant text is the
    concatenation of every chunk yielded across the whole call.
    """
    from backend.agent import SYSTEM_PROMPT, client, model

    with propagate_attributes(user_id=user_id):
        system_prompt = _build_system_prompt(SYSTEM_PROMPT, user_id)

        async with open_mcp_session(user_id) as session:
            tools = await get_tool_schemas(session) + LOCAL_TOOL_SCHEMAS

            while True:
                with langfuse_client.start_as_current_observation(
                    as_type="generation",
                    name="claude-messages-create",
                    model=model,
                    input=messages,
                ) as generation:
                    async with client.messages.stream(
                        model=model,
                        max_tokens=1024,
                        system=system_prompt,
                        tools=tools,
                        tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                        messages=messages,
                    ) as stream:
                        async for text in stream.text_stream:
                            yield text
                        response = await stream.get_final_message()

                    generation.update(
                        output=[block.model_dump() for block in response.content],
                        usage_details={
                            "input": response.usage.input_tokens,
                            "output": response.usage.output_tokens,
                        },
                    )

                content_dicts = [block.model_dump() for block in response.content]
                messages.append({"role": "assistant", "content": content_dicts})

                if response.stop_reason != "tool_use":
                    return

                db.save_message(user_id, "assistant", content_dicts)

                tool_results = await call_tools(user_id, session, response.content)
                messages.append({"role": "user", "content": tool_results})
                db.save_message(user_id, "user", tool_results)
```

Key behavior change to flag during review: when `stop_reason != "tool_use"`, the old code built `reply` by joining only `text` blocks and returned it — callers got the final text exactly once. The new code has already `yield`ed every text chunk during the stream, so on the terminal turn it just `return`s (ending the generator) rather than yielding anything again. Verify no double-yield of the final text.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/services/test_chat_service.py -v`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add backend/services/chat_service.py tests/backend/services/test_chat_service.py
git commit -m "feat: stream process_query text chunks instead of returning full reply"
```

---

### Task 2: `/chat` route streams SSE instead of returning JSON

**Files:**
- Modify: `backend/routes/chat.py:21-42`
- Test: `tests/backend/routes/test_chat.py`

**Interfaces:**
- Consumes: `process_query(user_id, messages) -> AsyncIterator[str]` from Task 1.
- Produces: `POST /chat` now responds `Content-Type: text/event-stream` with a body of repeated `data: {"text": "<chunk>"}\n\n` frames. `GET /chat/history` is unchanged.

- [x] **Step 1: Write the failing tests**

`TestClient` (httpx-based) supports reading streamed bodies. Replace the `process_query` mock and the two assertions that depend on JSON shape in `tests/backend/routes/test_chat.py`:

```python
@pytest.fixture
def client(monkeypatch):
    from backend.agent import app
    from backend.routes import chat as chat_route

    async def fake_process_query(user_id, messages):
        for chunk in ["mocked ", "reply"]:
            yield chunk

    monkeypatch.setattr(chat_route, "process_query", fake_process_query)

    async def fake_maybe_fold(user_id, system_prompt, rows, tools):
        return rows

    monkeypatch.setattr(chat_route, "maybe_fold", fake_maybe_fold)

    @asynccontextmanager
    async def fake_open_mcp_session(user_id):
        yield None

    monkeypatch.setattr(chat_route, "open_mcp_session", fake_open_mcp_session)
    monkeypatch.setattr(chat_route, "get_tool_schemas", AsyncMock(return_value=[]))

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    return TestClient(app)
```

Add a helper and rewrite the two affected tests:

```python
import json


def _collect_sse_text(response) -> str:
    text = ""
    for line in response.text.splitlines():
        if line.startswith("data: "):
            text += json.loads(line[len("data: "):])["text"]
    return text


def test_post_chat_streams_sse_and_persists_full_reply(client):
    cookies = _session_cookie_for_new_user(client)

    response = client.post("/chat", json={"message": "hi"}, cookies=cookies)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert _collect_sse_text(response) == "mocked reply"

    history = client.get("/chat/history", cookies=cookies)
    contents = [m["content"] for m in history.json()["messages"]]
    assert contents == ["mocked reply", "hi"]
```

Delete the old `test_post_chat_persists_user_and_assistant_messages` (superseded by the test above) and update `test_post_chat_calls_maybe_fold_with_rows_since_last_summary` — it already only checks status code and `maybe_fold` call args, so it needs no change beyond the fixture swap above. `test_post_chat_requires_auth`, `test_get_chat_history_requires_auth`, and `test_get_chat_history_paginates` are unaffected.

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/backend/routes/test_chat.py -v`
Expected: `test_post_chat_streams_sse_and_persists_full_reply` FAILS — the route still returns `{"reply": ...}` as a JSON body with `content-type: application/json`, not an SSE stream.

- [x] **Step 3: Implement — user writes the code**

```python
import json

from fastapi.responses import StreamingResponse


@router.post("/chat")
async def chat(request: ChatRequest, user_id: str = Depends(require_user)):
    from backend.agent import SYSTEM_PROMPT

    db.save_message(user_id, "user", request.message)

    summary = db.get_conversation_summary(user_id)
    cursor = summary["through_message_id"] if summary else 0
    rows = db.get_messages_since(user_id, after_id=cursor)

    system_prompt = _build_system_prompt(SYSTEM_PROMPT, user_id)

    async with open_mcp_session(user_id) as session:
        tools = await get_tool_schemas(session) + LOCAL_TOOL_SCHEMAS

    rows = await maybe_fold(user_id, system_prompt, rows, tools)

    messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    async def event_stream():
        full_reply = ""
        async for chunk in process_query(user_id, messages):
            full_reply += chunk
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        db.save_message(user_id, "assistant", full_reply)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

Note during review: `_build_system_prompt` is called here for the `tools`/`maybe_fold` setup but its result (`system_prompt`) isn't otherwise used by the route — that's pre-existing (`chat.py:31` before this change) and out of scope for this plan, flag it but don't fix it here.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/routes/test_chat.py -v`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add backend/routes/chat.py tests/backend/routes/test_chat.py
git commit -m "feat: stream /chat responses as SSE"
```

---

### Task 3: Frontend reads the SSE stream and renders chunks live

**Files:**
- Create: `frontend/lib/api.ts` (add `apiStream` alongside existing `apiFetch`)
- Modify: `frontend/components/chat-screen.tsx:58-77`
- Test: `frontend/tests/chat-screen.test.tsx`

**Interfaces:**
- Consumes: SSE body produced by Task 2 (`data: {"text": "..."}\n\n` frames).
- Produces: `apiStream(path: string, options: RequestInit, onChunk: (text: string) => void): Promise<void>` in `frontend/lib/api.ts`. `ChatScreen`'s send flow calls it instead of the old `useMutation`/`apiFetch` pair. `ChatScreen` also gains an `isThinking` boolean derived from time-since-last-chunk, rendered as a typing indicator in place of the coach bubble whenever true.

- [x] **Step 1: Write the failing test**

Read `frontend/tests/chat-screen.test.tsx` first to match its existing mocking conventions (it currently mocks `apiFetch`/`fetch` — check whether it mocks the module or global fetch) before writing this test, since the exact mock setup must match the file's established pattern. Add a test asserting the coach bubble updates incrementally:

```tsx
test("renders streamed chunks into the coach bubble as they arrive", async () => {
  const encoder = new TextEncoder();
  const frames = ['data: {"text":"Hel"}\n\n', 'data: {"text":"lo!"}\n\n'];

  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    body: new ReadableStream({
      start(controller) {
        for (const frame of frames) controller.enqueue(encoder.encode(frame));
        controller.close();
      },
    }),
  });

  render(<ChatScreen locale="en" />);
  await userEvent.type(screen.getByPlaceholderText(/.+/), "hi{enter}");

  await waitFor(() => expect(screen.getByText("Hello!")).toBeInTheDocument());
});
```

Adjust the mock/import style (`vi.fn` vs `jest.fn`, how `render`/`screen`/`userEvent` are imported) to match whatever this test file already uses elsewhere — do not introduce a second testing convention into the same file.

Add a second test for the thinking indicator, using fake timers to simulate a gap between chunks (e.g. a tool-call pause):

```tsx
test("shows a thinking indicator during a gap between chunks", async () => {
  vi.useFakeTimers();
  const encoder = new TextEncoder();
  let pushSecondChunk: () => void;

  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"text":"Checking"}\n\n'));
        pushSecondChunk = () => {
          controller.enqueue(encoder.encode('data: {"text":" your runs"}\n\n'));
          controller.close();
        };
      },
    }),
  });

  render(<ChatScreen locale="en" />);
  await userEvent.type(screen.getByPlaceholderText(/.+/), "hi{enter}");

  await vi.advanceTimersByTimeAsync(700); // past THINKING_TIMEOUT_MS with no new chunk
  expect(screen.getByTestId("thinking-indicator")).toBeInTheDocument();

  pushSecondChunk();
  await waitFor(() => expect(screen.queryByTestId("thinking-indicator")).not.toBeInTheDocument());
  vi.useRealTimers();
});
```

Match this to the file's existing timer/mocking conventions (some setups need `vi.useFakeTimers({ shouldAdvanceTime: true })` for streams to keep resolving underneath fake timers — check what the file already does for any existing timer-based test before assuming this exact call works unmodified).

- [x] **Step 2: Run test to verify it fails**

Run: `npm test -- chat-screen.test.tsx` (from `frontend/`)
Expected: FAIL — `sendMessage` currently calls `apiFetch`, which calls `response.json()` on a body that in this test is a `ReadableStream`, not JSON — the test's mocked `fetch` return also lacks a `.json()` method, so the mutation errors out and the coach bubble is never rendered.

- [x] **Step 3: Implement — user writes the code**

Add a thinking-indicator constant and state near the top of `chat-screen.tsx`:

```tsx
const THINKING_TIMEOUT_MS = 600;
```

```tsx
const [isThinking, setIsThinking] = useState(false);
const lastChunkAtRef = useRef(Date.now());
```

Add to `frontend/lib/api.ts`:

```ts
export async function apiStream(
  path: string,
  options: RequestInit,
  onChunk: (text: string) => void,
): Promise<void> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok || !response.body) {
    throw new Error(`Request to ${path} failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const { text } = JSON.parse(line.slice("data: ".length));
      onChunk(text);
    }
  }
}
```

Replace the `sendMessage` mutation and `handleSend` in `chat-screen.tsx`:

```tsx
const [isSending, setIsSending] = useState(false);

async function handleSend() {
  const trimmed = draft.trim();
  if (!trimmed || isSending) return;
  setDraft("");
  setIsSending(true);
  setMessages((prev) => [...prev, { from: "user", text: trimmed }, { from: "coach", text: "" }]);

  lastChunkAtRef.current = Date.now();
  const thinkingTimer = setInterval(() => {
    setIsThinking(Date.now() - lastChunkAtRef.current > THINKING_TIMEOUT_MS);
  }, 200);

  try {
    await apiStream("/chat", { method: "POST", body: JSON.stringify({ message: trimmed, locale }) }, (chunk) => {
      lastChunkAtRef.current = Date.now();
      setIsThinking(false);
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { from: "coach", text: next[next.length - 1].text + chunk };
        return next;
      });
    });
    await queryClient.invalidateQueries({ queryKey: CHAT_HISTORY_QUERY_KEY });
  } finally {
    clearInterval(thinkingTimer);
    setIsThinking(false);
    setIsSending(false);
  }
}
```

In the message-rendering JSX, render the indicator *after* whatever text is already in the bubble, not instead of it — a second tool call mid-answer must not make the partial answer disappear:

```tsx
{msg.from === "coach" ? (
  <>
    <ReactMarkdown>{msg.text}</ReactMarkdown>
    {isThinking && i === allMessages.length - 1 && (
      <span data-testid="thinking-indicator" className="inline-flex gap-1">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-light [animation-delay:-0.2s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-light [animation-delay:-0.1s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-light" />
      </span>
    )}
  </>
) : (
  msg.text
)}
```

Remove the now-unused `useMutation` import if nothing else in the file uses it, and remove the `sendMessage` mutation object entirely. Note during review: the old code cleared `setMessages([])` in `onSuccess` (relying on the invalidated history query to re-supply the message) — the new code leaves the streamed coach bubble in local `messages` state after the history refetch lands, which will likely double-render that message once history includes it. Decide during review whether to clear `messages` after `invalidateQueries` resolves, same as the old `onSuccess` did.

- [x] **Step 4: Run test to verify it passes**

Run: `npm test -- chat-screen.test.tsx` (from `frontend/`)
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/components/chat-screen.tsx frontend/tests/chat-screen.test.tsx
git commit -m "feat: render streamed chat replies chunk-by-chunk in the UI"
```

---

## Self-Review Notes

- **Spec coverage:** backend generator (Task 1) → SSE route (Task 2) → frontend stream consumer (Task 3) covers the full path discussed. Langfuse instrumentation is preserved in Task 1's implementation sketch, not dropped.
- **Type consistency:** `process_query` signature (`AsyncIterator[str]`, no return value) is consistent between Task 1's produces-block and Task 2's route code (`async for chunk in process_query(...)`). `apiStream`'s `onChunk` callback shape matches how Task 3's `handleSend` calls it.
- **Known risk flagged, not silently fixed:** the double-render risk from local `messages` state colliding with the refetched history after `invalidateQueries`, and the pre-existing unused `system_prompt` in the route — both called out inline above rather than fixed as drive-by cleanup, per the "flag, don't silently fix" project rule.

---

## Execution Handoff

This plan follows the project's own per-task loop (see `CLAUDE.md`): for each task, Claude writes the failing test and confirms it fails red, **you** implement the code change, then Claude reviews the diff before moving on. That's the default here — no subagent dispatch needed unless you'd rather use one.

Which would you like:
1. **Project's own loop (recommended, matches CLAUDE.md)** — go task by task, you implement each Step 3 yourself.
2. **Subagent-driven** — I dispatch a fresh subagent per task, review between tasks.
3. **Inline execution** — I implement everything in this session across batched checkpoints.
