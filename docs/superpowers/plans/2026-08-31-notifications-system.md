# Global Notifications System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a global, backend-driven notifications system — bell icon with unread count, shown identically on every screen (web + mobile) — first wired to the OAuth token-expiry failure that is currently silently swallowed (Connectors page shows "Connected" while the Dashboard quietly renders empty).

**Architecture:** A new `notifications` table in the existing Postgres instance (same pattern as `preferences`/`memories` in `data/db.py`, no new infra). A single creation point in `auth/auth.py`'s `get_valid_access_token` (the one place both MCP servers refresh Health/Calendar tokens) writes a notification the moment Google's refresh token is confirmed dead (`invalid_grant`), and deletes the now-useless token row in the same transaction. A new `backend/routes/notifications.py` exposes `GET /notifications` (list) and `PATCH /notifications/read-all` (mark-all-read). Resolution is wired into the existing OAuth success callbacks in `backend/routes/auth.py`. The frontend polls `GET /notifications` every 5 minutes via React Query and renders a bell + unread badge in a new shared header (`AppShell`), opening a shadcn `Sheet` (full-width on mobile) on click.

**Tech Stack:** FastAPI, Postgres (psycopg), Next.js/React Query, shadcn/ui `Sheet`, next-intl, Vitest + Testing Library (frontend), pytest (backend).

**Spec:** none — this plan is the direct output of an interactive design interview (grill-me) with the project owner, not a separate written spec. Key decisions locked in during that interview (see Global Constraints) take the place of a spec here.

## Global Constraints

- No new database or infrastructure. The `notifications` table lives in the same Postgres instance `data/db.py` already manages; `init_db()` creates it like every other table.
- Detection is **reactive only** — no scheduler/cron job. A notification is created exactly when a live request already hits the failure (e.g. `get_valid_access_token` refreshing a dead token), never by a background sweep.
- Delivery is **polling only** (5-minute interval via React Query `refetchInterval`) — no SSE/WebSocket/push. This is a deliberate choice to avoid holding an open connection per active tab, which would defeat Cloud Run's scale-to-zero.
- Duplicate prevention is **DB-enforced**, via a partial unique index (`UNIQUE (user_id, type) WHERE status != 'resolved'`), not app-level "check then insert" logic.
- Lifecycle is three states: `unread → read → resolved`. "Read" (user has seen it) is distinct from "resolved" (the underlying problem is actually fixed) — a user can read a notification without fixing anything.
- Scope boundary (decided explicitly, do not expand): only **asynchronous, backend-detected, durable, screen-independent** events go through this system. This plan implements exactly one such event (OAuth token expiry). Synchronous action failures that are immediately visible at the point of the action (chat send failure, avatar upload failure, preference save failure, plan-a-run failure, OAuth *connect* redirect failure) are explicitly **out of scope** — they keep their existing inline/toast handling and must not be migrated into this system by this plan.
- Notification text is **never stored in the DB** — only `type` and `action_href` are. The frontend translates `type` to display text via next-intl (`notifications.types.<type>`), so a German-locale user reads German, and there's no stored-English-string migration to do later if more locales are added. This is a deliberate correction from an earlier draft of this plan that stored a plain-English `message` column — caught in review before any row existed with that shape.
- Mark-all-read fires once, when the notifications Sheet opens — not per-item.
- Clicking a notification with a non-null `action_href` navigates there and closes the Sheet; a notification with no `action_href` just marks read in place.
- The bell and the user's avatar live in one shared header component, mounted once in `AppShell`, rendered in the same top-right position on all 4 screens (Dashboard, Coach, Connectors, Profile) and both breakpoints. This fixes an existing inconsistency as a side effect: today the avatar only appears on Dashboard (mobile-only, `dashboard-screen.tsx:111-113`) and Profile (a different avatar — the upload control, not a nav link, stays untouched).

---

## File Structure

