# Multi-Chat Threads — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single flat per-user chat history with multiple persistent conversation threads (create, list, rename, pin, delete, search), backed by a new `conversations` table.

**Architecture:** A new `conversations` table becomes the parent of `messages` and `conversation_summaries` (both gain a `conversation_id` FK, replacing their current `user_id` scoping). A new `/conversations` router exposes CRUD. `/chat` gains an optional `conversation_id` in its request body — omitted means "first message of a new chat," and the route creates the conversation (title = truncated first message) before persisting. Per-conversation folding gives each thread its own independent 40k-token summarization budget.

**Tech Stack:** FastAPI, psycopg (raw SQL, no ORM), pytest + testcontainers Postgres (existing `conftest.py`).

**Spec:** `docs/superpowers/specs/2026-09-04-multi-chat-threads-design.md`

## Global Constraints

- Existing chat history is **discarded**, not migrated (spec: "Decisions").
- Hard delete only — `ON DELETE CASCADE`, no archive/undo.
- Rename rejects empty/whitespace-only titles (validation error, not a silent fallback).
- Search is title-only (`ILIKE`), not full message-content search.
- Token budget (`TOKEN_BUDGET_LIMIT`) and long-term memories (`memories` table) stay scoped to `user_id`, unchanged by this plan.
- Every conversation-scoped endpoint must verify `conversations.user_id == current user_id` before acting, returning **404** (not 403) on mismatch.
- Title truncation: 60 chars max, `…` suffix when truncated (no LLM call — first-message-as-title per spec).

## Note on scope beyond the spec

The spec's "Backend" section names `chat.py` and `summarization_service.py`, but `backend/services/chat_service.py` also calls `db.save_message` and `db.get_conversation_summary` directly (mid-tool-loop persistence, and system-prompt summary injection) — this file needs `conversation_id` threaded through it too (Task 4 below). This doesn't change the design, just adds a file the spec didn't enumerate.

---

### Task 1: `conversations` table + schema migration

**Files:**
- Modify: `data/db.py:19-131` (`init_db`)
- Modify: `tests/data/test_db.py` (`clean_schema` fixture, schema assertion tests)

**Interfaces:**
- Produces: `conversations` table (`id UUID PK`, `user_id UUID FK`, `title TEXT`, `pinned BOOLEAN`, `created_at`, `updated_at`); `messages.conversation_id` FK (replacing `messages.user_id`); `conversation_summaries.conversation_id` PK (replacing `conversation_summaries.user_id`).

- [x] **Step 1: Write the failing test**

Add to `tests/data/test_db.py` (near the existing `test_init_db_creates_users_table`):

```python
def test_init_db_creates_conversations_table():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'conversations' AND table_schema = 'public'"
        ).fetchall()
    columns = {row[0] for row in result}
    assert columns == {"id", "user_id", "title", "pinned", "created_at", "updated_at"}


def test_init_db_scopes_messages_to_conversation_id():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'messages' AND table_schema = 'public'"
        ).fetchall()
    columns = {row[0] for row in result}
    assert "conversation_id" in columns
    assert "user_id" not in columns


def test_init_db_scopes_conversation_summaries_to_conversation_id():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'conversation_summaries' AND table_schema = 'public'"
        ).fetchall()
    columns = {row[0] for row in result}
    assert "conversation_id" in columns
    assert "user_id" not in columns
```

Also update the existing `clean_schema` fixture at the top of the file to drop the new table:

```python
@pytest.fixture(autouse=True)
def clean_schema():
    init_db()
    yield
    with get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS conversation_summaries CASCADE")
        conn.execute("DROP TABLE IF EXISTS messages CASCADE")
        conn.execute("DROP TABLE IF EXISTS conversations CASCADE")
        conn.execute("DROP TABLE IF EXISTS memories CASCADE")
        conn.execute("DROP TABLE IF EXISTS preferences CASCADE")
        conn.execute("DROP TABLE IF EXISTS notifications CASCADE")
        conn.execute("DROP TABLE IF EXISTS oauth_tokens CASCADE")
        conn.execute("DROP TABLE IF EXISTS sessions CASCADE")
        conn.execute("DROP TABLE IF EXISTS users CASCADE")
        conn.commit()
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/test_db.py -k "conversations_table or scopes_messages or scopes_conversation_summaries" -v`
Expected: FAIL — `conversations` table doesn't exist yet; `messages`/`conversation_summaries` still have `user_id`, not `conversation_id`.

- [x] **Step 3: Replace the `messages` and `conversation_summaries` table definitions in `init_db`**

In `data/db.py`, replace this block (currently lines 59-78):

```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_user_id_id ON messages (user_id, id DESC)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                summary_text TEXT NOT NULL,
                through_message_id INTEGER NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
```

with:

