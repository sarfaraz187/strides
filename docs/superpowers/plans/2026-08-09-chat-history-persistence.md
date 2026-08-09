# Chat History Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every chat turn (user message + assistant reply) to Postgres and expose a paginated history endpoint, so chat history survives backend restarts and can be displayed back in the UI.

**Architecture:** A new `messages` table is written to as a side-effect inside `POST /chat`, after the existing in-memory-agent-context flow runs unchanged. A new `GET /chat/history` endpoint reads from that table using keyset pagination (cursor = `id`, newest-first). The frontend chat screen loads the latest page on mount and older pages on scroll-up via React Query's `useInfiniteQuery`, reusing the existing markdown renderer.

**Tech Stack:** FastAPI, psycopg (`data/db.py` connection pool pattern), pytest + `TestClient`, Next.js + React Query (frontend).

## Global Constraints

- No retention cap — all messages kept indefinitely (per spec `docs/superpowers/specs/2026-08-09-chat-history-persistence-design.md`).
- Persistence is write-only from the agent's perspective — `backend/agent/conversations` (in-memory) and `backend/services/chat_service.py` are not modified.
- One continuous thread per user — no `conversation_id`, no thread titles.
- `content` stored as raw text/markdown, unmodified.
- `user_id` is `UUID` (matches `users.id`), passed around as `str` in Python (matches existing `data/db.py` convention).
- Per this project's CLAUDE.md workflow: Claude writes the failing test, the user implements the code themselves, Claude reviews the diff, then tests are re-run to confirm green. Steps below are written as if Claude does both for planning completeness, but during actual execution the user does the "write minimal implementation" step.

---

### Task 1: `messages` table + `save_message`/`get_messages` in `data/db.py`

**Files:**
- Modify: `data/db.py` (add table to `init_db()`, add two functions)
- Test: `tests/data/test_db.py`

**Interfaces:**
- Consumes: `get_connection()` (existing), `find_or_create_user()` (existing, for test setup)
- Produces:
  - `save_message(user_id: str, role: str, content: str) -> None`
  - `get_messages(user_id: str, before_id: int | None, limit: int) -> tuple[list[dict], bool]` — each dict is `{"id": int, "role": str, "content": str, "created_at": datetime}`; returns `(messages, has_more)` with `messages` ordered newest-first (descending `id`)

- [x] **Step 1: Write the failing tests**

Add to `tests/data/test_db.py` (import `get_messages, save_message` alongside the existing imports from `data.db`):

```python
def test_init_db_creates_messages_table():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'messages' AND table_schema = 'public'"
        ).fetchall()
    columns = {row[0] for row in result}
    assert columns == {"id", "user_id", "role", "content", "created_at"}


def test_save_message_then_get_messages_round_trips():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    save_message(user_id, "user", "How far did I run this week?")
    save_message(user_id, "assistant", "You ran 12km this week.")

    messages, has_more = get_messages(user_id, before_id=None, limit=20)

    assert has_more is False
    assert [m["role"] for m in messages] == ["assistant", "user"]
    assert [m["content"] for m in messages] == [
        "You ran 12km this week.",
        "How far did I run this week?",
    ]


def test_get_messages_only_returns_requesting_users_messages():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    other_user_id = find_or_create_user("other@example.com", "google-sub-456", "Other Runner")
    save_message(user_id, "user", "mine")
    save_message(other_user_id, "user", "not mine")

    messages, _ = get_messages(user_id, before_id=None, limit=20)

    assert [m["content"] for m in messages] == ["mine"]


def test_get_messages_paginates_with_before_id_cursor():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    for i in range(5):
        save_message(user_id, "user", f"message {i}")

    first_page, first_has_more = get_messages(user_id, before_id=None, limit=2)
    second_page, second_has_more = get_messages(
        user_id, before_id=first_page[-1]["id"], limit=2
    )

    assert [m["content"] for m in first_page] == ["message 4", "message 3"]
    assert first_has_more is True
    assert [m["content"] for m in second_page] == ["message 2", "message 1"]
    assert second_has_more is True


def test_get_messages_has_more_false_on_last_page():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    save_message(user_id, "user", "only message")

    messages, has_more = get_messages(user_id, before_id=None, limit=20)

    assert has_more is False
    assert len(messages) == 1
```

