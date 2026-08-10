# Conversation Summarization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound the token cost of `/chat` by folding old conversation history into a rolling per-user summary once the payload gets too large, instead of resending the entire unbounded history every turn — and do it with Postgres as the single source of truth for conversation state, not an in-memory dict, so the design survives restarts and doesn't require a fragile parallel id-tracking list.

**Architecture:** The `messages` table becomes the source of truth for *everything* sent to Claude, not just the human-readable text. Its `content` column changes from `TEXT` to `JSONB` so a row can hold either a plain string (a real user/assistant turn) or a list of content blocks (a `tool_use`/`tool_result` exchange) — the exact shape the Anthropic SDK sends and expects. A new `conversation_summaries` table holds one row per user (`summary_text`, `through_message_id`). On each `/chat` call: save the user's message, then reconstruct the message list Claude needs by querying `messages` for everything after the stored summary's cursor (`through_message_id`) — a small, indexed, bounded query regardless of how long the user's total history is. If that reconstructed list is too big (checked via the free `count_tokens` endpoint, including `tools`), fold the oldest rows into the summary with one cheap Claude call, persist the new summary and cursor, and continue with just the remaining recent rows. Every entry `process_query` generates mid-turn (tool calls, tool results) is persisted immediately, so there is no in-memory conversation state to keep in sync with Postgres — the alignment problem an earlier draft of this plan ran into (a shadow `message_ids` list trying to mirror a RAM-first `conversations` dict) is eliminated by construction, not patched.

**Tech Stack:** Python, FastAPI, psycopg (Postgres), Anthropic SDK (`claude-haiku-4-5`), pytest + testcontainers.

## Global Constraints