```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL DEFAULT 'New chat',
                pinned BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_user_id_updated_at "
            "ON conversations (user_id, pinned DESC, updated_at DESC)"
        )

        # One-time destructive migration: `messages`/`conversation_summaries` predate
        # the `conversations` table and have no `conversation_id` to backfill against.
        # Per the multi-chat-threads design doc, existing chat history is discarded
        # rather than migrated, so drop-and-recreate only if the old shape is present.
        old_shape = conn.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'messages' AND column_name = 'user_id'
        """).fetchone()
        if old_shape is not None:
            conn.execute("DROP TABLE IF EXISTS conversation_summaries CASCADE")
            conn.execute("DROP TABLE IF EXISTS messages CASCADE")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_id "
            "ON messages (conversation_id, id DESC)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                conversation_id UUID PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
                summary_text TEXT NOT NULL,
                through_message_id INTEGER NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
```

---

### Task 2: Conversation CRUD functions

**Files:**
- Modify: `data/db.py` (add new functions after `upsert_conversation_summary`, i.e. after the block touched in Task 1)
- Modify: `tests/data/test_db.py` (add tests; add new imports)

**Interfaces:**
- Consumes: `get_connection()` (existing), `conversations` table (Task 1).
- Produces: `create_conversation(user_id: str, title: str) -> str`, `get_conversation(conversation_id: str, user_id: str) -> dict | None`, `list_conversations(user_id: str, search: str | None = None) -> list[dict]`, `rename_conversation(conversation_id: str, user_id: str, title: str) -> None` (raises `EmptyTitleError`), `set_pinned(conversation_id: str, user_id: str, pinned: bool) -> None`, `delete_conversation(conversation_id: str, user_id: str) -> None`, exception class `EmptyTitleError`.

- [x] **Step 1: Write the failing tests**

Add to `tests/data/test_db.py`'s import block (alphabetical, matching existing style):

```python
from data.db import (
    EmptyTitleError,
    Notification,
    Preferences,
    create_conversation,
    create_notification,
    create_session,
    delete_conversation,
    delete_oauth_token,
    delete_session,
    find_or_create_user,
    get_calendar_id,
    get_connection,
    get_conversation,
    get_memories,
    get_messages,
    get_messages_since,
    get_oauth_token,
    get_preferences,
    get_session_user_id,
    get_tokens_used,
    get_user,
    increment_tokens_used,
    init_db,
    list_conversations,
    list_notifications,
    mark_all_read,
    rename_conversation,
    resolve_notification,
    save_memory,
    save_message,
    save_oauth_token,
    save_calendar_id,
    set_pinned,
    update_avatar_path,
    upsert_preferences,
)
```

Add new test functions:

```python
def _create_user() -> str:
    return find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")


def test_create_conversation_returns_id_and_defaults():
    user_id = _create_user()

    conversation_id = create_conversation(user_id, "Marathon taper plan")

    conversation = get_conversation(conversation_id, user_id)
    assert conversation["title"] == "Marathon taper plan"
    assert conversation["pinned"] is False


def test_get_conversation_returns_none_for_other_users_conversation():
    user_id = _create_user()
    other_user_id = find_or_create_user("other@example.com", "google-sub-456", "Other")
    conversation_id = create_conversation(user_id, "Mine")

    assert get_conversation(conversation_id, other_user_id) is None


def test_list_conversations_orders_pinned_first_then_by_recency():
    user_id = _create_user()
    older = create_conversation(user_id, "Older chat")
    newer = create_conversation(user_id, "Newer chat")
    save_message(older, "user", "hi")
    save_message(newer, "user", "hi")
    set_pinned(older, user_id, True)

    conversations = list_conversations(user_id)

    assert [c["id"] for c in conversations] == [older, newer]
    assert conversations[0]["pinned"] is True


def test_list_conversations_filters_by_title_search():
    user_id = _create_user()
    create_conversation(user_id, "Marathon taper plan")
    create_conversation(user_id, "Shin pain advice")

    results = list_conversations(user_id, search="marathon")

    assert len(results) == 1
    assert results[0]["title"] == "Marathon taper plan"


def test_rename_conversation_updates_title():
    user_id = _create_user()
    conversation_id = create_conversation(user_id, "New chat")

    rename_conversation(conversation_id, user_id, "Renamed chat")

    assert get_conversation(conversation_id, user_id)["title"] == "Renamed chat"


def test_rename_conversation_rejects_empty_title():
    user_id = _create_user()
    conversation_id = create_conversation(user_id, "New chat")

    with pytest.raises(EmptyTitleError):
        rename_conversation(conversation_id, user_id, "   ")

    assert get_conversation(conversation_id, user_id)["title"] == "New chat"


def test_set_pinned_toggles_pinned_flag():
    user_id = _create_user()
    conversation_id = create_conversation(user_id, "New chat")

    set_pinned(conversation_id, user_id, True)
    assert get_conversation(conversation_id, user_id)["pinned"] is True

    set_pinned(conversation_id, user_id, False)
    assert get_conversation(conversation_id, user_id)["pinned"] is False


def test_delete_conversation_removes_it_and_cascades_to_messages():
    user_id = _create_user()
    conversation_id = create_conversation(user_id, "New chat")
    save_message(conversation_id, "user", "hi")

    delete_conversation(conversation_id, user_id)

    assert get_conversation(conversation_id, user_id) is None
    messages, _ = get_messages(conversation_id, before_id=None, limit=20)
    assert messages == []
```

