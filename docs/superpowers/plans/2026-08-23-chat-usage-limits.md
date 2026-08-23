# Chat Usage Limits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protect the Anthropic API key from cost abuse now that the app is publicly reachable (Google OAuth consent screen is "In production", unverified) by capping non-allowlisted users to a lifetime 50,000-token budget and a 500-character input limit, while exempting a small allowlist of trusted emails entirely.

**Architecture:** A new `tokens_used` column on the `users` table tracks cumulative Anthropic token spend per user, checked in `POST /chat` before any Anthropic call is made. `process_query` (in `chat_service.py`) is extended to accumulate `usage.input_tokens + usage.output_tokens` across every Claude API call in its tool-use loop via an out-param dict, so the route can persist the total after the stream finishes. A 500-character cap on the incoming message is enforced in the same route, before the budget check. Both rejections return distinct, non-streaming JSON error responses so the frontend can render fixed, simple messages instead of attempting to stream.

**Tech Stack:** FastAPI, psycopg (Postgres/Supabase), pytest, Next.js/React, vitest (frontend tests — confirm exact runner in `frontend/tests/` before writing).

**Spec:** This plan's spec is this document's Goal/Architecture sections plus the constraints below — there is no separate spec doc, this was scoped directly in conversation.

## Global Constraints

- Token budget limit: **50,000 tokens** (lifetime, per user), configurable via env var `TOKEN_BUDGET_LIMIT` (default `50000`).
- Allowlisted emails are fully exempt from both the token budget and the character limit check, via env var `UNRESTRICTED_EMAILS` (comma-separated, e.g. `a@example.com,b@example.com`).
- Character limit: **500 characters** on `ChatRequest.message`, enforced server-side (frontend `maxLength` is a UX nicety only, not a substitute).
- Both limit violations return **non-streaming** JSON responses with a distinguishable machine-readable `error` code, not a raw 500/plain string, so the frontend can branch on them.
- No per-message or "remaining count" UI — only a fixed message shown once the limit is actually hit.
- This is a lifetime cap, not a rolling/daily window — no reset logic.

---

### Task 1: `tokens_used` column and DB helpers

**Files:**
- Modify: `data/db.py:91-105` (schema block inside `init_db()`), and after `update_avatar_path` (`data/db.py:141-145`) to add two new functions
- Test: `tests/data/test_db.py`

**Interfaces:**
- Produces: `db.get_tokens_used(user_id: str) -> int`, `db.increment_tokens_used(user_id: str, amount: int) -> None`

- [ ] **Step 1: Write the failing tests**

Add to `tests/data/test_db.py` (check the file's existing fixtures for how a test user is created/torn down — mirror that pattern; if it doesn't already exist, follow the pattern in `tests/backend/routes/test_chat.py`'s `_session_cookie_for_new_user`, using `find_or_create_user`):

```python
def test_get_tokens_used_defaults_to_zero():
    user_id = find_or_create_user("tokens-test@example.com", "google-sub-tokens", "Tokens Test")
    assert get_tokens_used(user_id) == 0


def test_increment_tokens_used_accumulates():
    user_id = find_or_create_user("tokens-test2@example.com", "google-sub-tokens2", "Tokens Test 2")
    increment_tokens_used(user_id, 1200)
    increment_tokens_used(user_id, 300)
    assert get_tokens_used(user_id) == 1500
```

Add the needed imports at the top of the test file: `from data.db import find_or_create_user, get_tokens_used, increment_tokens_used` (merge with existing imports rather than duplicating).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/data/test_db.py -k tokens_used -v`
Expected: FAIL with `ImportError` or `AttributeError: module 'data.db' has no attribute 'get_tokens_used'`

- [ ] **Step 3: Add the column and implement the functions**

In `data/db.py`, inside `init_db()`, add alongside the other `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` lines (after line 105):

```python
        conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS tokens_used INTEGER NOT NULL DEFAULT 0"
        )