- Modify: `data/db.py` — add `notifications` table to `init_db()`; add `Notification` dataclass and `create_notification`, `resolve_notification`, `list_notifications`, `mark_all_read` functions.
- Modify: `auth/auth.py` — on confirmed `invalid_grant`, delete the dead token row and insert a notification, in the same transaction/connection already holding the row lock (see Task 2 for why this can't reuse the plain `data.db` helpers directly).
- Create: `backend/routes/notifications.py` — `GET /notifications`, `PATCH /notifications/read-all`.
- Modify: `backend/agent.py` — register the new router.
- Modify: `backend/routes/auth.py` — `health_callback`/`calendar_callback` success paths call `resolve_notification`.
- Create: `frontend/lib/notifications-api.ts` — `Notification` type + `getNotifications`, `markAllRead`.
- Create: `frontend/hooks/use-notifications.ts` — polling React Query hook + mark-all-read mutation.
- Create: `frontend/components/notifications-bell.tsx` — bell icon + unread count badge, toggles the Sheet.
- Create: `frontend/components/notifications-sheet.tsx` — shadcn `Sheet` (full-width on mobile), list + empty state, click-to-navigate.
- Create: `frontend/components/app-header.tsx` — shared header: bell + avatar link to Profile.
- Modify: `frontend/components/app-shell.tsx` — mount `AppHeader` above `{children}`, both breakpoints.
- Modify: `frontend/components/dashboard-screen.tsx` — remove the now-superseded mobile-only avatar link (`lines 111-113`).
- Modify: `frontend/messages/en.json`, `frontend/messages/de.json` — new `notifications` translation namespace.
- Tests: `tests/data/test_db.py` (append), `tests/auth/test_auth.py` (append), `tests/backend/routes/test_notifications.py` (new), `tests/backend/routes/test_auth.py` (append), `frontend/tests/use-notifications.test.tsx` (new), `frontend/tests/notifications-bell.test.tsx` (new), `frontend/tests/notifications-sheet.test.tsx` (new), `frontend/tests/app-shell.test.tsx` (new).

---

### Task 1: `notifications` table and `data/db.py` CRUD

**Files:**
- Modify: `data/db.py`
- Test: `tests/data/test_db.py`

**Interfaces:**
- Produces: `Notification` dataclass — `id: int`, `user_id: str`, `type: str`, `action_href: str | None`, `status: str`, `created_at: datetime`. No `message` field — display text is derived from `type` on the frontend (next-intl key `notifications.types.<type>`), never stored in English (or any language) in the DB.
- Produces: `create_notification(user_id: str, type_: str, action_href: str | None = None) -> None` — no-ops (via `ON CONFLICT ... DO NOTHING`) if an unresolved notification of the same `(user_id, type)` already exists.
- Produces: `resolve_notification(user_id: str, type_: str) -> None` — marks any unresolved notification of that type resolved; no-op if none exists.
- Produces: `list_notifications(user_id: str) -> list[Notification]` — all non-resolved notifications for the user, newest first.
- Produces: `mark_all_read(user_id: str) -> None` — flips every `unread` notification for the user to `read`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/data/test_db.py` (add these names to the existing `from data.db import (...)` block too: `Notification`, `create_notification`, `resolve_notification`, `list_notifications`, `mark_all_read`):

```python
def test_create_notification_is_visible_in_list():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    create_notification(user_id, "health_reauth_required", "/connectors")

    notifications = list_notifications(user_id)
    assert len(notifications) == 1
    assert notifications[0].type == "health_reauth_required"
    assert notifications[0].action_href == "/connectors"
    assert notifications[0].status == "unread"


def test_create_notification_dedupes_unresolved_same_type():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    create_notification(user_id, "health_reauth_required", "/connectors")
    create_notification(user_id, "health_reauth_required", "/connectors")

    notifications = list_notifications(user_id)
    assert len(notifications) == 1


def test_resolve_notification_allows_a_fresh_one_of_the_same_type():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    create_notification(user_id, "health_reauth_required", "/connectors")

    resolve_notification(user_id, "health_reauth_required")
    assert list_notifications(user_id) == []

    create_notification(user_id, "health_reauth_required", "/connectors")
    notifications = list_notifications(user_id)
    assert len(notifications) == 1


def test_resolve_notification_is_a_noop_when_none_exists():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    resolve_notification(user_id, "health_reauth_required")  # must not raise
    assert list_notifications(user_id) == []


def test_mark_all_read_flips_unread_to_read_but_not_resolved():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    create_notification(user_id, "health_reauth_required", "/connectors")

    mark_all_read(user_id)

    notifications = list_notifications(user_id)
    assert len(notifications) == 1
    assert notifications[0].status == "read"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/data/test_db.py -k notification -v`
Expected: FAIL with `ImportError: cannot import name 'Notification'` (or `create_notification`).

- [ ] **Step 3: Add the table to `init_db()`**

In `data/db.py`, inside `init_db()`, after the existing `memories` table block (right before the trailing `ALTER TABLE` migration statements), add:

```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                action_href TEXT,
                status TEXT NOT NULL DEFAULT 'unread',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                resolved_at TIMESTAMPTZ
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications (user_id)"
        )
        # Partial unique index, not a plain UNIQUE constraint: a *resolved*
        # notification of a given (user, type) must not block a fresh one
        # from being created later if the same problem recurs.
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_unresolved_dedup
            ON notifications (user_id, type)
            WHERE status != 'resolved'
        """)
```

- [ ] **Step 4: Add the dataclass and CRUD functions**

In `data/db.py`, near the other dataclasses (alongside `Preferences`), add:

```python
@dataclass
class Notification:
    id: int
    user_id: str
    type: str
    action_href: str | None
    status: str
    created_at: datetime


def create_notification(
    user_id: str, type_: str, action_href: str | None = None
) -> None:
    # No message text here on purpose: display text is derived from `type`
    # client-side via next-intl (`notifications.types.<type>`), so it's
    # correctly localized instead of being frozen in whatever language the
    # backend happened to write at insert time.
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO notifications (user_id, type, action_href)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, type) WHERE status != 'resolved' DO NOTHING
            """,
            (user_id, type_, action_href),
        )
        conn.commit()