Note: this step's tests reference `save_message(conversation_id, ...)` and `get_messages(conversation_id, ...)` with the *new* Task 3 signatures — that's expected; Task 2 and Task 3 land together in this plan's execution order, so run this task's new tests only (not the full file) until Task 3 is also done. (`pytest -k` selection below.)

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/test_db.py -k "conversation and not messages_table and not scopes_" -v`
Expected: FAIL with `ImportError` (functions don't exist yet).

- [x] **Step 3: Implement the CRUD functions**

Add to `data/db.py`, directly after `upsert_conversation_summary`:

```python
class EmptyTitleError(ValueError):
    pass


def create_conversation(user_id: str, title: str) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "INSERT INTO conversations (user_id, title) VALUES (%s, %s) RETURNING id",
            (user_id, title),
        ).fetchone()
        conn.commit()
    return str(row[0])


def get_conversation(conversation_id: str, user_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, title, pinned, created_at, updated_at
            FROM conversations WHERE id = %s AND user_id = %s
            """,
            (conversation_id, user_id),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": str(row[0]),
        "title": row[1],
        "pinned": row[2],
        "created_at": row[3],
        "updated_at": row[4],
    }


def list_conversations(user_id: str, search: str | None = None) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, pinned, created_at, updated_at
            FROM conversations
            WHERE user_id = %s AND (%s::text IS NULL OR title ILIKE '%%' || %s || '%%')
            ORDER BY pinned DESC, updated_at DESC
            """,
            (user_id, search, search),
        ).fetchall()
    return [
        {
            "id": str(row[0]),
            "title": row[1],
            "pinned": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }
        for row in rows
    ]


def rename_conversation(conversation_id: str, user_id: str, title: str) -> None:
    if not title.strip():
        raise EmptyTitleError("title cannot be empty")
    with get_connection() as conn:
        conn.execute(
            "UPDATE conversations SET title = %s WHERE id = %s AND user_id = %s",
            (title, conversation_id, user_id),
        )
        conn.commit()


def set_pinned(conversation_id: str, user_id: str, pinned: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE conversations SET pinned = %s WHERE id = %s AND user_id = %s",
            (pinned, conversation_id, user_id),
        )
        conn.commit()


def delete_conversation(conversation_id: str, user_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM conversations WHERE id = %s AND user_id = %s",
            (conversation_id, user_id),
        )
        conn.commit()
```

---

### Task 3: Scope messages, folding, and summaries to `conversation_id`

**Files:**
- Modify: `data/db.py` (`save_message`, `get_messages`, `get_messages_since`, `get_conversation_summary`, `upsert_conversation_summary`)
- Modify: `backend/services/summarization_service.py` (`maybe_fold` parameter name)
- Modify: `tests/data/test_db.py` (update existing message/summary tests to pass a `conversation_id`)
- Modify: `tests/backend/services/test_summarization_service.py` (no signature changes needed — calls are positional — but re-run to confirm no regressions)

**Interfaces:**
- Consumes: `create_conversation` (Task 2), `conversations` table (Task 1).
- Produces: `save_message(conversation_id: str, role: str, content: str | list) -> int` (also bumps `conversations.updated_at`), `get_messages(conversation_id: str, before_id: int | None, limit: int) -> tuple[list[dict], bool]`, `get_messages_since(conversation_id: str, after_id: int) -> list[dict]`, `get_conversation_summary(conversation_id: str) -> dict | None`, `upsert_conversation_summary(conversation_id: str, summary_text: str, through_message_id: int) -> None`, `maybe_fold(conversation_id: str, system_prompt, rows, tools) -> list[dict]`.

- [x] **Step 1: Write the failing test**

Add to `tests/data/test_db.py`:

```python
def test_save_message_bumps_conversation_updated_at():
    user_id = _create_user()
    conversation_id = create_conversation(user_id, "New chat")
    before = get_conversation(conversation_id, user_id)["updated_at"]

    save_message(conversation_id, "user", "hi")

    after = get_conversation(conversation_id, user_id)["updated_at"]
    assert after >= before


def test_messages_are_isolated_per_conversation():
    user_id = _create_user()
    conversation_a = create_conversation(user_id, "Chat A")
    conversation_b = create_conversation(user_id, "Chat B")
    save_message(conversation_a, "user", "message in A")
    save_message(conversation_b, "user", "message in B")

    messages_a, _ = get_messages(conversation_a, before_id=None, limit=20)
    messages_b, _ = get_messages(conversation_b, before_id=None, limit=20)

    assert [m["content"] for m in messages_a] == ["message in A"]
    assert [m["content"] for m in messages_b] == ["message in B"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/test_db.py -k "bumps_conversation_updated_at or isolated_per_conversation" -v`
Expected: FAIL — `save_message`/`get_messages` still take `user_id`, not `conversation_id`.

- [x] **Step 3: Update `save_message`, `get_messages`, `get_messages_since`**

Replace in `data/db.py`:

```python
def save_message(user_id: str, role: str, content: str | list) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO messages (user_id, role, content)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (user_id, role, Json(content)),
        ).fetchone()
        conn.commit()
    return row[0]