```

After `update_avatar_path` (after line 145), add:

```python
def get_tokens_used(user_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT tokens_used FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    return row[0] if row is not None else 0


def increment_tokens_used(user_id: str, amount: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET tokens_used = tokens_used + %s WHERE id = %s",
            (amount, user_id),
        )
        conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/data/test_db.py -k tokens_used -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add data/db.py tests/data/test_db.py
git commit -m "feat(db): add tokens_used column and get/increment helpers"
```

---

### Task 2: Accumulate token usage in `process_query`

**Files:**
- Modify: `backend/services/chat_service.py:117-212` (the `process_query` function)
- Test: `tests/backend/services/test_chat_service.py`

**Interfaces:**
- Consumes: nothing new from Task 1 directly (Task 3 wires the DB call)
- Produces: `process_query(user_id: str, messages: list[dict], usage: dict | None = None)` — when `usage` is passed, the function mutates it in place, setting/accumulating `usage["input_tokens"]` and `usage["output_tokens"]` across every Claude API call made during the tool-use loop (there can be more than one call per turn when tools are used). Callers read `usage["input_tokens"] + usage["output_tokens"]` after the generator is fully exhausted.

- [ ] **Step 1: Write the failing test**

Check `tests/backend/services/test_chat_service.py` for how `process_query` is currently tested (it likely mocks `client.messages.stream` via `backend.agent.client`/`model`). Add a test that follows the same mocking pattern but asserts on the `usage` out-param:

```python
async def test_process_query_accumulates_usage_across_tool_loop(monkeypatch):
    # Simulate two API calls: first returns a tool_use (forcing a second call),
    # second returns a final text response. Reuse this file's existing helper(s)
    # for constructing a fake stream/response if present; otherwise construct
    # minimal fakes matching the shape process_query reads:
    #   response.usage.input_tokens, response.usage.output_tokens,
    #   response.usage.cache_creation_input_tokens, response.usage.cache_read_input_tokens,
    #   response.stop_reason, response.content (list of blocks with .type/.text/.id/.name/.input)

    usage = {}
    async for _ in process_query("user-1", [{"role": "user", "content": "hi"}], usage=usage):
        pass

    assert usage["input_tokens"] == <sum of both calls' input_tokens>
    assert usage["output_tokens"] == <sum of both calls' output_tokens>
```

Replace the placeholder assertions with concrete numbers once you've written the fakes — pick e.g. call 1: `input_tokens=100, output_tokens=20`, call 2: `input_tokens=150, output_tokens=40`, so the test asserts `usage["input_tokens"] == 250` and `usage["output_tokens"] == 60`. Base the fake `client.messages.stream` construction on however the existing tests in this file already fake it (look for `AsyncMock`/`MagicMock` usage around `stream.get_final_message` and `stream.text_stream` before writing this from scratch — reuse the existing helper if one exists).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/services/test_chat_service.py -k accumulates_usage -v`
Expected: FAIL — `usage` dict stays empty since `process_query` doesn't accept/populate it yet.

- [ ] **Step 3: Implement usage accumulation**

In `backend/services/chat_service.py`, change the signature (line 117):

```python
async def process_query(user_id: str, messages: list[dict], usage: dict | None = None):
```

Update the docstring to mention the new parameter. Inside the `while True:` loop, right after the existing `generation.update(...)` call (after line 186, still inside the `with generation:` block scope — i.e., right after `response = await stream.get_final_message()` has run and `response` is available), add:

```python
                    if usage is not None:
                        usage["input_tokens"] = (
                            usage.get("input_tokens", 0) + response.usage.input_tokens
                        )
                        usage["output_tokens"] = (
                            usage.get("output_tokens", 0) + response.usage.output_tokens
                        )
```

This runs on every iteration of the loop (both the final answer and any intermediate tool-use calls), so multi-tool-call turns accumulate correctly.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backend/services/test_chat_service.py -k accumulates_usage -v`
Expected: PASS

Also re-run the full file to confirm no regressions from the signature change:

Run: `uv run pytest tests/backend/services/test_chat_service.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/chat_service.py tests/backend/services/test_chat_service.py
git commit -m "feat(chat): accumulate Claude token usage across tool-use loop"
```

---

### Task 3: Enforce character limit and token budget in `POST /chat`

**Files:**
- Modify: `backend/routes/chat.py:1-56`
- Test: `tests/backend/routes/test_chat.py`

**Interfaces:**
- Consumes: `db.get_tokens_used(user_id)`, `db.increment_tokens_used(user_id, amount)` (Task 1); `process_query(user_id, messages, usage=...)` (Task 2)
- Produces: `POST /chat` now returns `400 {"error": "message_too_long"}` when `len(request.message) > 500` (for non-allowlisted users — see step 3 for exact placement), and `403 {"error": "budget_exceeded"}` when the user's `tokens_used >= TOKEN_BUDGET_LIMIT` and their email is not in `UNRESTRICTED_EMAILS`. Neither check applies to allowlisted emails. On success, `tokens_used` is incremented by the turn's total after the stream completes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/backend/routes/test_chat.py`, reusing the existing `client`/`_session_cookie_for_new_user` fixtures:

```python
def test_post_chat_rejects_message_over_500_chars(client):
    cookies = _session_cookie_for_new_user(client)
    response = client.post("/chat", json={"message": "x" * 501}, cookies=cookies)
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "message_too_long"


def test_post_chat_rejects_when_budget_exceeded(client, monkeypatch):
    from backend.routes import chat as chat_route

    monkeypatch.setenv("TOKEN_BUDGET_LIMIT", "1000")
    cookies = _session_cookie_for_new_user(client)

    import data.db as db
    from data.db import get_connection

    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET tokens_used = 1000 WHERE email = %s",
            ("runner@example.com",),
        )
        conn.commit()

    response = client.post("/chat", json={"message": "hi"}, cookies=cookies)
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "budget_exceeded"


def test_post_chat_allowlisted_email_bypasses_budget_and_length(client, monkeypatch):
    monkeypatch.setenv("TOKEN_BUDGET_LIMIT", "1000")
    monkeypatch.setenv("UNRESTRICTED_EMAILS", "runner@example.com")
    cookies = _session_cookie_for_new_user(client)

    from data.db import get_connection

    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET tokens_used = 999999 WHERE email = %s",
            ("runner@example.com",),
        )
        conn.commit()

    response = client.post("/chat", json={"message": "x" * 501}, cookies=cookies)
    assert response.status_code == 200


def test_post_chat_increments_tokens_used_after_reply(client, monkeypatch):
    from backend.routes import chat as chat_route

    async def fake_process_query(user_id, messages, usage=None):
        if usage is not None:
            usage["input_tokens"] = 100
            usage["output_tokens"] = 50
        for chunk in ["mocked ", "reply"]:
            yield chunk

    monkeypatch.setattr(chat_route, "process_query", fake_process_query)
    cookies = _session_cookie_for_new_user(client)

    response = client.post("/chat", json={"message": "hi"}, cookies=cookies)
    assert response.status_code == 200

    import data.db as db
    from data.db import get_connection

    with get_connection() as conn:
        row = conn.execute(
            "SELECT tokens_used FROM users WHERE email = %s", ("runner@example.com",)
        ).fetchone()
    assert row[0] == 150
```

Note: the existing `client` fixture (`tests/backend/routes/test_chat.py:27-55`) already monkeypatches `chat_route.process_query` with a two-arg fake (`fake_process_query(user_id, messages)`). Once Task 3's implementation calls `process_query(..., usage=usage)`, that existing fixture-level fake needs a `usage=None` param added too, or every existing test in this file will break on an unexpected-kwarg TypeError. Update it in the same step:

```python
    async def fake_process_query(user_id, messages, usage=None):
        for chunk in ["mocked ", "reply"]:
            yield chunk
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/backend/routes/test_chat.py -v`
Expected: the four new tests FAIL (no 400/403 behavior yet, `tokens_used` never incremented); pre-existing tests should still PASS once the fixture's `fake_process_query` signature is updated in this same step (do that edit now, not later, so you have an accurate baseline).

- [ ] **Step 3: Implement the checks**

Rewrite `backend/routes/chat.py`:

```python
import json
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import data.db as db
from backend.dependencies import require_user
from backend.services.chat_service import (
    LOCAL_TOOL_SCHEMAS,
    _build_system_prompt,
    process_query,
)
from backend.services.mcp_client import (
    HEALTH_SERVER_URL,
    get_tool_schemas,
    open_mcp_session,
)
from backend.services.summarization_service import maybe_fold

router = APIRouter()

MAX_MESSAGE_CHARS = 500


class ChatRequest(BaseModel):
    message: str


def _unrestricted_emails() -> set[str]:
    raw = os.environ.get("UNRESTRICTED_EMAILS", "")
    return {e.strip() for e in raw.split(",") if e.strip()}


def _token_budget_limit() -> int:
    return int(os.environ.get("TOKEN_BUDGET_LIMIT", "50000"))


@router.post("/chat")
async def chat(request: ChatRequest, user_id: str = Depends(require_user)):
    from backend.agent import SYSTEM_PROMPT

    email, _, _, _ = db.get_user(user_id)
    is_unrestricted = email in _unrestricted_emails()

    if not is_unrestricted and len(request.message) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=400, detail={"error": "message_too_long"})

    if not is_unrestricted and db.get_tokens_used(user_id) >= _token_budget_limit():
        raise HTTPException(status_code=403, detail={"error": "budget_exceeded"})

    db.save_message(user_id, "user", request.message)

    summary = db.get_conversation_summary(user_id)
    cursor = summary["through_message_id"] if summary else 0
    rows = db.get_messages_since(user_id, after_id=cursor)

    system_prompt = _build_system_prompt(SYSTEM_PROMPT, user_id)

    async with open_mcp_session(user_id, server_url=HEALTH_SERVER_URL) as session:
        tools = await get_tool_schemas(session) + LOCAL_TOOL_SCHEMAS

    rows = await maybe_fold(user_id, system_prompt, rows, tools)

    messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    usage: dict = {}

    async def event_stream():
        full_reply = ""
        async for chunk in process_query(user_id, messages, usage=usage):
            full_reply += chunk
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        db.save_message(user_id, "assistant", full_reply)
        if not is_unrestricted:
            total = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            db.increment_tokens_used(user_id, total)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/chat/history")
def get_chat_history(
    before_id: int | None = None, limit: int = 20, user_id: str = Depends(require_user)
):
    messages, has_more = db.get_messages(user_id, before_id=before_id, limit=limit)
    return {"messages": messages, "has_more": has_more}
```

Note: `is_unrestricted` also gates the token-increment step — an allowlisted user's usage is never persisted, so their `tokens_used` never drifts from 0 and the budget check stays consistent if they're ever removed from the allowlist later.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/backend/routes/test_chat.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/chat.py tests/backend/routes/test_chat.py
git commit -m "feat(chat): enforce 500-char limit and 50k token budget with allowlist bypass"
```

---

### Task 4: Frontend — surface both limit errors as fixed messages

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/chat-screen.tsx`
- Modify: `frontend/messages/en.json:32-37`, `frontend/messages/de.json` (same block)
- Test: `frontend/tests/chat-screen.test.tsx`

**Interfaces:**
- Consumes: backend error shape from Task 3 — `400 {"detail": {"error": "message_too_long"}}`, `403 {"detail": {"error": "budget_exceeded"}}`
- Produces: `ApiError` class exported from `frontend/lib/api.ts` with `status: number` and `body: unknown` fields, thrown by both `apiFetch` and `apiStream` instead of the current generic `Error`

- [ ] **Step 1: Write the failing tests**

Check `frontend/tests/chat-screen.test.tsx` for its existing mocking pattern (how it currently mocks `apiStream`/`fetch`) before writing these — mirror that exactly. Add:

```tsx
it("renders the budget-exceeded message as a normal coach bubble and disables input", async () => {
  // Mock apiStream (or the underlying fetch, matching this file's existing pattern)
  // to reject with `new ApiError(403, { error: "budget_exceeded" })`.
  // ... arrange per this file's existing setup ...

  // send a message via the input + send button, per this file's existing interaction pattern
  // assert the fixed copy appears as message content (not a separate error line):
  expect(screen.getByText(/usage limit/i)).toBeInTheDocument();
  // assert the input and send button are now disabled:
  expect(screen.getByPlaceholderText(/ask about your training/i)).toBeDisabled();
  expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
});

it("shows the existing send-failed error line when the message is too long, input stays enabled", async () => {
  // Mock apiStream to reject with new ApiError(400, { error: "message_too_long" })
  // this reuses the existing generic sendFailed copy/line, not a distinct message:
  expect(screen.getByText(/couldn't send your message/i)).toBeInTheDocument();
  // input must stay usable — this is a recoverable error, not a dead-end:
  expect(screen.getByPlaceholderText(/ask about your training/i)).not.toBeDisabled();
});

it("caps the input field at 500 characters", () => {
  // render, grab the input by its existing test id/role (per this file's existing queries),
  // and assert it has maxLength={500} — either via the DOM attribute or by typing >500
  // chars and asserting the value length stays at 500.
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- chat-screen` (confirm exact test command from `frontend/package.json` scripts before running — use whatever this project already uses)
Expected: FAIL — `ApiError` doesn't exist yet, no budget/length copy rendered, no `maxLength` on the input.

- [ ] **Step 3: Implement**

In `frontend/lib/api.ts`, add the error class and use it in both functions:

```ts
export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(`Request failed: ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function parseErrorBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorBody(response));
  }

  return response.json() as Promise<T>;
}

