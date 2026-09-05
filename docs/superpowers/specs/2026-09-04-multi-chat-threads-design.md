# Multi-Chat Threads ("New Chat" + History) — Design

## Problem

Chat today is a single, ever-growing flat conversation per user (`docs/superpowers/specs/2026-08-09-chat-history-persistence-design.md`) — `messages` and `conversation_summaries` are keyed only by `user_id`. There is no concept of "a chat" as a distinct, nameable thread, no way to start fresh without losing/mixing context, and no way to revisit an older topic separately from the current one.

## Scope

Introduce ChatGPT-style multiple persistent conversation threads per user: create, list, rename, pin, delete, search. Superseded: the single-thread model from the 2026-08-09 spec (that spec's `messages`/history mechanics are extended with a `conversation_id`, not replaced).

Out of scope: real-time cross-device sync (see Decisions), goals/notifications integration, changing the token-budget or long-term-memory scoping (both correctly stay per-`user_id`, not per-conversation).

## Decisions

- **Existing history is discarded**, not migrated. `messages` and `conversation_summaries` gain a `NOT NULL conversation_id` FK — no backfill path needed for pre-existing flat rows.
- **Titling: first-message-as-title.** The conversation's title is the user's first message, truncated (no LLM call, no manual-only requirement — matches "Marathon taper plan"-style mockup titles for free).
- **Lazy creation.** Clicking "New chat" only resets the frontend view; no `conversations` row is created until the first message is actually sent. Avoids empty-chat clutter in the sidebar.
- **Hard delete.** Deleting a conversation is immediate and permanent (`ON DELETE CASCADE` removes its messages + summary) — matches the trash-can icon in the mockup, no archive/undo.
- **Deleting the active conversation** redirects the frontend to the empty "New chat" state (not to another existing conversation).
- **Search is title-only** (`ILIKE` on `conversations.title`), not full message-content search.
- **Rename rejects empty input** — a blank title is a validation error; it does not silently fall back to "New chat" or the previous title.
- **Pinning only affects sort order** — pinned conversations render in a separate "Pinned" section above "Recent"; pinning does not change folding behavior, deletion eligibility, or anything else.
- **Folding becomes per-conversation.** Each conversation gets its own independent 40k-token fold threshold (see Summarization below) — this is a behavior improvement over today, where a user's Nth conversation would fold sooner because it competed with every prior conversation's token count.
- **No global state library.** React Query (already in use) covers the two pieces of shared state this feature needs — the conversations list and each conversation's messages, both server-persisted and cache-keyed by `conversationId`. The "which conversation is active" state is owned by the URL route param, not app state, so we get back/forward nav and refresh-safety for free. Introducing Zustand/Redux here would solve a problem this feature doesn't have.
- **No real-time multi-device sync.** All state is server-persisted; a second device simply sees stale data until its next fetch. React Query's default `refetchOnWindowFocus`/refetch-on-remount is sufficient for a personal-use app — genuinely simultaneous multi-device editing of the same thread is out of scope as a rare, low-stakes edge case. Deleting an already-deleted conversation from a stale second-device view is a no-op (cascade delete is idempotent), not an error case.

## Data model

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New chat',
    pinned BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conversations_user_id_updated_at
    ON conversations (user_id, pinned DESC, updated_at DESC);
```

`messages` (from the 2026-08-09 spec) changes:

```sql
ALTER TABLE messages ADD COLUMN conversation_id UUID NOT NULL
    REFERENCES conversations(id) ON DELETE CASCADE;
-- superseding the pre-existing table definition on fresh init_db(), not an in-place migration
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_id
    ON messages (conversation_id, id DESC);
```

`conversation_summaries` changes its primary key from `user_id` to `conversation_id`:

```sql
CREATE TABLE IF NOT EXISTS conversation_summaries (
    conversation_id UUID PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL,
    through_message_id INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`updated_at` on `conversations` is bumped whenever a message is saved to it — this drives "Recent" sort order in the sidebar.

## Backend

New `data/db.py` functions:
- `create_conversation(user_id, title) -> conversation_id`
- `list_conversations(user_id, search=None) -> list[dict]` — ordered `pinned DESC, updated_at DESC`; `search` does `ILIKE` on `title`
- `rename_conversation(conversation_id, user_id, title) -> None` — raises on empty title; `user_id` included in the `WHERE` clause so one user can't rename another's conversation
- `set_pinned(conversation_id, user_id, pinned: bool) -> None`
- `delete_conversation(conversation_id, user_id) -> None`
- `get_conversation(conversation_id, user_id) -> dict | None` — ownership check, used to 404 cross-user access

Existing functions gain a `conversation_id` parameter in place of/alongside `user_id`:
- `save_message`, `get_messages`, `get_messages_since` — filter by `conversation_id`; also bump `conversations.updated_at` in the same transaction as `save_message`
- `get_conversation_summary`, `upsert_conversation_summary` — keyed by `conversation_id`

New router, `backend/routes/conversations.py`:
- `GET /conversations?search=` — list
- `POST /conversations` — create (used by the frontend only if it ever needs an explicit create separate from lazy-create-on-first-message; primarily conversations are created inline by `POST /chat`)
- `PATCH /conversations/{id}` — body `{title}` and/or `{pinned}`
- `DELETE /conversations/{id}`
- `GET /conversations/{id}/messages?before_id=&limit=` — replaces the old `/chat/history` (same keyset pagination shape)

`backend/routes/chat.py` changes:
- `POST /chat` request body gains `conversation_id: str | None`. `None` means "first message of a new chat" — the route creates the conversation (title = truncated message text) before proceeding, and returns the new `conversation_id` to the frontend in the response so it can update the URL/route.
- All `db.get_messages_since`, `maybe_fold`, `db.save_message` calls scope to the resolved `conversation_id` instead of `user_id`.
- `MAX_MESSAGE_CHARS` / token-budget checks (`_unrestricted_emails`, `get_tokens_used`) are unchanged — still per-`user_id`.
- `GET /chat/history` is removed in favor of `GET /conversations/{id}/messages`.

`summarization_service.py`: `maybe_fold(user_id, ...)` → `maybe_fold(conversation_id, ...)`; internals unchanged since it already only operates on the `rows` passed in.

Ownership checks: every conversation-scoped endpoint verifies `conversations.user_id == current user_id` (via `get_conversation`) before acting, returning 404 (not 403, to avoid leaking existence) on mismatch.

## Frontend

- New route structure: `frontend/app/[locale]/(app)/chat/[conversationId]/page.tsx`, with a `/chat` (no id) route rendering the empty "New chat" state.
- New `<ChatSidebar>` component (desktop: persistent left column per the mockup; mobile: a separate `/chat/list`-style screen navigated to via the hamburger icon) — renders "Pinned"/"Recent" sections, search input, per-row rename (pencil → inline edit), pin (star toggle), delete (trash, with the redirect-to-new-chat behavor if it's the active one).
- `chat-screen.tsx` splits: message list + composer stay, but `messages` state moves from local `useState` to a React Query query keyed by `["conversation", conversationId, "messages"]`, so switching threads via the sidebar swaps data without manual cache clearing.
- Sending the first message of a new chat (`conversationId` is `undefined`/absent): `POST /chat` returns the newly created `conversation_id`; frontend does a client-side route replace to `/chat/{conversationId}` and invalidates the `["conversations"]` list query so the sidebar picks up the new row.
- Conversations list: `["conversations", searchTerm]` query, refetch-on-focus (React Query default) is the sync mechanism across devices/tabs — no additional polling or websocket infrastructure.

## Testing

- Backend: conversation CRUD (create/list/rename/pin/delete), ownership enforcement (404 on cross-user access), cascade delete removes messages + summary, per-conversation folding isolation (two conversations' token counts don't interfere), title-from-first-message truncation, rename-empty-title rejection, search filters by title substring.
- Frontend: sidebar renders pinned/recent sections and search filtering; new-chat lazy-create (no row until first send); delete-active-conversation redirects to empty state; switching conversations swaps message list correctly (no stale cache bleed-through).

## Out of scope

- Full message-content search (title-only for now).
- Real-time cross-device sync (websockets/SSE push).
- Archive/soft-delete/undo.
- Migrating pre-existing flat chat history into the new model.
- Global frontend state management library.