def get_messages(
    user_id: str, before_id: int | None, limit: int
) -> tuple[list[dict], bool]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, created_at FROM messages
            WHERE user_id = %s AND (%s::int IS NULL OR id < %s)
                AND jsonb_typeof(content) = 'string'
            ORDER BY id DESC
            LIMIT %s
            """,
            (user_id, before_id, before_id, limit + 1),
        ).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    messages = [
        {"id": row[0], "role": row[1], "content": row[2], "created_at": row[3]}
        for row in rows
    ]
    return messages, has_more


def get_messages_since(user_id: str, after_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content FROM messages
            WHERE user_id = %s AND id > %s
            ORDER BY id
            """,
            (user_id, after_id),
        ).fetchall()
    return [{"id": row[0], "role": row[1], "content": row[2]} for row in rows]
```

with:

```python
def save_message(conversation_id: str, role: str, content: str | list) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (conversation_id, role, Json(content)),
        ).fetchone()
        conn.execute(
            "UPDATE conversations SET updated_at = now() WHERE id = %s",
            (conversation_id,),
        )
        conn.commit()
    return row[0]


def get_messages(
    conversation_id: str, before_id: int | None, limit: int
) -> tuple[list[dict], bool]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, created_at FROM messages
            WHERE conversation_id = %s AND (%s::int IS NULL OR id < %s)
                AND jsonb_typeof(content) = 'string'
            ORDER BY id DESC
            LIMIT %s
            """,
            (conversation_id, before_id, before_id, limit + 1),
        ).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    messages = [
        {"id": row[0], "role": row[1], "content": row[2], "created_at": row[3]}
        for row in rows
    ]
    return messages, has_more


def get_messages_since(conversation_id: str, after_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content FROM messages
            WHERE conversation_id = %s AND id > %s
            ORDER BY id
            """,
            (conversation_id, after_id),
        ).fetchall()
    return [{"id": row[0], "role": row[1], "content": row[2]} for row in rows]
