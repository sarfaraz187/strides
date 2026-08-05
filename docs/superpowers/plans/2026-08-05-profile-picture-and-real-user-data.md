# Profile Picture Upload + Real User Data Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `mockUser` (name/email/initials) with the real signed-in user everywhere it's shown, and add profile picture upload backed by Supabase Storage.

**Architecture:** Task 1 fixes an existing gap — `useAuth()` already returns real `name`/`email` from `/auth/me`, but `sidebar.tsx`, `profile-screen.tsx`, and `dashboard-screen.tsx` still read `mockUser` instead. That gets fixed first and independently, since the new `<Avatar>` component built in this plan needs a real user object to render initials from anyway. Tasks 2–6 then build the picture feature per the spec: a `users.avatar_path` column, a **private** Supabase Storage `avatars` bucket with server-signed URLs (avatars are personal data tied to a real identity — decided against public-bucket during execution, see the spec's revision), an upload route that validates and stores the file server-side, and a shared `<Avatar>` component wired into the three existing mock-avatar call sites.

> **Superseded during execution:** Tasks 2 and 3 below were originally written for a public bucket storing a plain `avatar_url`. Mid-implementation the bucket was switched to private with signed URLs — `data/db.py` stores `avatar_path` (bucket-relative, e.g. `user-123.jpg`) instead of a URL, `update_avatar_url` is `update_avatar_path`, and `backend/storage.py`'s `upload_avatar` returns a path while a new `create_signed_url(path, expires_in=3600)` mints the actual URL on demand (called from `/auth/me`, not stored). Both tasks were re-implemented this way and are already committed — the step-by-step content below is kept for historical record but Task 5 (not yet built) reflects the corrected interfaces.

**Tech Stack:** FastAPI + psycopg (backend), Next.js/React + TanStack Query (frontend), Supabase Storage REST API (no new Python dependency — plain `requests` calls, consistent with the rest of the codebase).

## Global Constraints

- Avatar upload: content-type must be `image/jpeg` or `image/png`; size must be ≤5MB — enforced server-side, never trust client-only checks.
- Storage: Supabase Storage bucket `avatars`, **private** — signed URLs (~1hr expiry) generated server-side on demand, never stored.
- If a user already has an `avatar_path`, the old file is deleted from the bucket before/with the new upload.
- Out of scope (per spec): cropping/resizing UI, private/signed URLs, multiple avatar sizes/thumbnails.
- New env vars required: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (needed to call the Storage REST API with write access — the pooler `DATABASE_URL` already in `.env` is Postgres-only, not the Storage API).

---

### Task 1: Wire real user name/email into sidebar, profile screen, dashboard

Fixes the immediate ask — currently `frontend/lib/mock-data.ts`'s `mockUser` (hardcoded `"Sam B."` / `"sam.b@gmail.com"`) is shown in three places instead of the real signed-in user, even though `useAuth()` (`frontend/lib/auth-context.tsx`) already fetches the real `{ email, name, created_at, health_connected }` from `/auth/me`.

**Files:**
- Modify: `frontend/components/sidebar.tsx`
- Modify: `frontend/components/profile-screen.tsx`
- Modify: `frontend/components/dashboard-screen.tsx`
- Test: `frontend/tests/sidebar.test.tsx`
- Test: `frontend/tests/profile-screen.test.tsx`
- Test: `frontend/tests/dashboard-screen.test.tsx`

**Interfaces:**
- Consumes: `useAuth()` from `frontend/lib/auth-context.tsx`, returns `{ user: { email: string; name: string | null; created_at: string; health_connected: boolean } | null; isLoading: boolean }`.
- Produces: an inline `initialsFromName(name: string | null): string` helper (first letters of first/last word, uppercased, `"?"` fallback when `name` is `null`/empty) — Task 4 replaces this ad-hoc helper with the shared `<Avatar>` component, so keep it a small local function for now, not exported.

- [ ] **Step 1: Write the failing test for sidebar**

Add to `frontend/tests/sidebar.test.tsx`:

```tsx
import { AuthContext } from "@/lib/auth-context";

function renderWithUser(name: string | null, ui: React.ReactElement) {
  return render(
    <AuthContext.Provider
      value={{ user: { email: "runner@example.com", name, created_at: "", health_connected: false }, isLoading: false }}
    >
      <NextIntlClientProvider locale="en" messages={en}>
        <SidebarProvider>{ui}</SidebarProvider>
      </NextIntlClientProvider>
    </AuthContext.Provider>
  );
}

describe("Sidebar user display", () => {
  it("shows the signed-in user's name and initials, not the mock user", () => {
    renderWithUser("Runner Example", <Sidebar active="dashboard" locale="en" />);

    expect(screen.getByText("Runner Example")).toBeInTheDocument();
    expect(screen.getByText("RE")).toBeInTheDocument();
    expect(screen.queryByText("Sam B.")).not.toBeInTheDocument();
  });
});
```

This requires exporting `AuthContext` (not just `useAuth`/`AuthProvider`) from `frontend/lib/auth-context.tsx` — add `export` to the `const AuthContext = createContext<AuthState>(...)` declaration (it's currently unexported).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/sidebar.test.tsx`
Expected: FAIL — `Sam B.` is currently rendered instead of `Runner Example`, and `AuthContext` isn't exported yet.

- [ ] **Step 3: Export `AuthContext` and wire `Sidebar` to `useAuth()`**

In `frontend/lib/auth-context.tsx`, change:

```ts
const AuthContext = createContext<AuthState>({ user: null, isLoading: true });
```

to:

```ts
export const AuthContext = createContext<AuthState>({ user: null, isLoading: true });
```

In `frontend/components/sidebar.tsx`, replace the `mockUser` import and both usages:

```tsx
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";
```

(remove `import { mockUser } from "@/lib/mock-data";`)

Inside the component, before the `return`:

```tsx
const { user } = useAuth();
const displayName = user?.name ?? user?.email ?? "";
const initials = displayName
  ? displayName
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((word) => word[0]?.toUpperCase())
      .join("")
  : "?";
```

Replace the footer's `{mockUser.initials}` with `{initials}` and `{mockUser.name}` with `{displayName}`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/sidebar.test.tsx`
Expected: PASS

- [ ] **Step 5: Write the failing test for profile screen**

Add to `frontend/tests/profile-screen.test.tsx`, reusing the `AuthContext.Provider` pattern from Step 1 (import `AuthContext` from `@/lib/auth-context`):

```tsx
it("shows the signed-in user's name, email, and join date instead of the mock user", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({ weekly_goal_km: 30, units: "km", notifications_enabled: true, language: "en" }),
      { status: 200 }
    )
  );

  render(
    <AuthContext.Provider
      value={{
        user: { email: "runner@example.com", name: "Runner Example", created_at: "2026-01-15T00:00:00Z", health_connected: false },
        isLoading: false,
      }}
    >
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <NextIntlClientProvider locale="en" messages={en}>
          <ProfileScreen locale="en" />
        </NextIntlClientProvider>
      </QueryClientProvider>
    </AuthContext.Provider>
  );

  await waitFor(() => expect(screen.getByText("Runner Example")).toBeInTheDocument());
  expect(screen.getByText("runner@example.com")).toBeInTheDocument();
  expect(screen.getByText("Jan 2026")).toBeInTheDocument();
});
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/profile-screen.test.tsx`
Expected: FAIL — still shows `Sam B.` / `sam.b@gmail.com` / the hardcoded `mockUser.memberSince` string `"Jan 2025"`.

- [ ] **Step 7: Wire `ProfileScreen` to `useAuth()`**

In `frontend/components/profile-screen.tsx`:

```tsx
import { useAuth } from "@/lib/auth-context";
```

(remove `import { mockUser } from "@/lib/mock-data";`)

Inside the component:

```tsx
const { user } = useAuth();
const displayName = user?.name ?? user?.email ?? "";
const initials = displayName
  ? displayName
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((word) => word[0]?.toUpperCase())
      .join("")
  : "?";
const memberSince = user?.created_at
  ? new Date(user.created_at).toLocaleDateString("en", { month: "short", year: "numeric" })
  : "";
```

Replace:
- `{mockUser.initials}` → `{initials}`
- `{mockUser.name}` → `{displayName}`
- `{mockUser.email}` → `{user?.email ?? ""}`
- `{mockUser.memberSince}` → `{memberSince}`

- [ ] **Step 8: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/profile-screen.test.tsx`
Expected: PASS

- [ ] **Step 9: Write the failing test for dashboard screen**

Add to `frontend/tests/dashboard-screen.test.tsx` (same `AuthContext.Provider` wrapping pattern):

```tsx
it("shows the signed-in user's initials on the mobile avatar link, not the mock user's", () => {
  render(
    <AuthContext.Provider
      value={{ user: { email: "runner@example.com", name: "Runner Example", created_at: "", health_connected: false }, isLoading: false }}
    >
      <NextIntlClientProvider locale="en" messages={en}>
        <DashboardScreen locale="en" />
      </NextIntlClientProvider>
    </AuthContext.Provider>
  );

  expect(screen.getByText("RE")).toBeInTheDocument();
  expect(screen.queryByText("SB")).not.toBeInTheDocument();
});
```

- [ ] **Step 10: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/dashboard-screen.test.tsx`
Expected: FAIL — shows `SB` (from `mockUser.initials`).

- [ ] **Step 11: Wire `DashboardScreen` to `useAuth()`**

In `frontend/components/dashboard-screen.tsx`, change the import:

```tsx
import { mockGoals, mockRecentRuns, mockWeekGoalPct, mockWeekStats } from "@/lib/mock-data";
import { useAuth } from "@/lib/auth-context";
```

(drop `mockUser` from the mock-data import list, keep the rest — dashboard stats/runs/goals stay mock per the existing project status, only the user identity changes here)

Inside the component:

```tsx
const { user } = useAuth();
const displayName = user?.name ?? user?.email ?? "";
const initials = displayName
  ? displayName
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((word) => word[0]?.toUpperCase())
      .join("")
  : "?";
```

Replace `{mockUser.initials}` with `{initials}`.

- [ ] **Step 12: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/dashboard-screen.test.tsx`
Expected: PASS

- [ ] **Step 13: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: PASS (no regressions in other component tests)

- [ ] **Step 14: Commit**

```bash
git add frontend/lib/auth-context.tsx frontend/components/sidebar.tsx frontend/components/profile-screen.tsx frontend/components/dashboard-screen.tsx frontend/tests/sidebar.test.tsx frontend/tests/profile-screen.test.tsx frontend/tests/dashboard-screen.test.tsx
git commit -m "fix: show real signed-in user instead of mock user in sidebar, profile, dashboard"
```

---

### Task 2: `users.avatar_url` column + `update_avatar_url` in `data/db.py`

**Files:**
- Modify: `data/db.py`
- Test: `tests/data/test_db.py` (create if it doesn't exist — check first with `find tests -iname "test_db.py"`)

**Interfaces:**
- Produces: `update_avatar_url(user_id: str, url: str | None) -> None`; `get_user(user_id)` return tuple grows from `(email, name, created_at)` to `(email, name, created_at, avatar_url)`.

- [ ] **Step 1: Write the failing test**

Create/append to `tests/data/test_db.py`:

```python
import base64
import os

import pytest

from data.db import (
    find_or_create_user,
    get_connection,
    get_user,
    init_db,
    update_avatar_url,
)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv(
        "TOKEN_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    init_db()
    yield
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE email = %s", ("avatar-test@example.com",))
        conn.commit()


def test_update_avatar_url_sets_and_clears_url():
    user_id = find_or_create_user("avatar-test@example.com", "avatar-sub-123", "Avatar Tester")

    update_avatar_url(user_id, "https://example.supabase.co/storage/v1/object/public/avatars/x.jpg")
    email, name, created_at, avatar_url = get_user(user_id)
    assert avatar_url == "https://example.supabase.co/storage/v1/object/public/avatars/x.jpg"

    update_avatar_url(user_id, None)
    _, _, _, avatar_url_after_clear = get_user(user_id)
    assert avatar_url_after_clear is None


def test_new_user_has_no_avatar_by_default():
    user_id = find_or_create_user("avatar-test@example.com", "avatar-sub-123", "Avatar Tester")
    _, _, _, avatar_url = get_user(user_id)
    assert avatar_url is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/data/test_db.py -v`
Expected: FAIL — `update_avatar_url` doesn't exist, and `get_user` returns a 3-tuple, not 4.

- [ ] **Step 3: Add the column, migration, and functions**

In `data/db.py`, inside `init_db()`, alongside the existing `ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT` line, add:

```python
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT")
```

Update `get_user`:

```python
def get_user(user_id: str) -> tuple[str, str, datetime, str | None] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT email, name, created_at, avatar_url FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    if row is None:
        return None
    email, name, created_at, avatar_url = row
    return email, name, created_at, avatar_url
```

Add a new function near it:

```python
def update_avatar_url(user_id: str, url: str | None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET avatar_url = %s WHERE id = %s", (url, user_id)
        )
        conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/data/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Update the `/auth/me` caller in `backend/routes/auth.py`**

`get_user` now returns a 4-tuple, so its one existing caller breaks. In `backend/routes/auth.py`, the `me` route currently does:

```python
    email, name, created_at = get_user(user_id)
```

Change to:

```python
    email, name, created_at, avatar_url = get_user(user_id)
```

and add `"avatar_url": avatar_url` to the returned dict:

```python
    return {
        "email": email,
        "name": name,
        "created_at": created_at,
        "avatar_url": avatar_url,
        "health_connected": is_connected,
    }
```

- [ ] **Step 6: Run the existing auth route tests to confirm nothing broke**

Run: `uv run pytest tests/backend/routes/test_auth.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add data/db.py backend/routes/auth.py tests/data/test_db.py
git commit -m "feat: add users.avatar_url column and update_avatar_url"
```

---

### Task 3: Supabase Storage client helper (`backend/storage.py`)

Isolates the raw Storage REST API calls (upload, delete) behind two functions, so the route in Task 5 doesn't hand-build HTTP requests inline. Uses `requests` directly against the Storage REST API rather than adding the `supabase-py` dependency — the project only needs upload/delete/public-URL, which is three plain HTTP calls.

**Files:**
- Create: `backend/storage.py`
- Test: `tests/backend/test_storage.py`

**Interfaces:**
- Consumes: env vars `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`.
- Produces: `upload_avatar(user_id: str, content: bytes, content_type: str) -> str` (returns the public URL); `delete_avatar(url: str) -> None` (no-op if the URL doesn't point into the `avatars` bucket).

- [ ] **Step 1: Write the failing test**

Create `tests/backend/test_storage.py`:

```python
from unittest.mock import Mock, patch

import pytest

from backend.storage import delete_avatar, upload_avatar


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")


def test_upload_avatar_puts_object_and_returns_public_url():
    with patch("backend.storage.requests.put") as mock_put:
        mock_put.return_value = Mock(status_code=200, raise_for_status=Mock())

        url = upload_avatar("user-123", b"fake-image-bytes", "image/jpeg")

    mock_put.assert_called_once()
    call_args = mock_put.call_args
    assert call_args.args[0] == (
        "https://project-ref.supabase.co/storage/v1/object/avatars/user-123.jpg"
    )
    assert call_args.kwargs["headers"]["Authorization"] == "Bearer service-role-key"
    assert call_args.kwargs["headers"]["Content-Type"] == "image/jpeg"
    assert call_args.kwargs["data"] == b"fake-image-bytes"
    assert url == (
        "https://project-ref.supabase.co/storage/v1/object/public/avatars/user-123.jpg"
    )


def test_delete_avatar_removes_object_by_url():
    with patch("backend.storage.requests.delete") as mock_delete:
        mock_delete.return_value = Mock(status_code=200, raise_for_status=Mock())

        delete_avatar(
            "https://project-ref.supabase.co/storage/v1/object/public/avatars/user-123.jpg"
        )

    mock_delete.assert_called_once_with(
        "https://project-ref.supabase.co/storage/v1/object/avatars/user-123.jpg",
        headers={"Authorization": "Bearer service-role-key"},
        timeout=10,
    )


def test_delete_avatar_noop_for_none():
    with patch("backend.storage.requests.delete") as mock_delete:
        delete_avatar(None)

    mock_delete.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/test_storage.py -v`
Expected: FAIL — `backend/storage.py` doesn't exist.

- [ ] **Step 3: Implement `backend/storage.py`**

```python
import os

import requests

_EXTENSION_BY_CONTENT_TYPE = {"image/jpeg": "jpg", "image/png": "png"}


def _bucket_object_url(path: str) -> str:
    base_url = os.environ["SUPABASE_URL"]
    return f"{base_url}/storage/v1/object/avatars/{path}"


def _bucket_public_url(path: str) -> str:
    base_url = os.environ["SUPABASE_URL"]
    return f"{base_url}/storage/v1/object/public/avatars/{path}"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ['SUPABASE_SERVICE_ROLE_KEY']}"}


def upload_avatar(user_id: str, content: bytes, content_type: str) -> str:
    extension = _EXTENSION_BY_CONTENT_TYPE[content_type]
    path = f"{user_id}.{extension}"

    response = requests.put(
        _bucket_object_url(path),
        headers={**_auth_headers(), "Content-Type": content_type, "x-upsert": "true"},
        data=content,
        timeout=10,
    )
    response.raise_for_status()
    return _bucket_public_url(path)


def delete_avatar(url: str | None) -> None:
    if url is None:
        return
    path = url.rsplit("/avatars/", maxsplit=1)[-1]
    response = requests.delete(
        _bucket_object_url(path), headers=_auth_headers(), timeout=10
    )
    response.raise_for_status()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backend/test_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/storage.py tests/backend/test_storage.py
git commit -m "feat: add Supabase Storage helper for avatar upload/delete"
```

---

### Task 4: Create the `avatars` bucket in Supabase (manual, no code)

Storage buckets aren't created via SQL migration — this is a one-time dashboard/MCP action, not a code task, so it has no test cycle.

- [ ] **Step 1: Create the bucket**

Use the `mcp__supabase__list_storage_buckets` tool first to confirm `avatars` doesn't already exist. If it doesn't, create it via the Supabase dashboard (Storage → New bucket → name `avatars`, **Public bucket** toggle **off** — private, per the spec's revision to signed URLs) since bucket creation isn't exposed as a direct MCP write tool — confirm with the user which project/org before creating anything.

- [ ] **Step 2: Add `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` to `.env`**

Get these from the Supabase dashboard → Project Settings → API. Add both to `/Users/mohammedsarfaraz/Desktop/strides/.env`. Do not commit `.env` (already gitignored — verify with `git check-ignore .env`).

- [ ] **Step 3: Verify bucket is reachable**

Run: `curl -I "$SUPABASE_URL/storage/v1/object/avatars/nonexistent.jpg" -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY"` (source `.env` first) — expect a `400`/`404` from Supabase (bucket exists, object doesn't), not a connection error.

---

### Task 5: `POST /profile/avatar` route

**Files:**
- Create: `backend/routes/profile.py`
- Modify: `backend/agent.py` (register the router)
- Test: `tests/backend/routes/test_profile.py`

**Interfaces:**
- Consumes: `require_user` from `backend/dependencies.py`; `get_user`, `update_avatar_path` from `data/db.py`; `upload_avatar`, `create_signed_url`, `delete_avatar` from `backend/storage.py`.
- Produces: `POST /profile/avatar` → `{"avatar_url": str}` (a freshly signed URL) on success; `400` for wrong content-type or >5MB; `401` without a valid session.

- [ ] **Step 1: Write the failing tests**

Create `tests/backend/routes/test_profile.py`:

```python
import base64
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from data.db import create_session, find_or_create_user, get_connection, get_user, init_db


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "TOKEN_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    init_db()
    yield
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE email = %s", ("avatar-route@example.com",))
        conn.commit()


@pytest.fixture
def client():
    from backend.agent import app

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    return TestClient(app)


def _session_cookie(client) -> tuple[dict[str, str], str]:
    user_id = find_or_create_user("avatar-route@example.com", "avatar-route-sub", "Avatar Route")
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    return {"session": token}, user_id


def test_upload_avatar_requires_auth(client):
    response = client.post(
        "/profile/avatar", files={"file": ("pic.jpg", b"fake-bytes", "image/jpeg")}
    )
    assert response.status_code == 401


def test_upload_avatar_rejects_wrong_content_type(client):
    cookies, _ = _session_cookie(client)
    response = client.post(
        "/profile/avatar",
        files={"file": ("pic.gif", b"fake-bytes", "image/gif")},
        cookies=cookies,
    )
    assert response.status_code == 400


def test_upload_avatar_rejects_oversized_file(client):
    cookies, _ = _session_cookie(client)
    oversized = b"x" * (5 * 1024 * 1024 + 1)
    response = client.post(
        "/profile/avatar",
        files={"file": ("pic.jpg", oversized, "image/jpeg")},
        cookies=cookies,
    )
    assert response.status_code == 400


def test_upload_avatar_stores_path_and_returns_signed_url(client):
    cookies, user_id = _session_cookie(client)

    with patch("backend.routes.profile.upload_avatar") as mock_upload, patch(
        "backend.routes.profile.create_signed_url"
    ) as mock_sign:
        mock_upload.return_value = f"{user_id}.jpg"
        mock_sign.return_value = "https://project-ref.supabase.co/storage/v1/object/sign/avatars/x.jpg?token=abc"
        response = client.post(
            "/profile/avatar",
            files={"file": ("pic.jpg", b"fake-bytes", "image/jpeg")},
            cookies=cookies,
        )

    assert response.status_code == 200
    assert response.json()["avatar_url"] == (
        "https://project-ref.supabase.co/storage/v1/object/sign/avatars/x.jpg?token=abc"
    )
    _, _, _, stored_path = get_user(user_id)
    assert stored_path == f"{user_id}.jpg"


def test_upload_avatar_deletes_prior_file_when_replacing(client):
    cookies, user_id = _session_cookie(client)

    with patch("backend.routes.profile.upload_avatar") as mock_upload, patch(
        "backend.routes.profile.create_signed_url"
    ), patch("backend.routes.profile.delete_avatar") as mock_delete:
        mock_upload.return_value = "first.jpg"
        client.post(
            "/profile/avatar",
            files={"file": ("pic.jpg", b"first-bytes", "image/jpeg")},
            cookies=cookies,
        )

        mock_upload.return_value = "second.jpg"
        client.post(
            "/profile/avatar",
            files={"file": ("pic.jpg", b"second-bytes", "image/jpeg")},
            cookies=cookies,
        )

    mock_delete.assert_called_once_with("first.jpg")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/routes/test_profile.py -v`
Expected: FAIL — `/profile/avatar` doesn't exist (404s).

- [ ] **Step 3: Implement `backend/routes/profile.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile

from backend.dependencies import require_user
from backend.storage import create_signed_url, delete_avatar, upload_avatar
from data.db import get_user, update_avatar_path

router = APIRouter(prefix="/profile")

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
_MAX_SIZE_BYTES = 5 * 1024 * 1024


@router.post("/avatar")
async def upload_avatar_route(
    file: UploadFile, user_id: str = Depends(require_user)
):
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Must be a JPEG or PNG image")

    content = await file.read()
    if len(content) > _MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File must be 5MB or smaller")

    _, _, _, existing_avatar_path = get_user(user_id)

    new_path = upload_avatar(user_id, content, file.content_type)

    if existing_avatar_path is not None:
        delete_avatar(existing_avatar_path)

    update_avatar_path(user_id, new_path)
    return {"avatar_url": create_signed_url(new_path)}
```

- [ ] **Step 4: Register the router**

In `backend/agent.py`, alongside the other route imports:

```python
from backend.routes.profile import router as profile_router
```

and alongside the other `app.include_router(...)` calls:

```python
app.include_router(profile_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/backend/routes/test_profile.py -v`
Expected: PASS

- [ ] **Step 6: Run the full backend test suite**

Run: `uv run pytest -v`
Expected: PASS (no regressions elsewhere)

- [ ] **Step 7: Commit**

```bash
git add backend/routes/profile.py backend/agent.py tests/backend/routes/test_profile.py
git commit -m "feat: add POST /profile/avatar upload route"
```

---

### Task 6: Frontend `<Avatar>` component + wiring

Replaces the three inline initials circles (now real-data-driven from Task 1) with a shared component that also renders an uploaded picture, and adds the upload UI to the profile screen.

**Files:**
- Create: `frontend/components/avatar.tsx`
- Test: `frontend/tests/avatar.test.tsx`
- Modify: `frontend/lib/auth-context.tsx` (add `avatar_url` to `User` type)
- Modify: `frontend/components/sidebar.tsx`
- Modify: `frontend/components/profile-screen.tsx`
- Modify: `frontend/components/dashboard-screen.tsx`

**Interfaces:**
- Consumes: `useAuth()`'s `user.avatar_url: string | null` (new field), `user.name: string | null`.
- Produces: `<Avatar user={{ name, avatar_url }} size="sm" | "md" | "lg" className? />` — a reusable component; `initialsFromName(name: string | null): string`, exported so Task 1's three ad-hoc copies collapse into one.

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/avatar.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Avatar, initialsFromName } from "@/components/avatar";

describe("initialsFromName", () => {
  it("takes the first letter of the first two words, uppercased", () => {
    expect(initialsFromName("Runner Example")).toBe("RE");
  });

  it("falls back to a single letter for a one-word name", () => {
    expect(initialsFromName("Runner")).toBe("R");
  });

  it("falls back to '?' for null", () => {
    expect(initialsFromName(null)).toBe("?");
  });
});

describe("Avatar", () => {
  it("renders an img when avatar_url is present", () => {
    render(<Avatar user={{ name: "Runner Example", avatar_url: "https://example.com/pic.jpg" }} size="md" />);

    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", "https://example.com/pic.jpg");
  });

  it("falls back to initials when avatar_url is null", () => {
    render(<Avatar user={{ name: "Runner Example", avatar_url: null }} size="md" />);

    expect(screen.getByText("RE")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/avatar.test.tsx`
Expected: FAIL — `frontend/components/avatar.tsx` doesn't exist.

- [ ] **Step 3: Implement `frontend/components/avatar.tsx`**

```tsx
import { cn } from "@/lib/utils";

export function initialsFromName(name: string | null): string {
  if (!name) return "?";
  const words = name.trim().split(/\s+/).slice(0, 2);
  return words.map((word) => word[0]?.toUpperCase()).join("") || "?";
}

const SIZE_CLASSES = {
  sm: "h-8 w-8 text-xs",
  md: "h-9 w-9 text-[13px]",
  lg: "h-14 w-14 text-lg lg:h-16 lg:w-16 lg:text-xl",
};

export function Avatar({
  user,
  size,
  className,
}: {
  user: { name: string | null; avatar_url: string | null };
  size: "sm" | "md" | "lg";
  className?: string;
}) {
  if (user.avatar_url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={user.avatar_url}
        alt={user.name ?? "Profile picture"}
        className={cn("flex-none rounded-full object-cover", SIZE_CLASSES[size], className)}
      />
    );
  }

  return (
    <div
      className={cn(
        "flex flex-none items-center justify-center rounded-full bg-avatar-bg font-semibold text-primary",
        SIZE_CLASSES[size],
        className
      )}
    >
      {initialsFromName(user.name)}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/avatar.test.tsx`
Expected: PASS

- [ ] **Step 5: Add `avatar_url` to the `User` type**

In `frontend/lib/auth-context.tsx`:

```ts
type User = { email: string; health_connected: boolean; created_at: string; name: string | null; avatar_url: string | null };
```

Update `MOCK_USER` to include `avatar_url: null`.

- [ ] **Step 6: Replace the three ad-hoc initials blocks with `<Avatar>`**

In `frontend/components/sidebar.tsx`, replace the local `initials`/`displayName` computation and the hardcoded div from Task 1 Step 3 with:

```tsx
import { Avatar } from "@/components/avatar";
```

```tsx
const { user } = useAuth();
```

and in the footer JSX, replace the `<div className="flex h-8 w-8 ...">{initials}</div>` with:

```tsx
<Avatar user={{ name: user?.name ?? null, avatar_url: user?.avatar_url ?? null }} size="sm" />
```

keeping the adjacent `{!collapsed && <div>...{displayName}</div>}` block, now reading `user?.name ?? user?.email ?? ""`.

In `frontend/components/dashboard-screen.tsx`, same pattern — replace the mobile avatar link's div with `<Avatar user={{ name: user?.name ?? null, avatar_url: user?.avatar_url ?? null }} size="sm" />` wrapped in the existing `<Link>`.

In `frontend/components/profile-screen.tsx`, replace the header's initials div with `<Avatar user={{ name: user?.name ?? null, avatar_url: user?.avatar_url ?? null }} size="lg" />`.

- [ ] **Step 7: Run the three component test suites to confirm no regressions**

Run: `cd frontend && npx vitest run tests/sidebar.test.tsx tests/dashboard-screen.test.tsx tests/profile-screen.test.tsx`
Expected: PASS

- [ ] **Step 8: Add upload UI to the profile screen**

In `frontend/components/profile-screen.tsx`, add a `useMutation` for the upload and a hidden file input triggered by clicking the avatar:

```tsx
import { useRef } from "react";
```

```tsx
const fileInputRef = useRef<HTMLInputElement>(null);
const [uploadError, setUploadError] = useState<string | null>(null);

const uploadAvatar = useMutation({
  mutationFn: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    const response = await fetch(`${baseUrl}/profile/avatar`, {
      method: "POST",
      credentials: "include",
      body: formData,
    });
    if (!response.ok) throw new Error("Upload failed");
    return (await response.json()) as { avatar_url: string };
  },
  onSuccess: ({ avatar_url }) => {
    setUploadError(null);
    queryClient.setQueryData(["auth", "me"], (previous: typeof user) =>
      previous ? { ...previous, avatar_url } : previous
    );
  },
  onError: () => setUploadError(t("avatarUploadFailed")),
});

function onAvatarFileChosen(event: React.ChangeEvent<HTMLInputElement>) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  if (!["image/jpeg", "image/png"].includes(file.type)) {
    setUploadError(t("avatarInvalidType"));
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    setUploadError(t("avatarTooLarge"));
    return;
  }
  setUploadError(null);
  uploadAvatar.mutate(file);
}
```

`apiFetch` (`frontend/lib/api.ts`) always sets `Content-Type: application/json`, which breaks multipart uploads — that's why this mutation calls `fetch` directly instead, matching the note in the design spec that multipart needs its own handling.

Replace the avatar `<Avatar ... size="lg" />` from Step 6 with a clickable wrapper:

```tsx
<button
  type="button"
  onClick={() => fileInputRef.current?.click()}
  disabled={uploadAvatar.isPending}
  className="relative flex-none rounded-full disabled:cursor-not-allowed"
  aria-label={t("changeAvatar")}
>
  <Avatar user={{ name: user?.name ?? null, avatar_url: user?.avatar_url ?? null }} size="lg" />
  {uploadAvatar.isPending && (
    <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
    </div>
  )}
</button>
<input
  ref={fileInputRef}
  type="file"
  accept="image/jpeg,image/png"
  className="hidden"
  onChange={onAvatarFileChosen}
/>
```

Add `{uploadError && <div className="mb-4 rounded-xl bg-danger/10 p-3 text-[13px] text-danger">{uploadError}</div>}` near the existing preferences-error block.

Add the three new i18n keys to `frontend/messages/en.json` and `frontend/messages/de.json` under the `profile` namespace: `avatarUploadFailed`, `avatarInvalidType`, `avatarTooLarge`, `changeAvatar` (check the existing file's exact nesting with `grep -n '"profile"' frontend/messages/en.json` before editing, to match structure).

- [ ] **Step 9: Write a failing test for file-picker validation**

Add to `frontend/tests/profile-screen.test.tsx`:

```tsx
it("rejects an oversized file before making any network call", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({ weekly_goal_km: 30, units: "km", notifications_enabled: true, language: "en" }),
      { status: 200 }
    )
  );

  renderWithProviders(<ProfileScreen locale="en" />);
  await waitFor(() => expect(screen.getByText("English")).toBeInTheDocument());

  const fetchCallsBefore = (global.fetch as ReturnType<typeof vi.spyOn>).mock.calls.length;
  const input = screen.getByLabelText(en.profile.changeAvatar, { selector: "input" }) as HTMLInputElement;
  const oversizedFile = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.jpg", { type: "image/jpeg" });

  await userEvent.upload(input, oversizedFile);

  expect(screen.getByText(en.profile.avatarTooLarge)).toBeInTheDocument();
  expect((global.fetch as ReturnType<typeof vi.spyOn>).mock.calls.length).toBe(fetchCallsBefore);
});
```

This needs `import userEvent from "@testing-library/user-event";` added to the test file's imports (check `frontend/package.json` for `@testing-library/user-event` — if absent, this is a new dev dependency; flag it to the user before adding rather than installing silently).

- [ ] **Step 10: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/profile-screen.test.tsx`
Expected: FAIL — upload UI doesn't exist yet, or `aria-label` isn't reachable via `getByLabelText` on the hidden input (the `aria-label` in Step 8 is on the button, not the input — fix by moving `aria-label={t("changeAvatar")}` onto the `<input>` element itself, keeping the button unlabeled since it wraps a labeled input+avatar).

- [ ] **Step 11: Adjust and confirm pass**

Move the `aria-label` from the `<button>` onto the `<input>` in Step 8's JSX. Re-run:

Run: `cd frontend && npx vitest run tests/profile-screen.test.tsx`
Expected: PASS

- [ ] **Step 12: Run the full frontend suite**

Run: `cd frontend && npx vitest run`
Expected: PASS

- [ ] **Step 13: Commit**

```bash
git add frontend/components/avatar.tsx frontend/tests/avatar.test.tsx frontend/lib/auth-context.tsx frontend/components/sidebar.tsx frontend/components/dashboard-screen.tsx frontend/components/profile-screen.tsx frontend/tests/profile-screen.test.tsx frontend/messages/en.json frontend/messages/de.json
git commit -m "feat: add avatar upload UI and shared Avatar component"
```

---

## Notes for the executor

- Task 4 is the only non-code, non-automatable step — it requires a human decision (which Supabase project/org) and dashboard access. Don't attempt to script around it.
- Tasks 2, 3, 5 (backend) can run before or interleaved with Task 1 (frontend) — they don't share files. Task 6 depends on Task 1 (needs `useAuth()` already wired into the three components) and Task 2 (needs `avatar_url` returned by `/auth/me`) and Task 5 (needs the upload route live) being done first.
- Step 9 of Task 6 introduces a new dev dependency (`@testing-library/user-event`) only if it isn't already present — per the project's CLAUDE.md, confirm with the user before running `npm install` for it.