Also update `clean_schema` in `tests/data/test_db.py` to drop the new table:

```python
        conn.execute("DROP TABLE IF EXISTS messages CASCADE")
```//add this line before `conn.execute("DROP TABLE IF EXISTS preferences CASCADE")`

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/test_db.py -k messages -v`
Expected: FAIL with `ImportError` or `AttributeError` (`save_message`/`get_messages` not defined) and the table-columns test failing since the table doesn't exist yet.

- [x] **Step 3: Implement the minimal code**

In `data/db.py`, add the table creation inside `init_db()`, after the `preferences` table block:

```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_user_id_id ON messages (user_id, id DESC)"
        )
```

Add the two functions at the end of `data/db.py`:

```python
def save_message(user_id: str, role: str, content: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (%s, %s, %s)",
            (user_id, role, content),
        )
        conn.commit()


def get_messages(user_id: str, before_id: int | None, limit: int) -> tuple[list[dict], bool]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, created_at FROM messages
            WHERE user_id = %s AND (%s::int IS NULL OR id < %s)
            ORDER BY id DESC
            LIMIT %s
            """,
            (user_id, before_id, before_id, limit + 1),
        ).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    messages = [
        {"id": row[0], "role": row[1], "content": row[2], "created_at": row[3]} for row in rows
    ]
    return messages, has_more
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/data/test_db.py -k messages -v`
Expected: PASS (all 5 new tests)

- [x] **Step 5: Run the full `test_db.py` file to check for regressions**

Run: `pytest tests/data/test_db.py -v`
Expected: PASS (all tests, including pre-existing ones)

---

### Task 2: Wire persistence into `POST /chat` and add `GET /chat/history`

**Files:**
- Modify: `backend/routes/chat.py`
- Test: `tests/backend/routes/test_chat.py` (new file)

**Interfaces:**
- Consumes: `save_message(user_id, role, content) -> None`, `get_messages(user_id, before_id, limit) -> tuple[list[dict], bool]` (from Task 1); `require_user` (existing, `backend/dependencies.py`); `process_query(user_id, messages) -> str` (existing, unchanged)
- Produces: `GET /chat/history?before_id=&limit=` route returning `{"messages": [...], "has_more": bool}`, each message serialized as `{"id": int, "role": str, "content": str, "created_at": str}`

- [x] **Step 1: Write the failing tests**

Create `tests/backend/routes/test_chat.py`:

```python
import base64
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from data.db import create_session, find_or_create_user, get_connection, init_db


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "TOKEN_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    init_db()
    yield
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE email = %s", ("runner@example.com",))
        conn.commit()


@pytest.fixture
def client(monkeypatch):
    from backend.agent import app
    from backend.routes import chat as chat_route

    monkeypatch.setattr(chat_route, "process_query", AsyncMock(return_value="mocked reply"))

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    return TestClient(app)


def _session_cookie_for_new_user(client) -> dict[str, str]:
    from datetime import datetime, timedelta, timezone

    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    return {"session": token}


def test_post_chat_requires_auth(client):
    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 401


def test_post_chat_persists_user_and_assistant_messages(client):
    cookies = _session_cookie_for_new_user(client)

    response = client.post("/chat", json={"message": "hi"}, cookies=cookies)
    assert response.status_code == 200
    assert response.json() == {"reply": "mocked reply"}

    history = client.get("/chat/history", cookies=cookies)
    contents = [m["content"] for m in history.json()["messages"]]
    assert contents == ["mocked reply", "hi"]


def test_get_chat_history_requires_auth(client):
    response = client.get("/chat/history")
    assert response.status_code == 401


def test_get_chat_history_paginates(client):
    cookies = _session_cookie_for_new_user(client)
    for i in range(3):
        client.post("/chat", json={"message": f"message {i}"}, cookies=cookies)

    first_page = client.get("/chat/history?limit=2", cookies=cookies).json()
    assert len(first_page["messages"]) == 2
    assert first_page["has_more"] is True

    oldest_id_on_first_page = first_page["messages"][-1]["id"]
    second_page = client.get(
        f"/chat/history?before_id={oldest_id_on_first_page}&limit=2", cookies=cookies
    ).json()
    assert second_page["has_more"] is True
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/backend/routes/test_chat.py -v`
Expected: FAIL — `GET /chat/history` doesn't exist (404), and `POST /chat` doesn't persist anything yet.

- [x] **Step 3: Implement the minimal code**

Replace `backend/routes/chat.py` with:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.agent import conversations
from backend.dependencies import require_user
from backend.services.chat_service import process_query
from data.db import get_messages, save_message

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
async def chat(request: ChatRequest, user_id: str = Depends(require_user)):
    messages = conversations.setdefault(user_id, [])
    messages.append({"role": "user", "content": request.message})
    save_message(user_id, "user", request.message)

    reply = await process_query(user_id, messages)
    save_message(user_id, "assistant", reply)

    return {"reply": reply}


@router.get("/chat/history")
def chat_history(
    before_id: int | None = None, limit: int = 20, user_id: str = Depends(require_user)
):
    messages, has_more = get_messages(user_id, before_id=before_id, limit=limit)
    return {
        "messages": [
            {
                "id": m["id"],
                "role": m["role"],
                "content": m["content"],
                "created_at": m["created_at"].isoformat(),
            }
            for m in messages
        ],
        "has_more": has_more,
    }
```

Note: `process_query` is imported directly into the test via `backend.routes.chat.process_query` for mocking — since `chat.py` does `from backend.services.chat_service import process_query`, the name lives in the `chat` module's namespace, so `monkeypatch.setattr(chat_route, "process_query", ...)` patches the right reference.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/routes/test_chat.py -v`
Expected: PASS (all 4 tests)

- [x] **Step 5: Run the full backend test suite to check for regressions**

Run: `pytest tests/ -v`
Expected: PASS (no regressions in auth, dashboard, preferences, profile route tests)

---

### Task 3: Frontend — load and infinite-scroll chat history

**Files:**
- Modify: the chat screen component (locate via `grep -rl "useChat\|/chat" frontend/src --include=*.tsx` or equivalent — exact path not yet confirmed, confirm at execution time since frontend structure wasn't inspected during planning)
- Modify/Create: an API client function for `GET /chat/history` alongside the existing chat POST client function

**Interfaces:**
- Consumes: `GET /chat/history?before_id=&limit=` → `{"messages": [{"id": number, "role": "user"|"assistant", "content": string, "created_at": string}], "has_more": boolean}` (from Task 2)
- Produces: chat screen renders historical messages oldest-to-newest above the live conversation, loading older pages when the user scrolls to the top

**Note:** This task's exact file paths depend on the current frontend structure, which wasn't inspected during planning (backend-only context was gathered). Before starting implementation, locate:
1. The existing chat screen/component that calls `POST /chat`.
2. The existing API client module (likely near where `preferences`/`dashboard` API calls live, given the pattern described in this project's CLAUDE.md).
3. Confirm React Query is already configured with a `QueryClientProvider` (CLAUDE.md states "API client + React Query" is already wired up).

- [x] **Step 1: Write the failing test**

Locate the frontend test setup (check for `*.test.tsx` files near the chat component, e.g. via `find frontend -iname "*chat*test*"`). Write a test asserting that on mount, the chat screen calls the history endpoint and renders returned messages oldest-first. Use the project's existing frontend test tooling and mocking conventions (inspect an existing component test, e.g. for the preferences form, to match its mocking pattern for API calls) — write the concrete test against the actual component API once located, following the same assertions style already used in that test file.

- [x] **Step 2: Run test to verify it fails**

Run the project's frontend test command (check `package.json` `scripts.test`) scoped to the new/modified test file.
Expected: FAIL — history fetching not implemented yet.

- [x] **Step 3: Implement**

Add a `useInfiniteQuery` hook (React Query) that:
- Fetches `GET /chat/history?limit=20` for the initial page.
- Uses `has_more` and the oldest message's `id` in the current page as `getNextPageParam` to fetch `GET /chat/history?before_id=<id>&limit=20` on scroll-to-top.
- Flattens and reverses pages (oldest-to-newest) before rendering, reusing the existing markdown-rendering component for each message's `content`.
- Merges historical messages with the live in-session conversation state so newly sent messages continue to appear immediately (optimistic local append, as today) without waiting for a history refetch.

- [x] **Step 4: Run test to verify it passes**

Run the frontend test command again.
Expected: PASS

- [x] **Step 5: Manual verification**

Start the dev server, log in, send a few chat messages, refresh the page, and confirm history loads and renders with markdown intact. Scroll up if more than 20 messages exist to confirm older pages load.

---

### Task 4: Review and commit

- [x] **Step 1: User reviews the full diff across all three tasks**

Run: `git status` and `git diff` to review every change from Tasks 1-3 together.

- [x] **Step 2: Commit**

Once the user approves, stage and commit all changes in one commit (or split by task at the user's discretion at that time):

```bash
git add data/db.py backend/routes/chat.py tests/data/test_db.py tests/backend/routes/test_chat.py <frontend files from Task 3>
git commit -m "feat: persist chat history and display it with infinite scroll"
```

---

### Task 5: Follow-on fixes discovered during implementation (not in original plan)

While implementing and manually verifying Tasks 1-3, several issues surfaced that weren't anticipated in the original design:

- [x] **Test isolation:** `tests/data/test_db.py`'s `clean_schema` fixture (`DROP TABLE ... CASCADE`) was running against the real Supabase database, because `conftest.py`'s `load_dotenv()` loaded the same `DATABASE_URL` the live app uses — confirmed by comparing row counts before/after a test run. Fixed by adding `testcontainers[postgres]` as a dev dependency and starting a throwaway local Postgres container as module-level code in `conftest.py`, overwriting `os.environ["DATABASE_URL"]` before any test module (and therefore `data/db.py`'s import-time connection pool) can be imported. Verified the test run now connects to `localhost:<random-port>` instead of Supabase's pooler host.
- [x] **Duplicate message rendering:** after sending a message, the exchange sometimes rendered twice in the UI. Root cause: `chat-screen.tsx` concatenated DB-backed `historyMessages` (from `useInfiniteQuery`) with locally-held optimistic `messages` state, and React Query's default `refetchOnWindowFocus`/`refetchOnMount` behavior would refetch history mid-session, causing the same persisted turn to appear in both lists. Fixed by invalidating the `chat-history` query and clearing local `messages` state after a successful send, making `historyMessages` the single source of truth.
- [x] **Auto-scroll on new messages:** added scroll-to-bottom behavior in `chat-screen.tsx`, gated on whether the user was already near the bottom (tracked via a ref updated in the scroll handler), so it doesn't yank the view down if the user has scrolled up into history.
- [x] **Scroll never actually happened (flexbox bug):** the auto-scroll fix initially had no visible effect. Root cause: `ChatScreen`'s root `flex flex-1 flex-col` div had no `overflow` set, so per the flexbox spec its automatic minimum height stayed content-based — it grew to fit all messages instead of respecting `AppShell`'s `<main>` (`flex-1 overflow-y-auto`) available height, so the actual page scrolled instead of the intended inner container. Fixed by adding `min-h-0` to that root div.
- [x] **Scrollbar flash:** the native scrollbar briefly appearing/disappearing on each new message was visually distracting. Added a `.scrollbar-none` utility class (`app/globals.css`) and applied it to the chat scroll container — hides the scrollbar visually while keeping the container fully scrollable (wheel, touch, and programmatic `scrollTop`).

---

## Self-Review Notes

- **Spec coverage:** data model (Task 1), write-side persistence + read endpoint (Task 2), UI pagination/display (Task 3) — all three spec sections covered. Retention/threading/context-window items are explicitly out of scope per spec and not present in any task.
- **Type consistency:** `save_message`/`get_messages` signatures match between Task 1 (definition) and Task 2 (usage). `GET /chat/history` response shape matches between Task 2 (definition) and Task 3 (consumption).
- **Known gap:** Task 3's exact file paths are unconfirmed since frontend structure wasn't inspected during planning — flagged explicitly in the task rather than guessed, per the no-placeholder rule. Whoever executes Task 3 should do a quick `find`/`grep` first to fill this in before writing code.