```

- [x] **Step 4: Update `get_conversation_summary` and `upsert_conversation_summary`**

Replace in `data/db.py`:

```python
def get_conversation_summary(user_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT summary_text, through_message_id
            FROM conversation_summaries WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return {"summary_text": row[0], "through_message_id": row[1]}


def upsert_conversation_summary(
    user_id: str, summary_text: str, through_message_id: int
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversation_summaries
                (user_id, summary_text, through_message_id, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (user_id) DO UPDATE SET
                summary_text = excluded.summary_text,
                through_message_id = excluded.through_message_id,
                updated_at = excluded.updated_at
            """,
            (user_id, summary_text, through_message_id),
        )
        conn.commit()
```

with:

```python
def get_conversation_summary(conversation_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT summary_text, through_message_id
            FROM conversation_summaries WHERE conversation_id = %s
            """,
            (conversation_id,),
        ).fetchone()
    if row is None:
        return None
    return {"summary_text": row[0], "through_message_id": row[1]}


def upsert_conversation_summary(
    conversation_id: str, summary_text: str, through_message_id: int
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversation_summaries
                (conversation_id, summary_text, through_message_id, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (conversation_id) DO UPDATE SET
                summary_text = excluded.summary_text,
                through_message_id = excluded.through_message_id,
                updated_at = excluded.updated_at
            """,
            (conversation_id, summary_text, through_message_id),
        )
        conn.commit()
```

- [x] **Step 5: Rename the parameter in `maybe_fold`**

In `backend/services/summarization_service.py`, change the signature and every internal reference from `user_id` to `conversation_id`:

```python
async def maybe_fold(
    conversation_id: str, system_prompt: str, rows: list[dict], tools: list[dict]
) -> list[dict]:
```

and update its two internal call sites (`db.get_conversation_summary(user_id)` → `db.get_conversation_summary(conversation_id)`, `db.upsert_conversation_summary(user_id, ...)` → `db.upsert_conversation_summary(conversation_id, ...)`).

---

### Task 4: Thread `conversation_id` through `chat_service.py`

**Files:**
- Modify: `backend/services/chat_service.py` (`_build_system_prompt`, `process_query`)
- Modify: `tests/backend/services/test_chat_service.py`
- Modify: `tests/backend/services/test_chat_service_otel.py`

**Interfaces:**
- Consumes: `db.get_conversation_summary(conversation_id)`, `db.save_message(conversation_id, ...)` (Task 3).
- Produces: `_build_system_prompt(base_prompt: str, user_id: str, conversation_id: str) -> list[dict]`, `process_query(user_id: str, conversation_id: str, messages: list[dict], usage: dict | None = None)`.

- [x] **Step 1: Update the two call sites' test fixtures first (they currently call the old signature)**

In `tests/backend/services/test_chat_service.py`, apply these exact replacements:

Replace (7 occurrences — use `replace_all`):
```python
                "user-123", [{"role": "user", "content": "hi"}]
```
with:
```python
                "user-123", "conv-123", [{"role": "user", "content": "hi"}]
```

Replace (1 occurrence, the usage-tracking test):
```python
                "user-123", [{"role": "user", "content": "hi"}], usage=usage
```
with:
```python
                "user-123", "conv-123", [{"role": "user", "content": "hi"}], usage=usage
```

Replace the two `mock_save_message.assert_any_call` blocks:
```python
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
with:
```python
    mock_save_message.assert_any_call(
        "conv-123",
        "assistant",
        [{"type": "tool_use", "id": "call-1", "name": "get_weekly_stats", "input": {}}],
    )
    mock_save_message.assert_any_call(
        "conv-123",
        "user",
        [{"type": "tool_result", "tool_use_id": "call-1", "content": "42km this week"}],
    )
```

In `tests/backend/services/test_chat_service_otel.py`, replace:
```python
                "test-user", [{"role": "user", "content": "hello"}]
```
with:
```python
                "test-user", "conv-1", [{"role": "user", "content": "hello"}]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/backend/services/test_chat_service.py tests/backend/services/test_chat_service_otel.py -v`
Expected: FAIL — `process_query()` doesn't yet accept the extra positional argument (`TypeError: too many positional arguments`).

- [x] **Step 3: Update `_build_system_prompt` and `process_query` in `chat_service.py`**

Replace:
```python
def _build_system_prompt(base_prompt: str, user_id: str) -> list[dict]:
```
with:
```python
def _build_system_prompt(base_prompt: str, user_id: str, conversation_id: str) -> list[dict]:
```

Inside that function, replace:
```python
    summary = db.get_conversation_summary(user_id)
```
with:
```python
    summary = db.get_conversation_summary(conversation_id)
```

Replace the `process_query` signature:
```python
async def process_query(user_id: str, messages: list[dict], usage: dict | None = None):
```
with:
```python
async def process_query(
    user_id: str, conversation_id: str, messages: list[dict], usage: dict | None = None
):
```

Inside `process_query`, replace:
```python
            system_prompt = _build_system_prompt(SYSTEM_PROMPT, user_id)
```
with:
```python
            system_prompt = _build_system_prompt(SYSTEM_PROMPT, user_id, conversation_id)
```

and replace:
```python
                        db.save_message(user_id, "assistant", content_dicts)
                        db.save_message(user_id, "user", tool_results)
```
with:
```python
                        db.save_message(conversation_id, "assistant", content_dicts)
                        db.save_message(conversation_id, "user", tool_results)
```

---

### Task 5: `/conversations` router

**Files:**
- Create: `backend/routes/conversations.py`
- Create: `tests/backend/routes/test_conversations.py`
- Modify: `backend/agent.py:93-100` (register the new router)

**Interfaces:**
- Consumes: `require_user` (`backend/dependencies.py`), `get_conversation`, `list_conversations`, `rename_conversation`, `set_pinned`, `delete_conversation`, `EmptyTitleError`, `get_messages` (Tasks 2-3).
- Produces: `GET /conversations`, `PATCH /conversations/{id}`, `DELETE /conversations/{id}`, `GET /conversations/{id}/messages` — this last one is the router other future work (frontend, and Task 6's chat route) treats as the replacement for the old `GET /chat/history`. No `POST /conversations` — per the spec, conversations are only ever created inline by `POST /chat` (Task 6's lazy-create-on-first-message), so a standalone create endpoint would be unused.

- [x] **Step 1: Write the failing tests**

Create `tests/backend/routes/test_conversations.py`:

```python
import base64
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from data.db import create_conversation, create_session, find_or_create_user, init_db, save_message


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "TOKEN_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    init_db()


@pytest.fixture
def client():
    from backend.agent import app

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    return TestClient(app)


def _session_cookie_for_new_user(client, email="runner@example.com") -> str:
    user_id = find_or_create_user(email, f"google-sub-{email}", "Runner Example")
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    client.cookies.set("session", token)
    return user_id


def test_list_conversations_requires_auth(client):
    response = client.get("/conversations")
    assert response.status_code == 401


def test_list_conversations_returns_users_conversations(client):
    user_id = _session_cookie_for_new_user(client)
    create_conversation(user_id, "Marathon taper plan")

    response = client.get("/conversations")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["title"] == "Marathon taper plan"


def test_list_conversations_filters_by_search(client):
    user_id = _session_cookie_for_new_user(client)
    create_conversation(user_id, "Marathon taper plan")
    create_conversation(user_id, "Shin pain advice")

    response = client.get("/conversations?search=shin")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["title"] == "Shin pain advice"


def test_get_conversation_messages_returns_404_for_other_users_conversation(client):
    user_id = _session_cookie_for_new_user(client, "owner@example.com")
    conversation_id = create_conversation(user_id, "Private chat")
    _session_cookie_for_new_user(client, "intruder@example.com")

    response = client.get(f"/conversations/{conversation_id}/messages")

    assert response.status_code == 404


def test_get_conversation_messages_returns_messages(client):
    user_id = _session_cookie_for_new_user(client)
    conversation_id = create_conversation(user_id, "New chat")
    save_message(conversation_id, "user", "hi")

    response = client.get(f"/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    body = response.json()
    assert [m["content"] for m in body["messages"]] == ["hi"]


def test_patch_conversation_renames_it(client):
    user_id = _session_cookie_for_new_user(client)
    conversation_id = create_conversation(user_id, "New chat")

    response = client.patch(f"/conversations/{conversation_id}", json={"title": "Renamed"})

    assert response.status_code == 200
    assert client.get("/conversations").json()[0]["title"] == "Renamed"


def test_patch_conversation_rejects_empty_title(client):
    user_id = _session_cookie_for_new_user(client)
    conversation_id = create_conversation(user_id, "New chat")

    response = client.patch(f"/conversations/{conversation_id}", json={"title": "   "})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "empty_title"


def test_patch_conversation_pins_it(client):
    user_id = _session_cookie_for_new_user(client)
    conversation_id = create_conversation(user_id, "New chat")

    response = client.patch(f"/conversations/{conversation_id}", json={"pinned": True})

    assert response.status_code == 200
    assert client.get("/conversations").json()[0]["pinned"] is True


def test_patch_conversation_returns_404_for_other_users_conversation(client):
    user_id = _session_cookie_for_new_user(client, "owner@example.com")
    conversation_id = create_conversation(user_id, "Private chat")
    _session_cookie_for_new_user(client, "intruder@example.com")

    response = client.patch(f"/conversations/{conversation_id}", json={"title": "Hijacked"})

    assert response.status_code == 404


def test_delete_conversation_removes_it(client):
    user_id = _session_cookie_for_new_user(client)
    conversation_id = create_conversation(user_id, "New chat")

    response = client.delete(f"/conversations/{conversation_id}")

    assert response.status_code == 200
    assert client.get("/conversations").json() == []


def test_delete_conversation_returns_404_for_other_users_conversation(client):
    user_id = _session_cookie_for_new_user(client, "owner@example.com")
    conversation_id = create_conversation(user_id, "Private chat")
    _session_cookie_for_new_user(client, "intruder@example.com")

    response = client.delete(f"/conversations/{conversation_id}")

    assert response.status_code == 404
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/backend/routes/test_conversations.py -v`
Expected: FAIL — `404 Not Found` for every request (router doesn't exist / isn't registered).

- [x] **Step 3: Create the router**

Create `backend/routes/conversations.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.dependencies import require_user
from data.db import (
    EmptyTitleError,
    delete_conversation,
    get_conversation,
    get_messages,
    list_conversations,
    rename_conversation,
    set_pinned,
)

router = APIRouter(prefix="/conversations")


class ConversationUpdateRequest(BaseModel):
    title: str | None = None
    pinned: bool | None = None


def _require_owned_conversation(conversation_id: str, user_id: str) -> None:
    if get_conversation(conversation_id, user_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("")
def list_conversations_route(
    search: str | None = None, user_id: str = Depends(require_user)
):
    return list_conversations(user_id, search=search)


@router.get("/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: str,
    before_id: int | None = None,
    limit: int = 20,
    user_id: str = Depends(require_user),
):
    _require_owned_conversation(conversation_id, user_id)
    messages, has_more = get_messages(conversation_id, before_id=before_id, limit=limit)
    return {"messages": messages, "has_more": has_more}


@router.patch("/{conversation_id}")
def update_conversation_route(
    conversation_id: str,
    request: ConversationUpdateRequest,
    user_id: str = Depends(require_user),
):
    _require_owned_conversation(conversation_id, user_id)
    if request.title is not None:
        try:
            rename_conversation(conversation_id, user_id, request.title)
        except EmptyTitleError:
            raise HTTPException(status_code=400, detail={"error": "empty_title"})
    if request.pinned is not None:
        set_pinned(conversation_id, user_id, request.pinned)
    return {"status": "ok"}


@router.delete("/{conversation_id}")
def delete_conversation_route(
    conversation_id: str, user_id: str = Depends(require_user)
):
    _require_owned_conversation(conversation_id, user_id)
    delete_conversation(conversation_id, user_id)
    return {"status": "ok"}
```

Register it in `backend/agent.py`. Add the import alongside the other route imports and the `include_router` call alongside the others (`backend/agent.py:93-100`):

```python
from backend.routes.conversations import router as conversations_router
```

```python
app.include_router(conversations_router)
```

---

### Task 6: Rewire `/chat` to conversations

**Files:**
- Modify: `backend/routes/chat.py`
- Modify: `tests/backend/routes/test_chat.py` (full rewrite)

**Interfaces:**
- Consumes: `create_conversation`, `get_conversation` (Task 2), `save_message`, `get_messages_since`, `get_conversation_summary` (Task 3), `maybe_fold(conversation_id, ...)` (Task 3), `process_query(user_id, conversation_id, messages, usage=None)` (Task 4).
- Produces: `POST /chat` accepting `{"message": str, "conversation_id": str | None}`; first SSE event of the stream is `{"conversation_id": "..."}` so the frontend learns the id of a newly created conversation. `GET /chat/history` is removed (superseded by `GET /conversations/{id}/messages`, Task 5).

- [x] **Step 1: Write the failing tests (full replacement of `tests/backend/routes/test_chat.py`)**

Replace the entire contents of `tests/backend/routes/test_chat.py` with:

```python
import base64
import json
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from data.db import create_conversation, create_session, find_or_create_user, get_connection, init_db


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

    async def fake_process_query(user_id, conversation_id, messages, usage=None):
        for chunk in ["mocked ", "reply"]:
            yield chunk

    monkeypatch.setattr(chat_route, "process_query", fake_process_query)

    async def fake_maybe_fold(conversation_id, system_prompt, rows, tools):
        return rows

    monkeypatch.setattr(chat_route, "maybe_fold", fake_maybe_fold)

    @asynccontextmanager
    async def fake_open_mcp_session(user_id, server_url):
        yield None

    monkeypatch.setattr(chat_route, "open_mcp_session", fake_open_mcp_session)
    monkeypatch.setattr(chat_route, "get_tool_schemas", AsyncMock(return_value=[]))

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    return TestClient(app)


def _session_cookie_for_new_user(client) -> str:
    from datetime import datetime, timedelta, timezone

    user_id = find_or_create_user(
        "runner@example.com", "google-sub-123", "Runner Example"
    )
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    client.cookies.set("session", token)
    return user_id


def _collect_sse_events(response) -> list[dict]:
    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


def _collect_sse_text(response) -> str:
    return "".join(e["text"] for e in _collect_sse_events(response) if "text" in e)


def test_post_chat_requires_auth(client):
    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 401


def test_post_chat_without_conversation_id_creates_a_new_conversation(client):
    _session_cookie_for_new_user(client)

    response = client.post("/chat", json={"message": "Marathon taper plan question"})

    assert response.status_code == 200
    events = _collect_sse_events(response)
    conversation_id = events[0]["conversation_id"]
    assert conversation_id

    conversations = client.get("/conversations").json()
    assert conversations[0]["id"] == conversation_id
    assert conversations[0]["title"] == "Marathon taper plan question"


def test_post_chat_truncates_long_first_message_into_title(client):
    _session_cookie_for_new_user(client)

    long_message = "x" * 80
    response = client.post("/chat", json={"message": long_message})

    conversation_id = _collect_sse_events(response)[0]["conversation_id"]
    conversations = client.get("/conversations").json()
    assert conversations[0]["id"] == conversation_id
    assert conversations[0]["title"] == ("x" * 60) + "…"


def test_post_chat_with_conversation_id_reuses_existing_conversation(client):
    user_id = _session_cookie_for_new_user(client)
    conversation_id = create_conversation(user_id, "Existing chat")

    response = client.post(
        "/chat", json={"message": "hi", "conversation_id": conversation_id}
    )

    assert response.status_code == 200
    assert _collect_sse_events(response)[0]["conversation_id"] == conversation_id

    history = client.get(f"/conversations/{conversation_id}/messages").json()
    contents = [m["content"] for m in history["messages"]]
    assert contents == ["mocked reply", "hi"]


def test_post_chat_returns_404_for_nonexistent_conversation_id(client):
    _session_cookie_for_new_user(client)

    response = client.post(
        "/chat", json={"message": "hi", "conversation_id": "00000000-0000-0000-0000-000000000000"}
    )

    assert response.status_code == 404


def test_post_chat_calls_maybe_fold_with_rows_since_last_summary(client, monkeypatch):
    from backend.routes import chat as chat_route

    fold_mock = AsyncMock(
        side_effect=lambda conversation_id, system_prompt, rows, tools: rows
    )
    monkeypatch.setattr(chat_route, "maybe_fold", fold_mock)

    _session_cookie_for_new_user(client)
    response = client.post("/chat", json={"message": "hi"})

    assert response.status_code == 200
    fold_mock.assert_awaited_once()
    call_args = fold_mock.await_args
    rows_arg = call_args.args[2]
    assert [r["content"] for r in rows_arg] == ["hi"]


def test_chat_history_is_isolated_per_conversation(client):
    user_id = _session_cookie_for_new_user(client)

    first = client.post("/chat", json={"message": "first chat message"})
    first_id = _collect_sse_events(first)[0]["conversation_id"]

    second = client.post("/chat", json={"message": "second chat message"})
    second_id = _collect_sse_events(second)[0]["conversation_id"]

    assert first_id != second_id
    first_history = client.get(f"/conversations/{first_id}/messages").json()
    second_history = client.get(f"/conversations/{second_id}/messages").json()
    assert [m["content"] for m in first_history["messages"]] == [
        "mocked reply",
        "first chat message",
    ]
    assert [m["content"] for m in second_history["messages"]] == [
        "mocked reply",
        "second chat message",
    ]


def test_post_chat_rejects_message_over_500_chars(client):
    _session_cookie_for_new_user(client)
    response = client.post("/chat", json={"message": "x" * 501})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "message_too_long"


def test_post_chat_rejects_when_budget_exceeded(client, monkeypatch):
    monkeypatch.setenv("TOKEN_BUDGET_LIMIT", "1000")
    _session_cookie_for_new_user(client)

    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET tokens_used = 1000 WHERE email = %s",
            ("runner@example.com",),
        )
        conn.commit()

    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "budget_exceeded"


def test_post_chat_allowlisted_email_bypasses_budget_and_length(client, monkeypatch):
    monkeypatch.setenv("TOKEN_BUDGET_LIMIT", "1000")
    monkeypatch.setenv("UNRESTRICTED_EMAILS", "runner@example.com")
    _session_cookie_for_new_user(client)

    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET tokens_used = 999999 WHERE email = %s",
            ("runner@example.com",),
        )
        conn.commit()

    response = client.post("/chat", json={"message": "x" * 501})
    assert response.status_code == 200


def test_post_chat_increments_tokens_used_after_reply(client, monkeypatch):
    from backend.routes import chat as chat_route

    async def fake_process_query(user_id, conversation_id, messages, usage=None):
        if usage is not None:
            usage["input_tokens"] = 100
            usage["output_tokens"] = 50
        for chunk in ["mocked ", "reply"]:
            yield chunk

    monkeypatch.setattr(chat_route, "process_query", fake_process_query)
    _session_cookie_for_new_user(client)

    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 200

    with get_connection() as conn:
        row = conn.execute(
            "SELECT tokens_used FROM users WHERE email = %s", ("runner@example.com",)
        ).fetchone()
    assert row[0] == 150
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/backend/routes/test_chat.py -v`
Expected: FAIL — `ChatRequest` doesn't accept `conversation_id`, `/chat` doesn't create conversations, no `conversation_id` SSE event, `GET /chat/history` still exists rather than 404ing (route removal not yet done).

- [x] **Step 3: Rewrite `backend/routes/chat.py`**

Replace the full contents of `backend/routes/chat.py` with:

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
TITLE_MAX_CHARS = 60


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


def _unrestricted_emails() -> set[str]:
    # Semicolon-separated, not comma: this value is injected into gcloud's
    # `--set-env-vars`, which itself uses commas to delimit KEY=VALUE pairs —
    # a comma inside the value breaks that syntax (see deploy failure from
    # the first attempt at this).
    raw = os.environ.get("UNRESTRICTED_EMAILS", "")
    return {e.strip() for e in raw.split(";") if e.strip()}


def _token_budget_limit() -> int:
    return int(os.environ.get("TOKEN_BUDGET_LIMIT", "50000"))


def _title_from_message(message: str) -> str:
    stripped = message.strip()
    if len(stripped) <= TITLE_MAX_CHARS:
        return stripped
    return stripped[:TITLE_MAX_CHARS].rstrip() + "…"


@router.post("/chat")
async def chat(request: ChatRequest, user_id: str = Depends(require_user)):
    from backend.agent import SYSTEM_PROMPT

    email, _, _, _ = db.get_user(user_id)
    is_unrestricted = email in _unrestricted_emails()

    if not is_unrestricted and len(request.message) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=400, detail={"error": "message_too_long"})

    if not is_unrestricted and db.get_tokens_used(user_id) >= _token_budget_limit():
        raise HTTPException(status_code=403, detail={"error": "budget_exceeded"})

    conversation_id = request.conversation_id
    if conversation_id is None:
        conversation_id = db.create_conversation(
            user_id, _title_from_message(request.message)
        )
    elif db.get_conversation(conversation_id, user_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.save_message(conversation_id, "user", request.message)

    summary = db.get_conversation_summary(conversation_id)
    cursor = summary["through_message_id"] if summary else 0
    rows = db.get_messages_since(conversation_id, after_id=cursor)

    system_prompt = _build_system_prompt(SYSTEM_PROMPT, user_id, conversation_id)

    async with open_mcp_session(user_id, server_url=HEALTH_SERVER_URL) as session:
        tools = await get_tool_schemas(session) + LOCAL_TOOL_SCHEMAS

    rows = await maybe_fold(conversation_id, system_prompt, rows, tools)

    messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    usage: dict = {}

    async def event_stream():
        yield f"data: {json.dumps({'conversation_id': conversation_id})}\n\n"
        full_reply = ""
        async for chunk in process_query(user_id, conversation_id, messages, usage=usage):
            full_reply += chunk
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        db.save_message(conversation_id, "assistant", full_reply)
        if not is_unrestricted:
            total = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            db.increment_tokens_used(user_id, total)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

(Note: `GET /chat/history` is intentionally dropped — `GET /conversations/{id}/messages`, added in Task 5, replaces it.)

(No per-task pass/commit here — verification and commit happen once, below, after every task is implemented.)

---

## Finishing: verify and commit everything

- [x] **Step 1: Run the full backend test suite**

Run: `pytest tests/ -v`
Expected: PASS — every test added or modified across all six tasks (schema, CRUD, message/folding scoping, `chat_service.py` threading, `/conversations` router, `/chat` rewire), plus the full pre-existing suite with no regressions.

- [ ] **Step 2: Commit everything in one commit**

```bash
git add data/db.py backend/services/summarization_service.py backend/services/chat_service.py \
    backend/routes/conversations.py backend/routes/chat.py backend/agent.py \
    tests/data/test_db.py tests/backend/services/test_summarization_service.py \
    tests/backend/services/test_chat_service.py tests/backend/services/test_chat_service_otel.py \
    tests/backend/routes/test_conversations.py tests/backend/routes/test_chat.py
git commit -m "feat: multi-chat threads backend (conversations table, CRUD, per-conversation folding, /chat rewire)"
```
