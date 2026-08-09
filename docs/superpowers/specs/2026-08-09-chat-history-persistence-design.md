# Chat History Persistence — Design

## Problem
Chat history lives only in the in-memory `conversations` dict in `backend/agent/`, keyed by `user_id`. It's lost on every backend restart and never displayed back to the user across sessions.

## Scope
Persist and display chat history only. This is explicitly separate from agent context management (which stays in-memory, untouched) and from any future context-window/summarization work.

## Decisions
- One continuous conversation thread per user (no thread/session concept, no titles).
- No retention cap — keep all messages indefinitely.
- Server-side keyset pagination; frontend loads newest messages first, older messages on scroll-up.
- Message content stored as raw text/markdown exactly as sent/received — no transformation. Frontend reuses the existing markdown renderer for both live and historical messages.
- Persistence is a pure side-effect write; nothing reads from the `messages` table to build agent/LLM context.

## Data model
New table in `data/db.py`:

```sql
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    role TEXT NOT NULL,       -- 'user' | 'assistant'
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_user_id_id ON messages (user_id, id DESC);
```

`id` (serial, monotonic) is the pagination cursor — avoids clock-skew issues with `created_at`.

## Backend
- `data/db.py`:
  - `save_message(user_id: str, role: str, content: str) -> None`
  - `get_messages(user_id: str, before_id: int | None, limit: int) -> tuple[list[dict], bool]` — keyset query (`WHERE user_id=%s AND (before_id IS NULL OR id < %s) ORDER BY id DESC LIMIT %s`), returns messages plus a `has_more` flag (fetch `limit+1` rows to detect it).
- `backend/routes/chat.py`:
  - After the existing `conversations` append + `process_query` call, additionally call `save_message` for the user's message and the assistant's reply. No change to agent context logic.
- New route `GET /chat/history?before_id=&limit=20` (default `limit=20`), protected by `require_user`, returns messages newest-first plus `has_more`.

## Frontend
- Chat screen fetches the latest page (`GET /chat/history`) on mount.
- Infinite-scroll-up loads older pages via `before_id` cursor (React Query, since it's already in use).
- Pages are reversed for oldest-to-newest display; existing markdown-rendering component is reused unchanged.

## Out of scope
- Agent/LLM context management (in-memory `conversations` dict) — untouched.
- Retention/archiving policy.
- Multiple named conversation threads.
- Search across history.