- Fold trigger: `input_tokens > 40_000` (20% of Haiku's 200K context window), checked via `client.messages.count_tokens` — **including `tools=`**, not just `system` and `messages` — before each `/chat` call.
- Recent window: the most recent 15 rows are never folded — they stay raw in every request.
- Model for the fold call: `claude-haiku-4-5` (same as the rest of the app — see `backend/agent.py`), no tools, plain text response.
- Tool results are capped at 4000 characters before ever being persisted or sent to Claude — see Task 4. This exists so a single oversized tool response can't defeat the 40k ceiling by hiding inside the always-protected recent window.
- `messages.content` is `JSONB`, holding either a plain string or a list of block dicts (plain `dict`, not SDK objects — SDK content blocks are converted via `.model_dump()` before persisting or returning from any function in this plan).
- `data/db.py` functions take/return plain types, use `get_connection()` + `conn.commit()`, tests live in `tests/data/test_db.py` using the `testcontainers` Postgres fixture from `conftest.py`. Follow this existing convention throughout.
- Out of scope: multi-instance cache coherency beyond what "always read from Postgres" already provides for free; key rotation or archival of old `conversation_summaries` rows; changing how `GET /chat/history` looks to the frontend (its response shape is unchanged — it still returns only human-readable text turns).

---

### Task 1: `messages.content` becomes `JSONB`; `save_message` accepts `str | list` and returns the new row's id

**Files:**
- Modify: `data/db.py`
- Test: `tests/data/test_db.py`

**Interfaces:**
- Produces: `db.save_message(user_id: str, role: str, content: str | list) -> int` — returns the new row's Postgres id. `content` is either a plain string (a real, human-readable turn) or a list of plain `dict` content blocks (a `tool_use`/`tool_result` exchange).

- [x] **Step 1: Write the failing tests**

Add to `tests/data/test_db.py` (add `save_message` is already imported; no new imports needed beyond what's already there):

```python
def test_save_message_returns_new_message_id():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    first_id = save_message(user_id, "user", "first")
    second_id = save_message(user_id, "user", "second")

    assert isinstance(first_id, int)
    assert second_id == first_id + 1


def test_messages_content_column_is_jsonb():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'messages' AND column_name = 'content'"
        ).fetchone()
    assert result[0] == "jsonb"


def test_save_message_stores_list_content_and_round_trips_via_get_messages_since():
    from data.db import get_messages_since  # written in Task 2; this test is exercised there

    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    block_content = [{"type": "tool_use", "id": "call-1", "name": "get_weekly_stats", "input": {}}]

    save_message(user_id, "assistant", block_content)

    rows = get_messages_since(user_id, after_id=0)
    assert rows[0]["content"] == block_content
```

Note: the third test imports `get_messages_since`, which doesn't exist until Task 2. Write it now (it documents the requirement), but don't run it until Task 2 is done — running it now will fail with `ImportError`, which is expected and fine to leave red until Task 2. Steps 2 and 4 below only run the first two tests.

- [x] **Step 2: Run the first two tests to verify they fail**

Run: `pytest tests/data/test_db.py -v -k "test_save_message_returns_new_message_id or test_messages_content_column_is_jsonb"`
Expected: FAIL — `test_save_message_returns_new_message_id` fails with `assert isinstance(None, int)`; `test_messages_content_column_is_jsonb` fails with `assert 'text' == 'jsonb'`.

- [x] **Step 3: Implement**

In `data/db.py`, add the import at the top of the file (after the existing `psycopg_pool` import):

```python
from psycopg.types.json import Json
```

Replace the `messages` table creation (lines 58-69) with:

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
```

No `TEXT`→`JSONB` migration is needed — this project is pre-launch with no real user data, so the `messages` table is dropped and recreated from scratch via Supabase directly rather than migrated in place.

Replace `save_message` (lines 186-192):

```python
def save_message(user_id: str, role: str, content: str | list) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (%s, %s, %s) RETURNING id",
            (user_id, role, Json(content)),
        ).fetchone()
        conn.commit()
    return row[0]
```

- [x] **Step 4: Run the first two tests to verify they pass**

Run: `pytest tests/data/test_db.py -v -k "test_save_message_returns_new_message_id or test_messages_content_column_is_jsonb"`
Expected: PASS. Also run `pytest tests/data/test_db.py -v -k test_save_message_then_get_messages_round_trips` to confirm the existing string round-trip test still passes unchanged (jsonb round-trips a plain string back to a plain string).

- [x] **Step 5: Commit**

```bash
git add data/db.py tests/data/test_db.py
git commit -m "feat: store message content as JSONB, save_message returns the new row's id"
```

---

### Task 2: `get_messages_since` (reconstruction query) and filter `get_messages` (display) to text-only rows

**Files:**
- Modify: `data/db.py:195-211` (existing `get_messages`)
- Test: `tests/data/test_db.py`

**Interfaces:**
- Consumes: `db.save_message` (Task 1).
- Produces: `db.get_messages_since(user_id: str, after_id: int) -> list[dict]` — returns `[{"id": int, "role": str, "content": str | list}, ...]` ordered ascending by id, for every row with `id > after_id` (pass `after_id=0` for "from the beginning"). Includes **every** row regardless of content shape — this is what reconstructs the array sent to Claude.
- `db.get_messages` (existing, used by `GET /chat/history`) now excludes rows whose `content` is a list (tool_use/tool_result plumbing) — the frontend chat log should only ever show real text turns. Signature and return shape are unchanged.

- [x] **Step 1: Write the failing tests**

Add to `tests/data/test_db.py`:

```python
def test_get_messages_since_returns_rows_after_cursor_ascending():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    ids = [save_message(user_id, "user", f"m{i}") for i in range(5)]

    rows = get_messages_since(user_id, after_id=ids[1])

    assert [r["content"] for r in rows] == ["m2", "m3", "m4"]
    assert [r["id"] for r in rows] == ids[2:]


def test_get_messages_since_zero_returns_everything():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    ids = [save_message(user_id, "user", f"m{i}") for i in range(3)]

    rows = get_messages_since(user_id, after_id=0)

    assert [r["id"] for r in rows] == ids


def test_get_messages_since_includes_block_content_rows():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    save_message(user_id, "user", "text turn")
    tool_block = [{"type": "tool_use", "id": "call-1", "name": "x", "input": {}}]
    save_message(user_id, "assistant", tool_block)

    rows = get_messages_since(user_id, after_id=0)

    assert [r["content"] for r in rows] == ["text turn", tool_block]


def test_get_messages_excludes_block_content_rows_from_display():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    save_message(user_id, "user", "text turn")
    save_message(user_id, "assistant", [{"type": "tool_use", "id": "call-1", "name": "x", "input": {}}])

    messages, _ = get_messages(user_id, before_id=None, limit=20)

    assert [m["content"] for m in messages] == ["text turn"]
```

Add `get_messages_since` to the import block at the top of `tests/data/test_db.py` (next to `get_messages`).

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/test_db.py -v -k get_messages_since`
Expected: FAIL — `ImportError` (function doesn't exist yet). The `test_get_messages_excludes_block_content_rows_from_display` test will fail once `get_messages_since` exists to import, or can be run separately: `pytest tests/data/test_db.py -v -k test_get_messages_excludes_block_content_rows_from_display` should currently FAIL because the assertion expects only `"text turn"` but the un-filtered query also returns the block-content row (which, being a list, doesn't equal a string — the list comprehension will include it and the list lengths/values won't match `["text turn"]`).

- [x] **Step 3: Implement**

In `data/db.py`, add after `save_message`:

```python
def get_messages_since(user_id: str, after_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, role, content FROM messages WHERE user_id = %s AND id > %s ORDER BY id",
            (user_id, after_id),
        ).fetchall()
    return [{"id": row[0], "role": row[1], "content": row[2]} for row in rows]
```

Replace `get_messages` (lines 195-211) — add the `jsonb_typeof` filter to the `WHERE` clause:

```python
def get_messages(user_id: str, before_id: int | None, limit: int) -> tuple[list[dict], bool]:
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
        {"id": row[0], "role": row[1], "content": row[2], "created_at": row[3]} for row in rows
    ]
    return messages, has_more
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/data/test_db.py -v`
Expected: PASS — full file, including the `get_messages_since` tests, the display-filter test, and the Task 1 test that imports `get_messages_since`.

- [x] **Step 5: Commit**

```bash
git add data/db.py tests/data/test_db.py
git commit -m "feat: add get_messages_since for full-history reconstruction; filter get_messages to text turns"
```

---

### Task 3: `conversation_summaries` table and CRUD

**Files:**
- Modify: `data/db.py`
- Test: `tests/data/test_db.py`

**Interfaces:**
- Produces: `db.get_conversation_summary(user_id: str) -> dict | None` — returns `{"summary_text": str, "through_message_id": int}` or `None` if no summary exists yet.
- Produces: `db.upsert_conversation_summary(user_id: str, summary_text: str, through_message_id: int) -> None`

- [x] **Step 1: Write the failing tests**

Add to `tests/data/test_db.py` (add `import data.db as db` near the top — the tests below use `db.get_conversation_summary`/`db.upsert_conversation_summary` qualified, since the existing import block imports everything else by name and this avoids a long addition to it):

```python
def test_init_db_creates_conversation_summaries_table():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'conversation_summaries' AND table_schema = 'public'"
        ).fetchall()
    columns = {row[0] for row in result}
    assert columns == {"user_id", "summary_text", "through_message_id", "updated_at"}


def test_get_conversation_summary_returns_none_when_absent():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    assert db.get_conversation_summary(user_id) is None


def test_upsert_then_get_conversation_summary_round_trips():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    db.upsert_conversation_summary(user_id, "Training for a fall marathon.", 42)

    summary = db.get_conversation_summary(user_id)
    assert summary == {"summary_text": "Training for a fall marathon.", "through_message_id": 42}


def test_upsert_conversation_summary_overwrites_existing():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    db.upsert_conversation_summary(user_id, "First summary.", 10)

    db.upsert_conversation_summary(user_id, "Second summary.", 25)

    summary = db.get_conversation_summary(user_id)
    assert summary == {"summary_text": "Second summary.", "through_message_id": 25}
```

Update the `clean_schema` fixture in the same file to also drop the new table:

```python
@pytest.fixture(autouse=True)
def clean_schema():
    init_db()
    yield
    with get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS conversation_summaries CASCADE")
        conn.execute("DROP TABLE IF EXISTS memories CASCADE")
        conn.execute("DROP TABLE IF EXISTS messages CASCADE")
        conn.execute("DROP TABLE IF EXISTS preferences CASCADE")
        conn.execute("DROP TABLE IF EXISTS oauth_tokens CASCADE")
        conn.execute("DROP TABLE IF EXISTS sessions CASCADE")
        conn.execute("DROP TABLE IF EXISTS users CASCADE")
        conn.commit()
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/test_db.py -v -k conversation_summar`
Expected: FAIL — `AttributeError: module 'data.db' has no attribute 'get_conversation_summary'`.

- [x] **Step 3: Implement**

In `data/db.py`, add the table creation inside `init_db()`, after the `memories` index block:

```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                summary_text TEXT NOT NULL,
                through_message_id INTEGER NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
```

Add the CRUD functions after `get_memories`:

```python
def get_conversation_summary(user_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT summary_text, through_message_id FROM conversation_summaries WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return {"summary_text": row[0], "through_message_id": row[1]}


def upsert_conversation_summary(user_id: str, summary_text: str, through_message_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversation_summaries (user_id, summary_text, through_message_id, updated_at)
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

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/data/test_db.py -v -k conversation_summar`
Expected: PASS (4 tests)

- [x] **Step 5: Commit**

```bash
git add data/db.py tests/data/test_db.py
git commit -m "feat: add conversation_summaries table and CRUD"
```

---

### Task 4: Cap tool_result size in `call_tools`

**Files:**
- Modify: `backend/services/chat_service.py:80-102`
- Test: `tests/backend/services/test_chat_service.py`

**Interfaces:**
- Produces: `MAX_TOOL_RESULT_CHARS: int` (module constant, `4000`). `call_tools` truncates any tool result longer than this before it ever becomes part of a message.

This is independent of the rest of this plan and fixed first because Task 6 (persisting every `process_query` turn) touches the same function — better to land this narrower change on its own.

- [x] **Step 1: Write the failing test**

Add to `tests/backend/services/test_chat_service.py`:

```python
def test_call_tools_truncates_large_tool_results():
    from backend.services.chat_service import MAX_TOOL_RESULT_CHARS, call_tools

    open_mcp_session, mock_session = _mock_session([])
    mock_session.call_tool.side_effect = lambda name, args: "x" * 10_000

    block = MagicMock(type="tool_use", id="call-1")
    block.name = "get_recent_runs"
    block.input = {"days": 90}

    results = asyncio.run(call_tools("user-123", mock_session, [block]))

    assert results[0]["content"] == ("x" * MAX_TOOL_RESULT_CHARS) + "... [truncated]"


def test_call_tools_leaves_small_tool_results_untouched():
    from backend.services.chat_service import call_tools

    open_mcp_session, mock_session = _mock_session([])
    mock_session.call_tool.side_effect = lambda name, args: "short result"

    block = MagicMock(type="tool_use", id="call-1")
    block.name = "get_weekly_stats"
    block.input = {}

    results = asyncio.run(call_tools("user-123", mock_session, [block]))

    assert results[0]["content"] == "short result"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/backend/services/test_chat_service.py -v -k truncat`
Expected: FAIL — `ImportError: cannot import name 'MAX_TOOL_RESULT_CHARS'` for the first test; the second currently passes already (no truncation needed for a short string) but run both together for a clean baseline.

- [x] **Step 3: Implement**

In `backend/services/chat_service.py`, add the constant near the top (after `LOCAL_TOOLS`):

```python
MAX_TOOL_RESULT_CHARS = 4000
```

In `call_tools`, replace the `content = str(result)` line:

```python
                content = str(result)
                if len(content) > MAX_TOOL_RESULT_CHARS:
                    content = content[:MAX_TOOL_RESULT_CHARS] + "... [truncated]"
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/services/test_chat_service.py -v`
Expected: PASS (full file — confirms no regression in the existing `call_tools`/`process_query` tests)

- [x] **Step 5: Commit**

```bash
git add backend/services/chat_service.py tests/backend/services/test_chat_service.py
git commit -m "fix: cap tool_result size so a single oversized response can't defeat the fold ceiling"
```

---

### Task 5: Persist every turn `process_query` generates, not just the final reply

**Files:**
- Modify: `backend/services/chat_service.py:36-77`
- Test: `tests/backend/services/test_chat_service.py`

**Interfaces:**
- Consumes: `db.save_message` returning `int` and accepting `str | list` (Task 1).
- Produces: `process_query` now persists the intermediate `assistant` (tool_use) and `user` (tool_result) turns it generates via `db.save_message`, converting SDK content blocks to plain dicts via `.model_dump()` first. It does **not** persist the final reply itself — that stays the caller's responsibility (Task 8), exactly as today, to avoid writing the same turn twice under two different representations.

This is what makes Postgres the actual source of truth: previously, only the outer user question and outer final answer were ever saved — everything `process_query` did internally (tool calls, tool results) lived only in the RAM list passed into it and vanished after the request. After this task, every entry that goes to Claude has a corresponding Postgres row.

- [x] **Step 1: Write the failing test**

Add to `tests/backend/services/test_chat_service.py`:

```python
def test_process_query_persists_intermediate_tool_turns():
    from backend.services.chat_service import process_query

    open_mcp_session, mock_session = _mock_session(["get_weekly_stats"])
    mock_session.call_tool.side_effect = lambda name, args: "42km this week"

    tool_use_block = MagicMock(type="tool_use", id="call-1")
    tool_use_block.name = "get_weekly_stats"
    tool_use_block.input = {}
    tool_use_block.model_dump.return_value = {
        "type": "tool_use", "id": "call-1", "name": "get_weekly_stats", "input": {}
    }
    tool_call_response = MagicMock(stop_reason="tool_use", content=[tool_use_block])

    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    final_response = MagicMock(stop_reason="end_turn", content=[text_block])

    with patch("backend.services.chat_service.open_mcp_session", open_mcp_session), patch(
        "backend.services.chat_service.db.get_memories", return_value=[]
    ), patch("backend.services.chat_service.db.save_message") as mock_save_message, patch(
        "backend.agent.client"
    ) as mock_client:
        mock_client.messages.create.side_effect = [tool_call_response, final_response]

        reply = asyncio.run(process_query("user-123", [{"role": "user", "content": "hi"}]))

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

Update the two existing tests that build fake `response.content` blocks so `.model_dump()` returns something real instead of an auto-generated `MagicMock`:

In `test_process_query_merges_local_tool_schemas_with_mcp_tools`, change:

```python
    fake_response.content = [MagicMock(type="text", text="done")]
```

to:

```python
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]
```

Apply the same change in `test_process_query_injects_memories_into_system_prompt` (identical line, same fix).

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/backend/services/test_chat_service.py -v -k persists_intermediate`
Expected: FAIL — `mock_save_message.call_count == 0` (nothing is persisted yet).

Also run the two updated existing tests to confirm they still pass with the `model_dump` fix applied (they should, since `process_query` doesn't call `.model_dump()` yet — this just gets the fixtures ready ahead of Step 3): `pytest tests/backend/services/test_chat_service.py -v -k "merges_local_tool_schemas or injects_memories"`

- [x] **Step 3: Implement**

In `backend/services/chat_service.py`, replace `process_query` (lines 45-77):

```python
async def process_query(user_id: str, messages: list[dict]) -> str:
    """Call Claude, executing any requested tools, until it gives a final answer."""
    from backend.agent import SYSTEM_PROMPT, client, model

    system_prompt = _build_system_prompt(SYSTEM_PROMPT, user_id)

    async with open_mcp_session(user_id) as session:
        tools = await get_tool_schemas(session) + LOCAL_TOOL_SCHEMAS

        while True:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=system_prompt,
                tools=tools,
                tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                messages=messages,
            )

            content_dicts = [block.model_dump() for block in response.content]
            messages.append({"role": "assistant", "content": content_dicts})

            if response.stop_reason != "tool_use":
                reply = "\n".join(
                    block["text"] for block in content_dicts if block["type"] == "text"
                )
                return reply

            db.save_message(user_id, "assistant", content_dicts)

            tool_results = await call_tools(user_id, session, response.content)
            messages.append({"role": "user", "content": tool_results})
            db.save_message(user_id, "user", tool_results)
```

Note the final turn is deliberately **not** persisted here — `messages.append(...)` still records it in the local working list (needed if `process_query` ever loops again, and harmless once it returns), but the caller (Task 8's `chat.py`) persists the final reply as a plain string, matching what it already does today. Persisting it here too would write the same turn twice in two different shapes.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/services/test_chat_service.py -v`
Expected: PASS (full file)

- [x] **Step 5: Commit**

```bash
git add backend/services/chat_service.py tests/backend/services/test_chat_service.py
git commit -m "feat: persist every tool-loop turn process_query generates, not just the final reply"
```

---

### Task 6: Fold logic — `backend/services/summarization_service.py`

**Files:**
- Create: `backend/services/summarization_service.py`
- Test: `tests/backend/services/test_summarization_service.py`

**Interfaces:**
- Consumes: `data.db.get_conversation_summary`, `data.db.upsert_conversation_summary` (Task 3); `backend.agent.client`, `backend.agent.model` (existing).
- Produces:
  - `FOLD_TOKEN_THRESHOLD: int` (module constant, `40_000`)
  - `KEEP_RECENT_MESSAGES: int` (module constant, `15`)
  - `async def maybe_fold(user_id: str, system_prompt: str, rows: list[dict], tools: list[dict]) -> list[dict]` — `rows` is exactly the shape `db.get_messages_since` returns (`{"id": int, "role": str, "content": str | list}`, ordered ascending by id). If folding isn't needed, returns `rows` unchanged. If it is, folds every row before the last `KEEP_RECENT_MESSAGES` into the stored summary (merging with any existing summary text), persists the new summary with `through_message_id` set to the last folded row's real id, and returns only the remaining (unfolded) rows. Because every row in `rows` came from Postgres, every row has a real id — there is no id-less entry to special-case, unlike an in-memory-first design would require.

- [x] **Step 1: Write the failing tests**

Create `tests/backend/services/test_summarization_service.py`:

```python
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _count_tokens_result(input_tokens: int):
    return SimpleNamespace(input_tokens=input_tokens)


def _text_response(text: str):
    block = MagicMock(type="text", text=text)
    return SimpleNamespace(content=[block])


def test_maybe_fold_returns_rows_unchanged_when_under_threshold():
    from backend.services.summarization_service import maybe_fold

    rows = [{"id": 1, "role": "user", "content": "hi"}]

    with patch("backend.services.summarization_service.client") as mock_client:
        mock_client.messages.count_tokens.return_value = _count_tokens_result(100)

        result = asyncio.run(maybe_fold("user-123", "system prompt", rows, tools=[]))

    mock_client.messages.create.assert_not_called()
    assert result == rows


def test_maybe_fold_returns_rows_unchanged_when_at_or_below_recent_window():
    from backend.services.summarization_service import KEEP_RECENT_MESSAGES, maybe_fold

    rows = [{"id": i, "role": "user", "content": f"msg {i}"} for i in range(KEEP_RECENT_MESSAGES)]

    with patch("backend.services.summarization_service.client") as mock_client:
        mock_client.messages.count_tokens.return_value = _count_tokens_result(50_000)

        result = asyncio.run(maybe_fold("user-123", "system prompt", rows, tools=[]))

    mock_client.messages.create.assert_not_called()
    assert result == rows


def test_maybe_fold_folds_oldest_rows_and_returns_remainder():
    from backend.services.summarization_service import KEEP_RECENT_MESSAGES, maybe_fold

    total = KEEP_RECENT_MESSAGES + 3
    rows = [{"id": 100 + i, "role": "user", "content": f"msg {i}"} for i in range(total)]

    with patch("backend.services.summarization_service.client") as mock_client, patch(
        "backend.services.summarization_service.db"
    ) as mock_db:
        mock_client.messages.count_tokens.return_value = _count_tokens_result(50_000)
        mock_client.messages.create.return_value = _text_response("Compressed summary.")
        mock_db.get_conversation_summary.return_value = None

        result = asyncio.run(maybe_fold("user-123", "system prompt", rows, tools=[]))

    assert len(result) == KEEP_RECENT_MESSAGES
    assert result[0]["content"] == "msg 3"  # first 3 folded away
    assert result[0]["id"] == 103

    mock_db.upsert_conversation_summary.assert_called_once_with(
        "user-123", "Compressed summary.", 102  # id of the last folded row
    )


def test_maybe_fold_includes_existing_summary_in_the_fold_prompt():
    from backend.services.summarization_service import KEEP_RECENT_MESSAGES, maybe_fold

    total = KEEP_RECENT_MESSAGES + 1
    rows = [{"id": i, "role": "user", "content": f"msg {i}"} for i in range(total)]

    with patch("backend.services.summarization_service.client") as mock_client, patch(
        "backend.services.summarization_service.db"
    ) as mock_db:
        mock_client.messages.count_tokens.return_value = _count_tokens_result(50_000)
        mock_client.messages.create.return_value = _text_response("New summary.")
        mock_db.get_conversation_summary.return_value = {
            "summary_text": "Existing summary text.",
            "through_message_id": 0,
        }

        asyncio.run(maybe_fold("user-123", "system prompt", rows, tools=[]))

    fold_call_kwargs = mock_client.messages.create.call_args.kwargs
    prompt_text = fold_call_kwargs["messages"][0]["content"]
    assert "Existing summary text." in prompt_text


def test_maybe_fold_passes_tools_to_count_tokens():
    from backend.services.summarization_service import maybe_fold

    rows = [{"id": 1, "role": "user", "content": "hi"}]
    fake_tools = [{"name": "get_weekly_stats", "description": "", "input_schema": {}}]

    with patch("backend.services.summarization_service.client") as mock_client:
        mock_client.messages.count_tokens.return_value = _count_tokens_result(100)

        asyncio.run(maybe_fold("user-123", "system prompt", rows, tools=fake_tools))

    call_kwargs = mock_client.messages.count_tokens.call_args.kwargs
    assert call_kwargs["tools"] == fake_tools


def test_content_to_text_handles_plain_string():
    from backend.services.summarization_service import _content_to_text

    assert _content_to_text("hello") == "hello"


def test_content_to_text_handles_text_block_dicts():
    from backend.services.summarization_service import _content_to_text

    content = [{"type": "text", "text": "hello"}]
    assert _content_to_text(content) == "hello"


def test_content_to_text_handles_tool_result_block_dicts():
    from backend.services.summarization_service import _content_to_text

    content = [{"type": "tool_result", "tool_use_id": "abc", "content": "42km this week"}]
    assert "42km this week" in _content_to_text(content)


def test_content_to_text_handles_tool_use_block_dicts():
    from backend.services.summarization_service import _content_to_text

    content = [{"type": "tool_use", "id": "abc", "name": "get_weekly_stats", "input": {}}]
    assert "get_weekly_stats" in _content_to_text(content)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/backend/services/test_summarization_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.summarization_service'`

- [x] **Step 3: Implement**

Create `backend/services/summarization_service.py`:

```python
import data.db as db
from backend.agent import client, model

FOLD_TOKEN_THRESHOLD = 40_000
KEEP_RECENT_MESSAGES = 15

FOLD_SYSTEM_PROMPT = "You compress running-coach conversation history into a compact summary."

FOLD_USER_PROMPT_TEMPLATE = """Existing summary (may be empty on first fold):
{existing_summary}

New messages to fold in:
{chunk_text}

Write an updated summary under 300 words. Focus on conversational context and in-progress \
topics — do not restate durable facts (goals, injuries, preferences) that would already be \
captured separately via long-term memory. Preserve concrete plans discussed and decisions made \
over conversational flavor. Do not restate what's already covered — merge and compress."""


def _content_to_text(content) -> str:
    if isinstance(content, str):
        return content

    parts = []
    for block in content:
        block_type = block.get("type")
        if block_type == "text":
            parts.append(block.get("text", ""))
        elif block_type == "tool_result":
            parts.append(f"[tool result: {block.get('content')}]")
        elif block_type == "tool_use":
            parts.append(f"[used tool: {block.get('name', '?')}]")
        else:
            parts.append(f"[{block_type}]")
    return " ".join(parts)


def _render_chunk(chunk: list[dict]) -> str:
    lines = [f"{row['role']}: {_content_to_text(row['content'])}" for row in chunk]
    return "\n".join(lines)


async def maybe_fold(
    user_id: str, system_prompt: str, rows: list[dict], tools: list[dict]
) -> list[dict]:
    messages_for_count = [{"role": r["role"], "content": r["content"]} for r in rows]
    count = client.messages.count_tokens(
        model=model, system=system_prompt, tools=tools, messages=messages_for_count
    )
    if count.input_tokens <= FOLD_TOKEN_THRESHOLD:
        return rows
    if len(rows) <= KEEP_RECENT_MESSAGES:
        return rows

    cutoff = len(rows) - KEEP_RECENT_MESSAGES
    chunk = rows[:cutoff]

    existing = db.get_conversation_summary(user_id)
    existing_summary = existing["summary_text"] if existing else "(none yet)"

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=FOLD_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": FOLD_USER_PROMPT_TEMPLATE.format(
                    existing_summary=existing_summary,
                    chunk_text=_render_chunk(chunk),
                ),
            }
        ],
    )
    new_summary = next(block.text for block in response.content if block.type == "text")

    db.upsert_conversation_summary(user_id, new_summary, chunk[-1]["id"])

    return rows[cutoff:]
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/services/test_summarization_service.py -v`
Expected: PASS (10 tests)

- [x] **Step 5: Commit**

```bash
git add backend/services/summarization_service.py tests/backend/services/test_summarization_service.py
git commit -m "feat: add DB-row-based conversation fold logic (token-threshold summarization)"
```

---

### Task 7: Inject the rolling summary into the system prompt

**Files:**
- Modify: `backend/services/chat_service.py:36-42`
- Test: `tests/backend/services/test_chat_service.py`

**Interfaces:**
- Consumes: `data.db.get_conversation_summary` (Task 3).
- Produces: `_build_system_prompt` now also appends the stored summary (if any) after the memories block. No signature change.

- [x] **Step 1: Write the failing test**

Add to `tests/backend/services/test_chat_service.py`:

```python
def test_process_query_injects_conversation_summary_into_system_prompt():
    from backend.services.chat_service import process_query

    open_mcp_session, mock_session = _mock_session([])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]

    fake_summary = {"summary_text": "User is training for a fall marathon.", "through_message_id": 5}

    with patch("backend.services.chat_service.open_mcp_session", open_mcp_session), patch(
        "backend.services.chat_service.db.get_memories", return_value=[]
    ), patch(
        "backend.services.chat_service.db.get_conversation_summary", return_value=fake_summary
    ), patch("backend.agent.client") as mock_client:
        mock_client.messages.create.return_value = fake_response

        asyncio.run(process_query("user-123", [{"role": "user", "content": "hi"}]))

        system_prompt = mock_client.messages.create.call_args.kwargs["system"]
        assert "User is training for a fall marathon." in system_prompt


def test_process_query_omits_summary_section_when_none_exists():
    from backend.services.chat_service import process_query

    open_mcp_session, mock_session = _mock_session([])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]

    with patch("backend.services.chat_service.open_mcp_session", open_mcp_session), patch(
        "backend.services.chat_service.db.get_memories", return_value=[]
    ), patch(
        "backend.services.chat_service.db.get_conversation_summary", return_value=None
    ), patch("backend.agent.client") as mock_client:
        mock_client.messages.create.return_value = fake_response

        asyncio.run(process_query("user-123", [{"role": "user", "content": "hi"}]))

        system_prompt = mock_client.messages.create.call_args.kwargs["system"]
        assert "Summary of earlier conversation" not in system_prompt
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/backend/services/test_chat_service.py -v -k conversation_summary`
Expected: FAIL — `AttributeError: <module 'backend.services.chat_service'> does not have the attribute 'get_conversation_summary'` (patch target doesn't exist yet).

- [x] **Step 3: Implement**

In `backend/services/chat_service.py`, replace `_build_system_prompt` (lines 36-42):

```python
def _build_system_prompt(base_prompt: str, user_id: str) -> str:
    prompt = base_prompt

    memories = db.get_memories(user_id)
    if memories:
        facts = "\n".join(f"- {m['fact']}" for m in memories)
        prompt = f"{prompt}\n\nKnown facts about this user:\n{facts}"

    summary = db.get_conversation_summary(user_id)
    if summary:
        prompt = f"{prompt}\n\nSummary of earlier conversation:\n{summary['summary_text']}"

    return prompt
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/services/test_chat_service.py -v`
Expected: PASS (all tests in the file)

- [x] **Step 5: Commit**

```bash
git add backend/services/chat_service.py tests/backend/services/test_chat_service.py
git commit -m "feat: inject rolling conversation summary into system prompt"
```

---

### Task 8: Rewrite `/chat` to reconstruct history from Postgres; remove the in-memory `conversations` dict

**Files:**
- Modify: `backend/agent.py:33`
- Modify: `backend/routes/chat.py`
- Test: `tests/backend/routes/test_chat.py`

**Interfaces:**
- Consumes: `db.get_messages_since`, `db.get_conversation_summary` (Task 2, 3); `summarization_service.maybe_fold` (Task 6); `chat_service._build_system_prompt`, `chat_service.LOCAL_TOOL_SCHEMAS`, `chat_service.process_query` (Task 7); `mcp_client.get_tool_schemas`, `mcp_client.open_mcp_session` (existing).
- Removes: `backend.agent.conversations` (the in-memory per-user dict). Nothing else in the codebase references it (only `backend/routes/chat.py` did).

This is the task that actually eliminates the RAM-first design. `/chat` no longer holds any state between requests — each call re-derives exactly what it needs from Postgres, bounded by the summary's cursor.

- [x] **Step 1: Write the failing test**

Add to `tests/backend/routes/test_chat.py`:

```python
def test_post_chat_calls_maybe_fold_with_rows_since_last_summary(client, monkeypatch):
    from backend.routes import chat as chat_route

    fold_mock = AsyncMock(side_effect=lambda user_id, system_prompt, rows, tools: rows)
    monkeypatch.setattr(chat_route, "maybe_fold", fold_mock)

    cookies = _session_cookie_for_new_user(client)
    response = client.post("/chat", json={"message": "hi"}, cookies=cookies)

    assert response.status_code == 200
    fold_mock.assert_awaited_once()
    call_args = fold_mock.await_args
    rows_arg = call_args.args[2]
    assert [r["content"] for r in rows_arg] == ["hi"]
```

Update the `client` fixture in the same file to mock the new collaborators `/chat` now calls directly (`maybe_fold`, `open_mcp_session`, `get_tool_schemas`), so tests don't hit a real MCP server or real Claude token-counting:

```python
@pytest.fixture
def client(monkeypatch):
    from backend.agent import app
    from backend.routes import chat as chat_route

    monkeypatch.setattr(chat_route, "process_query", AsyncMock(return_value="mocked reply"))

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

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/routes/test_chat.py -v -k maybe_fold`
Expected: FAIL — `AttributeError: <module 'backend.routes.chat'> does not have the attribute 'maybe_fold'`

- [x] **Step 3: Implement**

In `backend/agent.py`, delete line 33 entirely:

```python
conversations: dict[str, list] = {}  # per-user message history, keyed by user_id
```

Replace `backend/routes/chat.py` in full:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

import data.db as db
from backend.dependencies import require_user
from backend.services.chat_service import LOCAL_TOOL_SCHEMAS, _build_system_prompt, process_query
from backend.services.mcp_client import get_tool_schemas, open_mcp_session
from backend.services.summarization_service import maybe_fold

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


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
    reply = await process_query(user_id, messages)
    db.save_message(user_id, "assistant", reply)

    return {"reply": reply}


@router.get("/chat/history")
def get_chat_history(
    before_id: int | None = None, limit: int = 20, user_id: str = Depends(require_user)
):
    messages, has_more = db.get_messages(user_id, before_id=before_id, limit=limit)
    return {"messages": messages, "has_more": has_more}
```

Note: `/chat` now opens an MCP session and fetches tool schemas twice per request — once here, to measure the real payload size for the fold check, and once more inside `process_query` for the actual Claude call. This mirrors the same trade-off already accepted for `_build_system_prompt` (called once here, once inside `process_query`): both are small, cheap, per-request duplicate reads in exchange for keeping each function's responsibility self-contained. Not worth threading extra parameters through `process_query`'s signature to save two network calls — revisit only if this shows up as a real latency problem.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/routes/test_chat.py -v`
Expected: PASS (all tests in the file, including the new one — the existing persistence and pagination tests should pass unmodified against the updated fixture)

- [x] **Step 5: Run the full backend test suite**

Run: `pytest tests/ -v`
Expected: PASS (no regressions in `tests/backend/`, `tests/data/`, `tests/auth/`, `tests/mcp/`, `tests/mcp_servers/`)

- [x] **Step 6: Commit**

```bash
git add backend/agent.py backend/routes/chat.py tests/backend/routes/test_chat.py
git commit -m "feat: reconstruct chat history from Postgres per-request, remove in-memory conversations dict"
```

---

## Post-plan notes (not tasks — context for whoever picks this up next)

- **No more server-restart gap.** Because `/chat` reconstructs its working message list from Postgres on every request (Task 8) and every turn — including tool_use/tool_result plumbing — is persisted as it happens (Task 5), a restart loses nothing. This closes the gap the original version of this plan explicitly deferred.
- **Why `messages.content` is `JSONB` and not two columns or a separate table.** Keeping one `content` column that's either a string or a list of blocks means one row always equals exactly one entry in the array sent to Claude — a 1:1 mapping. An earlier draft of this plan tried to bridge a RAM-first design with a lossy, partial Postgres mirror via a hand-maintained parallel `message_ids` list; that fell apart the moment a tool call happened mid-turn (the two lists silently went out of alignment). Making Postgres the actual source of truth removes the need for that parallel structure entirely, rather than patching it.
- **`GET /chat/history` behavior is unchanged from the user's perspective.** It still returns only human-readable text turns (Task 2's `jsonb_typeof(content) = 'string'` filter) — tool machinery was never meant to be user-visible and still isn't.
- **`FOLD_TOKEN_THRESHOLD`, `KEEP_RECENT_MESSAGES`, and `MAX_TOOL_RESULT_CHARS` are hardcoded constants**, not environment variables — matches this codebase's existing style (e.g. `backend/agent.py`'s `model` constant). Revisit only if there's a concrete need to tune them per-environment.
- **Latency of the reconstruction query stays bounded regardless of a user's total history length**, because `get_messages_since` is always called with the summary's `through_message_id` as a cursor — it only ever returns rows accumulated since the last fold, not the full conversation. The existing `idx_messages_user_id_id` index on `(user_id, id DESC)` already covers this query pattern; no new index is needed.