def resolve_notification(user_id: str, type_: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE notifications SET status = 'resolved', resolved_at = now()
            WHERE user_id = %s AND type = %s AND status != 'resolved'
            """,
            (user_id, type_),
        )
        conn.commit()


def list_notifications(user_id: str) -> list[Notification]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, type, action_href, status, created_at
            FROM notifications
            WHERE user_id = %s AND status != 'resolved'
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [
        Notification(
            id=row[0],
            user_id=str(row[1]),
            type=row[2],
            action_href=row[3],
            status=row[4],
            created_at=row[5],
        )
        for row in rows
    ]


def mark_all_read(user_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE notifications SET status = 'read' WHERE user_id = %s AND status = 'unread'",
            (user_id,),
        )
        conn.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/data/test_db.py -k notification -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add data/db.py tests/data/test_db.py
git commit -m "feat: add notifications table and CRUD functions"
```

---

### Task 2: Create a notification when a Health/Calendar refresh token dies

**Files:**
- Modify: `auth/auth.py`
- Test: `tests/auth/test_auth.py`

**Interfaces:**
- Consumes: `create_notification` from Task 1 — but **not called directly** inside `get_valid_access_token`'s transaction (see Step 3's comment for why); the notification insert and token delete are done as raw SQL on the same `conn` that already holds the row's `FOR UPDATE` lock, to avoid a self-block (a second pooled connection trying to touch the same locked row before the first transaction commits or rolls back).
- Produces: `get_valid_access_token` now deletes the dead token and writes a notification as a side effect of `invalid_grant`, then still re-raises — callers' existing exception handling (e.g. `dashboard.py`'s `except Exception: health_connected = False`, and the OTel span auto-marking itself `ERROR`) is unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/auth/test_auth.py` (add `create_notification`, `list_notifications`, `get_oauth_token` to the `from data.db import (...)` line):

```python
def test_invalid_grant_deletes_token_and_creates_notification():
    import time
    import requests

    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    save_oauth_token(
        user_id, "health", "expired-access", "dead-refresh", int(time.time()) - 10
    )

    response = requests.models.Response()
    response.status_code = 400
    response._content = b'{"error": "invalid_grant", "error_description": "Token has been expired or revoked."}'

    with patch("auth.auth.refresh_access_token") as mock_refresh:
        mock_refresh.side_effect = requests.HTTPError(response=response)
        with pytest.raises(requests.HTTPError):
            get_valid_access_token(user_id)

    assert get_oauth_token(user_id, "health") is None
    notifications = list_notifications(user_id)
    assert len(notifications) == 1
    assert notifications[0].type == "health_reauth_required"
    assert notifications[0].action_href == "/connectors"


def test_concurrent_refresh_of_same_dead_token_raises_valueerror_not_httperror():
    # Simulates the dashboard's parallel health+calendar fetch both hitting
    # a dead health token: the first call's transaction (mocked here by
    # calling get_valid_access_token once, which deletes the row) leaves the
    # second call with no row to SELECT ... FOR UPDATE. That's expected and
    # harmless (the second caller's `except Exception` still catches it) —
    # asserted here only so the error shape is documented, not silent.
    import time
    import requests

    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    save_oauth_token(
        user_id, "health", "expired-access", "dead-refresh", int(time.time()) - 10
    )

    response = requests.models.Response()
    response.status_code = 400
    response._content = b'{"error": "invalid_grant"}'

    with patch("auth.auth.refresh_access_token") as mock_refresh:
        mock_refresh.side_effect = requests.HTTPError(response=response)
        with pytest.raises(requests.HTTPError):
            get_valid_access_token(user_id)

    with pytest.raises(ValueError):
        get_valid_access_token(user_id)


def test_other_http_errors_do_not_delete_the_token_or_notify():
    import time
    import requests

    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    save_oauth_token(
        user_id, "health", "expired-access", "refresh-1", int(time.time()) - 10
    )

    response = requests.models.Response()
    response.status_code = 500
    response._content = b"internal error"

    with patch("auth.auth.refresh_access_token") as mock_refresh:
        mock_refresh.side_effect = requests.HTTPError(response=response)
        with pytest.raises(requests.HTTPError):
            get_valid_access_token(user_id)

    assert get_oauth_token(user_id, "health") is not None
    assert list_notifications(user_id) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/auth/test_auth.py -k "invalid_grant or other_http_errors or concurrent_refresh" -v`
Expected: FAIL — token still present / notification not created (current code only `logging.error`s and re-raises via `raise_for_status()`, nothing deletes or notifies).

- [ ] **Step 3: Update `get_valid_access_token` in `auth/auth.py`**

Replace the body of `get_valid_access_token` (currently lines 38-71) with:

```python
def get_valid_access_token(user_id: str, provider: str = "health") -> str:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT access_token, refresh_token, expires_at
            FROM oauth_tokens WHERE user_id = %s AND provider = %s
            FOR UPDATE
            """,
            (user_id, provider),
        ).fetchone()

        if row is None:
            raise ValueError(
                f"No {provider} token for user {user_id}; user must complete "
                f"/auth/{provider}/connect first"
            )

        access_token, refresh_token, expires_at = row

        if expires_at > time.time():
            return decrypt(access_token)

        try:
            response = refresh_access_token(decrypt(refresh_token))
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else ""
            if exc.response is not None and exc.response.status_code == 400 and "invalid_grant" in body:
                # Deliberately NOT calling data.db's delete_oauth_token /
                # create_notification here — those open their own pooled
                # connection, which would block trying to touch this same
                # row while this connection's FOR UPDATE lock is still held
                # (only released when this `with` block exits). Do both
                # writes on `conn` instead, in the same transaction.
                conn.execute(
                    "DELETE FROM oauth_tokens WHERE user_id = %s AND provider = %s",
                    (user_id, provider),
                )
                conn.execute(
                    """
                    INSERT INTO notifications (user_id, type, action_href)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, type) WHERE status != 'resolved' DO NOTHING
                    """,
                    (user_id, f"{provider}_reauth_required", "/connectors"),
                )
                conn.commit()
            raise

        new_expires_at = int(time.time()) + response["expires_in"]

        conn.execute(
            """
            UPDATE oauth_tokens SET access_token = %s, expires_at = %s
            WHERE user_id = %s AND provider = %s
            """,
            (encrypt(response["access_token"]), new_expires_at, user_id, provider),
        )
        conn.commit()
        return response["access_token"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/auth/test_auth.py -v`
Expected: PASS (all tests in the file, including the two pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add auth/auth.py tests/auth/test_auth.py
git commit -m "feat: delete dead OAuth token and notify user on invalid_grant"
```

---

### Task 3: Resolve the notification on successful reconnect

**Files:**
- Modify: `backend/routes/auth.py`
- Test: `tests/backend/routes/test_auth.py`

**Interfaces:**
- Consumes: `resolve_notification` from Task 1.

- [ ] **Step 1: Write the failing tests**

Add to `tests/backend/routes/test_auth.py` (add `create_notification`, `list_notifications` to the `from data.db import init_db` line, making it `from data.db import create_notification, init_db, list_notifications`):

```python
def test_health_callback_resolves_existing_reauth_notification(client):
    with patch("backend.services.auth_service.exchange_code_for_identity_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "email": "runner@example.com",
            "google_sub": "google-sub-123",
            "name": "Runner Example",
        }
        login_response = client.get("/auth/callback?code=fake-code", follow_redirects=False)
    session_cookie = login_response.cookies["session"]

    from data.db import find_or_create_user
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    create_notification(user_id, "health_reauth_required", "/connectors")

    with patch("backend.services.auth_service.exchange_code_for_health_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        }
        client.get(
            "/auth/health/callback?code=fake-code",
            cookies={"session": session_cookie},
            follow_redirects=False,
        )

    assert list_notifications(user_id) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/routes/test_auth.py -k resolves_existing_reauth -v`
Expected: FAIL — notification still present (nothing resolves it today).

- [ ] **Step 3: Wire `resolve_notification` into both callbacks**

In `backend/routes/auth.py`, add `resolve_notification` to the `from data.db import (...)` block. Then in `health_callback` (currently lines 81-104), insert the call right after `save_oauth_token(...)` and before the `return RedirectResponse(FRONTEND_URL)`:

```python
    save_oauth_token(
        user_id,
        "health",
        tokens["access_token"],
        tokens["refresh_token"],
        expires_at,
    )
    resolve_notification(user_id, "health_reauth_required")
    return RedirectResponse(FRONTEND_URL)
```

Do the identical thing in `calendar_callback` (currently lines 120-143), using `"calendar_reauth_required"`:

```python
    save_oauth_token(
        user_id,
        "calendar",
        tokens["access_token"],
        tokens["refresh_token"],
        expires_at,
    )
    resolve_notification(user_id, "calendar_reauth_required")
    return RedirectResponse(FRONTEND_URL)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backend/routes/test_auth.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add backend/routes/auth.py tests/backend/routes/test_auth.py
git commit -m "feat: resolve reauth notification on successful OAuth reconnect"
```

---

### Task 4: `GET /notifications` and `PATCH /notifications/read-all` routes

**Files:**
- Create: `backend/routes/notifications.py`
- Modify: `backend/agent.py`
- Test: `tests/backend/routes/test_notifications.py`

**Interfaces:**
- Consumes: `require_user` (`backend/dependencies.py`), `list_notifications`/`mark_all_read` (Task 1).
- Produces: `router` (FastAPI `APIRouter`, prefix `/notifications`) — importable as `from backend.routes.notifications import router as notifications_router`.

- [ ] **Step 1: Write the failing tests**

Create `tests/backend/routes/test_notifications.py`:

```python
import base64
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from data.db import create_notification, create_session, find_or_create_user, init_db


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


def _session_cookie_for_new_user(client) -> dict[str, str]:
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    return {"session": token}, user_id


def test_get_notifications_requires_auth(client):
    response = client.get("/notifications")
    assert response.status_code == 401


def test_get_notifications_returns_unresolved_notifications(client):
    cookies, user_id = _session_cookie_for_new_user(client)
    create_notification(user_id, "health_reauth_required", "/connectors")

    response = client.get("/notifications", cookies=cookies)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["type"] == "health_reauth_required"
    assert body[0]["status"] == "unread"


def test_read_all_marks_notifications_read(client):
    cookies, user_id = _session_cookie_for_new_user(client)
    create_notification(user_id, "health_reauth_required", "/connectors")

    response = client.patch("/notifications/read-all", cookies=cookies)
    assert response.status_code == 200

    listed = client.get("/notifications", cookies=cookies).json()
    assert listed[0]["status"] == "read"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/backend/routes/test_notifications.py -v`
Expected: FAIL with 404 (route doesn't exist yet).

- [ ] **Step 3: Create `backend/routes/notifications.py`**

```python
from fastapi import APIRouter, Depends

from backend.dependencies import require_user
from data.db import list_notifications, mark_all_read

router = APIRouter(prefix="/notifications")


@router.get("")
def get_notifications(user_id: str = Depends(require_user)):
    return list_notifications(user_id)


@router.patch("/read-all")
def read_all_notifications(user_id: str = Depends(require_user)):
    mark_all_read(user_id)
    return {"status": "ok"}
```

- [ ] **Step 4: Register the router in `backend/agent.py`**

Find the existing router imports/registrations (`backend/agent.py`, around the `include_router` calls for `auth_router`, `calendar_router`, `dashboard_router`, `preferences_router`, `profile_router`). Add:

```python
from backend.routes.notifications import router as notifications_router
```

And add `app.include_router(notifications_router)` alongside the others.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/backend/routes/test_notifications.py -v`
Expected: PASS

- [ ] **Step 6: Run the full backend test suite to check nothing regressed**

Run: `pytest tests -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add backend/routes/notifications.py backend/agent.py tests/backend/routes/test_notifications.py
git commit -m "feat: add GET /notifications and PATCH /notifications/read-all routes"
```

---

### Task 5: Frontend API client + polling hook

**Files:**
- Create: `frontend/lib/notifications-api.ts`
- Create: `frontend/hooks/use-notifications.ts`
- Test: `frontend/tests/use-notifications.test.tsx`

**Interfaces:**
- Produces: `Notification` type (no `message` field — matches the backend dataclass from Task 1; display text is derived from `type` via next-intl in Task 6, not sent over the wire as text), `getNotifications(): Promise<Notification[]>`, `markAllRead(): Promise<{status: string}>` (`lib/notifications-api.ts`).
- Produces: `useNotifications()` — returns `{ notifications: Notification[], unreadCount: number, markAllRead: () => void }` (`hooks/use-notifications.ts`).

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/use-notifications.test.tsx`:

```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { useNotifications } from "@/hooks/use-notifications";

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient();
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useNotifications", () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (options?.method === "PATCH") {
        return Promise.resolve({ ok: true, json: async () => ({ status: "ok" }) });
      }
      return Promise.resolve({
        ok: true,
        json: async () => [
          { id: 1, user_id: "u1", type: "health_reauth_required", action_href: "/connectors", status: "unread", created_at: "2026-08-31T00:00:00Z" },
          { id: 2, user_id: "u1", type: "calendar_reauth_required", action_href: "/connectors", status: "read", created_at: "2026-08-30T00:00:00Z" },
        ],
      });
    });
  });

  it("computes unreadCount from the fetched list", async () => {
    const { result } = renderHook(() => useNotifications(), { wrapper });

    await waitFor(() => expect(result.current.notifications).toHaveLength(2));

    expect(result.current.unreadCount).toBe(1);
  });

  it("markAllRead posts to /notifications/read-all", async () => {
    const { result } = renderHook(() => useNotifications(), { wrapper });
    await waitFor(() => expect(result.current.notifications).toHaveLength(2));

    result.current.markAllRead();

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/notifications/read-all"),
        expect.objectContaining({ method: "PATCH", credentials: "include" })
      );
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/use-notifications.test.tsx`
Expected: FAIL with a module-not-found error for `@/hooks/use-notifications`.

- [ ] **Step 3: Create `frontend/lib/notifications-api.ts`**

```typescript
import { apiFetch } from "@/lib/api";

export type Notification = {
  id: number;
  user_id: string;
  type: string;
  action_href: string | null;
  status: "unread" | "read";
  created_at: string;
};

export function getNotifications(): Promise<Notification[]> {
  return apiFetch<Notification[]>("/notifications");
}

export function markAllRead(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/notifications/read-all", { method: "PATCH" });
}
```

- [ ] **Step 4: Create `frontend/hooks/use-notifications.ts`**

```typescript
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getNotifications, markAllRead as markAllReadRequest } from "@/lib/notifications-api";

const POLL_INTERVAL_MS = 5 * 60 * 1000;

export function useNotifications() {
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: getNotifications,
    refetchInterval: POLL_INTERVAL_MS,
  });

  const mutation = useMutation({
    mutationFn: markAllReadRequest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  const notifications = data ?? [];
  const unreadCount = notifications.filter((n) => n.status === "unread").length;

  return { notifications, unreadCount, markAllRead: mutation.mutate };
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/use-notifications.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/notifications-api.ts frontend/hooks/use-notifications.ts frontend/tests/use-notifications.test.tsx
git commit -m "feat: add notifications API client and polling hook"
```

---

### Task 6: Bell icon + Sheet components

**Files:**
- Create: `frontend/components/notifications-bell.tsx`
- Create: `frontend/components/notifications-sheet.tsx`
- Modify: `frontend/messages/en.json`, `frontend/messages/de.json`
- Test: `frontend/tests/notifications-bell.test.tsx`, `frontend/tests/notifications-sheet.test.tsx`

**Interfaces:**
- Consumes: `useNotifications` (Task 5).
- Produces: `<NotificationsBell />` — self-contained (owns its own open/closed state, renders both the trigger icon and the `<NotificationsSheet>`), for `AppHeader` (Task 7) to drop in with no props.

- [ ] **Step 1: Add translation keys**

In `frontend/messages/en.json`, add a new top-level `notifications` key (alongside `connectors`, `profile`, etc.):

```json
"notifications": {
  "title": "Notifications",
  "empty": "You're all caught up.",
  "types": {
    "health_reauth_required": "Your Google Health connection expired. Please reconnect.",
    "calendar_reauth_required": "Your Google Calendar connection expired. Please reconnect."
  }
}
```

In `frontend/messages/de.json`, add the same keys with a German translation:

```json
"notifications": {
  "title": "Benachrichtigungen",
  "empty": "Du bist auf dem neuesten Stand.",
  "types": {
    "health_reauth_required": "Deine Google Health-Verbindung ist abgelaufen. Bitte neu verbinden.",
    "calendar_reauth_required": "Deine Google Calendar-Verbindung ist abgelaufen. Bitte neu verbinden."
  }
}
```

Every notification `type` written by the backend (Task 2: `health_reauth_required`, `calendar_reauth_required`) must have a matching key under `notifications.types` in both files — that's the contract between backend and frontend for this feature, since no display text ever crosses the wire.

- [ ] **Step 2: Write the failing tests**

Create `frontend/tests/notifications-sheet.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import { NotificationsSheet } from "@/components/notifications-sheet";
import messages from "@/messages/en.json";

function renderWithIntl(ui: React.ReactElement) {
  return render(<NextIntlClientProvider locale="en" messages={messages}>{ui}</NextIntlClientProvider>);
}

describe("NotificationsSheet", () => {
  it("shows the empty state when there are no notifications", () => {
    renderWithIntl(
      <NotificationsSheet open notifications={[]} onOpenChange={vi.fn()} onNotificationClick={vi.fn()} locale="en" />
    );
    expect(screen.getByText("You're all caught up.")).toBeInTheDocument();
  });

  it("translates each notification's type to display text", () => {
    renderWithIntl(
      <NotificationsSheet
        open
        notifications={[
          { id: 1, user_id: "u1", type: "health_reauth_required", action_href: "/connectors", status: "unread", created_at: "2026-08-31T00:00:00Z" },
        ]}
        onOpenChange={vi.fn()}
        onNotificationClick={vi.fn()}
        locale="en"
      />
    );
    expect(screen.getByText("Your Google Health connection expired. Please reconnect.")).toBeInTheDocument();
  });
});
```

Create `frontend/tests/notifications-bell.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { NotificationsBell } from "@/components/notifications-bell";
import messages from "@/messages/en.json";

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={messages}>
        {children}
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
}

describe("NotificationsBell", () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (options?.method === "PATCH") return Promise.resolve({ ok: true, json: async () => ({ status: "ok" }) });
      return Promise.resolve({
        ok: true,
        json: async () => [
          { id: 1, user_id: "u1", type: "health_reauth_required", action_href: "/connectors", status: "unread", created_at: "2026-08-31T00:00:00Z" },
        ],
      });
    });
  });

  it("shows the unread count badge", async () => {
    render(<NotificationsBell locale="en" />, { wrapper });
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });

  it("opens the sheet and marks all read on click", async () => {
    render(<NotificationsBell locale="en" />, { wrapper });
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/notifications/read-all"),
        expect.objectContaining({ method: "PATCH" })
      );
    });
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npx vitest run tests/notifications-bell.test.tsx tests/notifications-sheet.test.tsx`
Expected: FAIL with module-not-found errors.

- [ ] **Step 4: Create `frontend/components/notifications-sheet.tsx`**

```tsx
"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { Notification } from "@/lib/notifications-api";
import { cn } from "@/lib/utils";

export function NotificationsSheet({
  open,
  onOpenChange,
  notifications,
  onNotificationClick,
  locale,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  notifications: Notification[];
  onNotificationClick: () => void;
  locale: string;
}) {
  const t = useTranslations("notifications");

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-full lg:max-w-sm">
        <SheetHeader>
          <SheetTitle>{t("title")}</SheetTitle>
        </SheetHeader>
        <div className="flex flex-col gap-2 px-4">
          {notifications.length === 0 && (
            <div className="py-8 text-center text-sm text-muted">{t("empty")}</div>
          )}
          {notifications.map((notification) => {
            const content = (
              <div
                className={cn(
                  "rounded-xl border border-border p-3 text-sm",
                  notification.status === "unread" ? "bg-surface" : "bg-transparent text-muted"
                )}
              >
                {t(`types.${notification.type}`)}
              </div>
            );
            return notification.action_href ? (
              <Link
                key={notification.id}
                href={`/${locale}${notification.action_href}`}
                onClick={onNotificationClick}
              >
                {content}
              </Link>
            ) : (
              <div key={notification.id}>{content}</div>
            );
          })}
        </div>
      </SheetContent>
    </Sheet>
  );
}
```

- [ ] **Step 5: Create `frontend/components/notifications-bell.tsx`**

```tsx
"use client";

import { Bell } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { NotificationsSheet } from "@/components/notifications-sheet";
import { useNotifications } from "@/hooks/use-notifications";

export function NotificationsBell({ locale }: { locale: string }) {
  const t = useTranslations("notifications");
  const [open, setOpen] = useState(false);
  const { notifications, unreadCount, markAllRead } = useNotifications();

  return (
    <>
      <button
        type="button"
        aria-label={t("title")}
        onClick={() => {
          setOpen(true);
          markAllRead();
        }}
        className="relative flex h-9 w-9 items-center justify-center rounded-full text-primary hover:bg-surface"
      >
        <Bell size={20} strokeWidth={1.8} />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold text-white">
            {unreadCount}
          </span>
        )}
      </button>
      <NotificationsSheet
        open={open}
        onOpenChange={setOpen}
        notifications={notifications}
        onNotificationClick={() => setOpen(false)}
        locale={locale}
      />
    </>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npx vitest run tests/notifications-bell.test.tsx tests/notifications-sheet.test.tsx`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/components/notifications-bell.tsx frontend/components/notifications-sheet.tsx frontend/messages/en.json frontend/messages/de.json frontend/tests/notifications-bell.test.tsx frontend/tests/notifications-sheet.test.tsx
git commit -m "feat: add notifications bell and sheet components"
```

---

### Task 7: Shared header (bell + avatar) mounted on every screen

**Files:**
- Create: `frontend/components/app-header.tsx`
- Modify: `frontend/components/app-shell.tsx`
- Modify: `frontend/components/dashboard-screen.tsx`
- Test: `frontend/tests/app-shell.test.tsx`

**Interfaces:**
- Consumes: `NotificationsBell` (Task 6), `Avatar` (`components/avatar.tsx`), `useAuth` (`lib/auth-context`).
- Produces: `<AppHeader locale={locale} />`, mounted once by `AppShell`, so no other screen needs to render its own avatar-as-nav-link again.

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/app-shell.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/en/dashboard" }));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ user: { name: "Runner Example", email: "runner@example.com", avatar_url: null } }),
}));

import { AppShell } from "@/components/app-shell";
import messages from "@/messages/en.json";

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={messages}>
        {children}
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
}

describe("AppShell", () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
  });

  it("renders the notifications bell", () => {
    render(<AppShell locale="en">{<div>content</div>}</AppShell>, { wrapper });
    expect(screen.getByRole("button", { name: /notifications/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/app-shell.test.tsx`
Expected: FAIL — no notifications bell rendered by `AppShell` yet.

- [ ] **Step 3: Create `frontend/components/app-header.tsx`**

```tsx
"use client";

import Link from "next/link";

import { Avatar } from "@/components/avatar";
import { NotificationsBell } from "@/components/notifications-bell";
import { useAuth } from "@/lib/auth-context";

export function AppHeader({ locale }: { locale: string }) {
  const { user } = useAuth();

  return (
    <div className="flex items-center justify-end gap-2 p-3">
      <NotificationsBell locale={locale} />
      <Link href={`/${locale}/profile`}>
        <Avatar user={user ?? null} size="sm" />
      </Link>
    </div>
  );
}
```

- [ ] **Step 4: Mount it in `AppShell`**

In `frontend/components/app-shell.tsx`, add the import:

```tsx
import { AppHeader } from "@/components/app-header";
```

Replace the existing `<SidebarTrigger className="m-3 hidden self-start lg:flex" />` line with a row containing both the trigger and the new header, so the trigger stays left and the header's content sits right:

```tsx
        <div className="flex items-center justify-between">
          <SidebarTrigger className="m-3 hidden self-start lg:flex" />
          <AppHeader locale={locale} />
        </div>
```

- [ ] **Step 5: Remove the now-superseded avatar link from `dashboard-screen.tsx`**

In `frontend/components/dashboard-screen.tsx`, remove lines 111-113:

```tsx
          <Link href={`/${locale}/profile`} className="lg:hidden">
            <Avatar user={user} size="md" className="h-10 w-10 rounded-xl" />
          </Link>
```

If `Avatar` and `Link` become unused imports in that file as a result, remove those import lines too — check the rest of the file for other usages first (`Link` is very likely still used elsewhere in this file for run cards, etc. — only remove the import if `Avatar` has no other use).

- [ ] **Step 6: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/app-shell.test.tsx`
Expected: PASS

- [ ] **Step 7: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: all PASS (check `dashboard-screen`'s existing tests specifically — removing its avatar link must not break a test asserting on it; update that test if it references the removed link)

- [ ] **Step 8: Commit**

```bash
git add frontend/components/app-header.tsx frontend/components/app-shell.tsx frontend/components/dashboard-screen.tsx frontend/tests/app-shell.test.tsx
git commit -m "feat: mount shared header (notifications bell + avatar) on every screen"
```

---

## Self-Review Notes

- **Spec coverage:** every decision locked in during the grill-me interview is reflected: Postgres-only (no new DB), reactive-only detection (no scheduler), poll-only delivery (no SSE), DB-enforced dedup (partial unique index), three-state lifecycle, in/out scope boundary (only OAuth expiry implemented; synchronous action failures explicitly untouched), mark-all-read on open, click-to-navigate, shared header on all 4 screens/both breakpoints, 5-minute poll interval, single Sheet component (full-width on mobile, not a separate route).
- **Placeholder scan:** no TBD/TODO; every step has concrete code, exact file paths, and exact commands.
- **Type consistency:** `Notification` (backend dataclass, Task 1) and `Notification` (frontend type, Task 5) have matching fields (`id`, `user_id`, `type`, `action_href`, `status`, `created_at`) — no `message` field on either side, by design (see Global Constraints). `create_notification`/`resolve_notification`/`list_notifications`/`mark_all_read` signatures are identical everywhere they're referenced (Tasks 2, 3, 4). `useNotifications()`'s returned shape (`notifications`, `unreadCount`, `markAllRead`) matches what `NotificationsBell` (Task 6) and the `AppShell` test (Task 7) expect.
- **Known follow-up, not in this plan:** a second event type could reuse `create_notification`/`resolve_notification` directly (e.g. a future "weekly goal achieved" notification) — no changes needed to Tasks 1-4 to support that, only a new call site plus a matching `notifications.types.<type>` key in both `en.json`/`de.json`, consistent with the scope boundary this plan settled on.
- **Confirmed side effect (intentional, not a bug to "fix" later):** Task 2 deleting the dead token row on `invalid_grant` also resolves the pre-existing `health_connected`/`calendar_connected` mismatch documented in `CLAUDE.md`'s "Known bug found via tracing" section — `get_oauth_token` will correctly return `None` after expiry once this row is gone, so the Connectors page stops showing "Connected" for a dead integration. That section of `CLAUDE.md` should be updated (or removed) once this plan ships, since the bug it describes is fixed as a byproduct of Task 2, not by a separate patch.
- **Known edge case, accepted as-is (not fixed):** if two requests concurrently hit the same dead token (e.g. the dashboard's parallel health+calendar fetch, both needing the *health* token), the first request's transaction deletes the row and commits; the second request's `SELECT ... FOR UPDATE` then finds no row and raises `ValueError` (the "no token, must reconnect" path) instead of the `HTTPError` `invalid_grant` path. Both are already caught by existing broad `except Exception` handlers at every call site, so this doesn't crash or duplicate a notification — just a different, currently-unasserted exception shape on the "loser" of the race. Documented via `test_concurrent_refresh_of_same_dead_token_raises_valueerror_not_httperror` in Task 2 rather than special-cased in code, since a personal app's actual concurrency here is at most 2 (the dashboard's own parallel health/calendar fetch), not worth extra locking complexity.