export async function apiStream(
  path: string,
  options: RequestInit,
  onChunk: (text: string) => void
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
    throw new ApiError(response.status, await parseErrorBody(response));
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

In `frontend/messages/en.json`, extend the `chat` block (line 32-37):

```json
  "chat": {
    "coachName": "Coach",
    "syncedStatus": "Synced with Google Health",
    "placeholder": "Ask about your training...",
    "sendFailed": "Couldn't send your message. Try again.",
    "budgetExceeded": "You've reached your usage limit for this app."
  },
```

In `frontend/messages/de.json`, extend the same block with German copy:

```json
  "chat": {
    "coachName": "Coach",
    "syncedStatus": "Mit Google Health synchronisiert",
    "placeholder": "Frag etwas zu deinem Training...",
    "sendFailed": "Nachricht konnte nicht gesendet werden. Versuch es erneut.",
    "budgetExceeded": "Du hast dein Nutzungslimit für diese App erreicht."
  },
```

In `frontend/components/chat-screen.tsx`:

1. Import `ApiError` alongside the existing `apiFetch`/`apiStream` import (line 13):

```tsx
import { ApiError, apiFetch, apiStream } from "@/lib/api";
```

2. Add a new piece of state near the other `useState` declarations (after line 40). This only needs to track whether the budget dead-end has been hit, since that's the only case that disables input — `message_too_long` reuses the existing `sendError` line and never blocks anything:

```tsx
  const [budgetExceeded, setBudgetExceeded] = useState(false);
```

3. In `handleSend`, branch the catch block on `ApiError`. Replace the existing `try { ... } catch { ... }` (lines 93-111):

```tsx
    try {
      await apiStream("/chat", { method: "POST", body: JSON.stringify({ message: trimmed, locale }) }, (chunk) => {
        lastChunkAtRef.current = Date.now();
        setIsThinking(false);
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, text: last.text + chunk };
          return next;
        });
      });
    } catch (err) {
      const code =
        err instanceof ApiError && err.body && typeof err.body === "object" && "error" in err.body
          ? (err.body as { error: string }).error
          : null;

      if (code === "budget_exceeded") {
        // Fill the already-added coach placeholder bubble with the fixed
        // message instead of removing it — renders exactly like a normal
        // coach reply, no separate error line.
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], text: t("budgetExceeded") };
          return next;
        });
        setBudgetExceeded(true);
      } else {
        // message_too_long and any other failure: recoverable, so drop the
        // empty placeholder bubble and show the existing small error line.
        setMessages((prev) => prev.filter((m) => m.id !== coachMessageId));
        setSendError(true);
      }
    } finally {
      clearInterval(thinkingTimer);
      setIsThinking(false);
      setIsSending(false);
    }
```

Note: this collapses `message_too_long` into the same visible treatment as any other send failure (the existing `sendFailed` copy/line) rather than a distinct message — simplest option, and still accurate since either way the fix is "try again with a shorter message." If you'd rather it say something more specific than "Couldn't send your message," add a second boolean and a second copy key following the same pattern as `budgetExceeded` below — not done here to keep this minimal per your "keep it simple" steer.

4. Render the existing error line unchanged (line 182) — no new line needed, since the budget case now renders as a bubble instead:

```tsx
      {sendError && <div className="px-4 pt-2 text-xs text-danger lg:px-0">{t("sendFailed")}</div>}
```

5. Add `maxLength={500}` to the `<Input>` and disable both the input and send button once `budgetExceeded` is true (lines 184-193):

```tsx
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t("placeholder")}
          maxLength={500}
          disabled={budgetExceeded}
          className="h-11 rounded-2xl border-border bg-card px-5 text-primary placeholder:text-muted-light lg:h-12"
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
        />
        <Button aria-label="send" onClick={handleSend} disabled={isSending || budgetExceeded} className="h-11 w-11 rounded-full bg-primary p-0 lg:h-12 lg:w-12">
          <ArrowRight size={17} color="#F6F4EF" strokeWidth={2} />
        </Button>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- chat-screen`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/components/chat-screen.tsx frontend/messages/en.json frontend/messages/de.json frontend/tests/chat-screen.test.tsx
git commit -m "feat(chat): show fixed messages for budget-exceeded and message-too-long, cap input at 500 chars"
```

---

### Task 5: Set production env vars

**Files:**
- Modify: `.github/workflows/deploy.yml` (backend Cloud Run deploy step — add `TOKEN_BUDGET_LIMIT` and `UNRESTRICTED_EMAILS` as literal env vars, matching how `GOOGLE_LOGIN_CALLBACK_URL` is already set per the project's CLAUDE.md notes)

**Interfaces:**
- Consumes: nothing (deployment-only, no code interface)

- [ ] **Step 1: Locate the existing backend Cloud Run env var block**

Open `.github/workflows/deploy.yml` and find the `gcloud run deploy` step for the backend service — it already sets `GOOGLE_LOGIN_CALLBACK_URL`/`GOOGLE_HEALTH_CALLBACK_URL` as literal values per the project's deployment history.

- [ ] **Step 2: Add the two new env vars**

Add `TOKEN_BUDGET_LIMIT=50000` and `UNRESTRICTED_EMAILS=<your comma-separated allowlist emails>` to that same `--set-env-vars` list, in the same format as the existing entries. Do not commit real personal emails to a public-facing plan doc — fill in the actual addresses directly in the workflow file, not here.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "chore(deploy): set TOKEN_BUDGET_LIMIT and UNRESTRICTED_EMAILS for backend Cloud Run service"
```

Note: this deploy will not take effect until pushed to `main` and the workflow runs — confirm with the user before pushing, per this repo's usual review flow.
