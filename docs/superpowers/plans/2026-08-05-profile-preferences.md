# Profile Preferences Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the profile screen's weekly goal, units, notifications, and a new language setting per-user in Postgres, replacing local `useState`, and add a language dropdown that also switches the app's locale.

**Architecture:** A `preferences` Postgres table (already exists, missing a `language` column) is read/written through two new FastAPI routes (`GET`/`PUT /preferences`), session-cookie authenticated via the existing `require_user` dependency. The profile screen calls these through React Query (`useQuery` for load, `useMutation` for writes), with per-control save timing (instant vs. debounced).

**Tech Stack:** FastAPI, psycopg (Postgres), pytest; Next.js/React, `@tanstack/react-query`, `next-intl`, Vitest + Testing Library, shadcn/ui (`select` — not yet installed).

## Global Constraints

- `language` column: `TEXT NOT NULL DEFAULT 'en'`, no DB-level CHECK constraint — validated app-side only (spec: Data model).
- No preferences row exists until the user changes something for the first time — lazy creation via upsert, not eager at signup (spec: Data model).
- Units/notifications/language mutations fire immediately on change; the weekly-goal stepper debounces ~500ms after the last click (spec: Frontend).
- No optimistic UI updates — controls reflect only server-confirmed values (spec: Frontend / Error handling).
- Language control is a shadcn `Select` dropdown, not a toggle, so adding a third language later is a one-line change (per user direction, overriding the toggle originally in the spec text — spec's Frontend section language description is superseded by this).
- Out of scope: locale auto-detection via middleware, languages beyond en/de, any change to the `goals` table (spec: Out of scope).

---

## Task 1: `language` column + `Preferences` dataclass with lazy defaults

**Files:**
- Modify: `data/db.py` (the `init_db()` `preferences` table DDL around line 45; the existing `upsert_preferences`/`get_preferences` functions around lines 177–213)
- Test: `tests/data/test_db.py` (existing preferences tests around lines 56–68, 224–248)

**Interfaces:**
- Produces: `@dataclass class Preferences: weekly_goal_km: float; units: str; notifications_enabled: bool; language: str`
- Produces: `get_preferences(user_id: str) -> Preferences` — always returns a `Preferences` (defaults when no row exists), never `None`.
- Produces: `upsert_preferences(user_id: str, weekly_goal_km: float | None = None, units: str | None = None, notifications_enabled: bool | None = None, language: str | None = None) -> Preferences` — partial update; omitted (`None`) args keep the existing row's value, or the default if no row exists yet.

- [x] **Step 1: Update the failing/changing tests in `tests/data/test_db.py`**

Replace the existing preferences tests (the `test_init_db_creates_preferences_table`, `test_upsert_preferences_then_get_preferences_round_trips`, `test_upsert_preferences_updates_existing_row`, and `test_get_preferences_returns_none_when_absent` tests) with:

```python
def test_init_db_creates_preferences_table():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'preferences' AND table_schema = 'public'"
        ).fetchall()
    columns = {row[0] for row in result}
    assert columns == {
        "user_id",
        "weekly_goal_km",
        "units",
        "notifications_enabled",
        "language",
    }


def test_get_preferences_returns_defaults_when_no_row_exists():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    prefs = get_preferences(user_id)

    assert prefs == Preferences(
        weekly_goal_km=30, units="km", notifications_enabled=True, language="en"
    )


def test_upsert_preferences_creates_row_with_defaults_for_omitted_fields():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    prefs = upsert_preferences(user_id, units="mi")

    assert prefs == Preferences(
        weekly_goal_km=30, units="mi", notifications_enabled=True, language="en"
    )


def test_upsert_preferences_then_get_preferences_round_trips():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    upsert_preferences(
        user_id, weekly_goal_km=30, units="km", notifications_enabled=True, language="en"
    )
    prefs = get_preferences(user_id)

    assert prefs == Preferences(
        weekly_goal_km=30, units="km", notifications_enabled=True, language="en"
    )


def test_upsert_preferences_partial_update_only_touches_provided_fields():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    upsert_preferences(
        user_id, weekly_goal_km=30, units="km", notifications_enabled=True, language="en"
    )
    upsert_preferences(user_id, language="de")

    prefs = get_preferences(user_id)

    assert prefs == Preferences(
        weekly_goal_km=30, units="km", notifications_enabled=True, language="de"
    )
```

Add `Preferences` to the imports from `data.db` at the top of the test file, and remove `get_preferences`/`upsert_preferences` if the import list needs adjusting (they stay, just add `Preferences`).

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/data/test_db.py -k preferences -v`
Expected: FAIL — `Preferences` doesn't exist / column mismatch / `get_preferences` returns `None` instead of defaults.

- [x] **Step 3: Add the `language` column to the `init_db()` DDL**

In `data/db.py`, find the `CREATE TABLE IF NOT EXISTS preferences` block inside `init_db()` and add the column:

```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                weekly_goal_km NUMERIC NOT NULL,
                units TEXT NOT NULL,
                notifications_enabled BOOLEAN NOT NULL,
                language TEXT NOT NULL DEFAULT 'en'
            )
        """)
```

Since the table may already exist from prior runs without the column, also add directly below the other `ALTER TABLE` migration line (`conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT")`):

```python
        conn.execute(
            "ALTER TABLE preferences ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en'"
        )
```

- [x] **Step 4: Replace `upsert_preferences`/`get_preferences` with the dataclass-based, partial-update versions**

Add near the top of `data/db.py`, alongside the other `@dataclass` (`Goal`):

```python
@dataclass
class Preferences:
    weekly_goal_km: float
    units: str
    notifications_enabled: bool
    language: str


_DEFAULT_PREFERENCES = Preferences(
    weekly_goal_km=30, units="km", notifications_enabled=True, language="en"
)
```

Replace the existing `upsert_preferences` and `get_preferences` functions with:

```python
def upsert_preferences(
    user_id: str,
    weekly_goal_km: float | None = None,
    units: str | None = None,
    notifications_enabled: bool | None = None,
    language: str | None = None,
) -> Preferences:
    current = get_preferences(user_id)
    weekly_goal_km = current.weekly_goal_km if weekly_goal_km is None else weekly_goal_km
    units = current.units if units is None else units
    notifications_enabled = (
        current.notifications_enabled if notifications_enabled is None else notifications_enabled
    )
    language = current.language if language is None else language

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO preferences (user_id, weekly_goal_km, units, notifications_enabled, language)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                weekly_goal_km = excluded.weekly_goal_km,
                units = excluded.units,
                notifications_enabled = excluded.notifications_enabled,
                language = excluded.language
            """,
            (user_id, weekly_goal_km, units, notifications_enabled, language),
        )
        conn.commit()
    return Preferences(
        weekly_goal_km=float(weekly_goal_km),
        units=units,
        notifications_enabled=notifications_enabled,
        language=language,
    )


def get_preferences(user_id: str) -> Preferences:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT weekly_goal_km, units, notifications_enabled, language
            FROM preferences WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return _DEFAULT_PREFERENCES
    weekly_goal_km, units, notifications_enabled, language = row
    return Preferences(
        weekly_goal_km=float(weekly_goal_km),
        units=units,
        notifications_enabled=notifications_enabled,
        language=language,
    )
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/data/test_db.py -k preferences -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add data/db.py tests/data/test_db.py
git commit -m "feat: add language column and partial-update preferences upsert"
```

---

## Task 2: `GET`/`PUT /preferences` routes

**Files:**
- Create: `backend/routes/preferences.py`
- Modify: `backend/agent.py` (router registration, alongside the other three `app.include_router` calls)
- Test: `tests/backend/routes/test_preferences.py`

**Interfaces:**
- Consumes: `data.db.get_preferences(user_id: str) -> Preferences`, `data.db.upsert_preferences(user_id, weekly_goal_km=None, units=None, notifications_enabled=None, language=None) -> Preferences` (Task 1), `backend.dependencies.require_user` (existing — `Cookie`-based, returns `user_id: str`, raises 401 via `HTTPException`).
- Produces: `router = APIRouter(prefix="/preferences")` with `GET /preferences` and `PUT /preferences`, both returning JSON `{weekly_goal_km, units, notifications_enabled, language}`.

- [x] **Step 1: Write the failing route tests**

Create `tests/backend/routes/test_preferences.py`:

```python
import base64
import os
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from data.db import find_or_create_user, init_db


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
    from datetime import datetime, timedelta, timezone

    from data.db import create_session

    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))
    return {"session": token}


def test_get_preferences_requires_auth(client):
    response = client.get("/preferences")
    assert response.status_code == 401


def test_get_preferences_returns_defaults_for_new_user(client):
    cookies = _session_cookie_for_new_user(client)

    response = client.get("/preferences", cookies=cookies)

    assert response.status_code == 200
    assert response.json() == {
        "weekly_goal_km": 30,
        "units": "km",
        "notifications_enabled": True,
        "language": "en",
    }


def test_put_preferences_requires_auth(client):
    response = client.put("/preferences", json={"language": "de"})
    assert response.status_code == 401


def test_put_preferences_partial_update_round_trips_through_get(client):
    cookies = _session_cookie_for_new_user(client)

    put_response = client.put("/preferences", json={"language": "de"}, cookies=cookies)
    assert put_response.status_code == 200
    assert put_response.json()["language"] == "de"
    assert put_response.json()["units"] == "km"

    get_response = client.get("/preferences", cookies=cookies)
    assert get_response.json()["language"] == "de"
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/backend/routes/test_preferences.py -v`
Expected: FAIL with 404 (route doesn't exist)

- [x] **Step 3: Write the route**

Create `backend/routes/preferences.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.dependencies import require_user
from data.db import get_preferences, upsert_preferences

router = APIRouter(prefix="/preferences")


class PreferencesUpdate(BaseModel):
    weekly_goal_km: float | None = None
    units: str | None = None
    notifications_enabled: bool | None = None
    language: str | None = None


@router.get("")
def read_preferences(user_id: str = Depends(require_user)):
    return get_preferences(user_id)


@router.put("")
def write_preferences(body: PreferencesUpdate, user_id: str = Depends(require_user)):
    return upsert_preferences(
        user_id,
        weekly_goal_km=body.weekly_goal_km,
        units=body.units,
        notifications_enabled=body.notifications_enabled,
        language=body.language,
    )
```

`Preferences` is a plain `@dataclass`, which FastAPI/Pydantic serializes to JSON automatically when returned directly from a route.

Register the router in `backend/agent.py`, next to the other route imports/includes:

```python
from backend.routes.preferences import router as preferences_router
```

```python
app.include_router(preferences_router)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/backend/routes/test_preferences.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add backend/routes/preferences.py backend/agent.py tests/backend/routes/test_preferences.py
git commit -m "feat: add GET/PUT /preferences routes"
```

---

## Task 3: Frontend API client + `usePreferences` hook

**Files:**
- Modify: `frontend/lib/api.ts` (add typed helpers) — or create `frontend/lib/preferences-api.ts` if keeping `api.ts` to just the generic `apiFetch` wrapper (follow existing pattern: `api.ts` currently only has the generic fetch wrapper, so create a new file to match the one-file-one-responsibility pattern used by `hooks/use-health-connector.ts`)
- Create: `frontend/hooks/use-preferences.ts`
- Test: `frontend/tests/use-preferences.test.tsx`

**Interfaces:**
- Consumes: `apiFetch<T>(path, options) -> Promise<T>` (existing, `frontend/lib/api.ts`).
- Produces: `type Preferences = { weekly_goal_km: number; units: "km" | "mi"; notifications_enabled: boolean; language: "en" | "de" }`.
- Produces: `DEFAULT_PREFERENCES: Preferences` (exported — Task 5 does not need it directly, but it documents the fallback contract).
- Produces: `usePreferences()` returning `{ preferences: Preferences | undefined, isLoading: boolean, updateNow: (partial: Partial<Preferences>) => void, updateDebounced: (partial: Partial<Preferences>) => void, error: Error | null }`. `preferences` is `undefined` only while `isLoading` is `true`; once loading finishes, it is always a `Preferences` value — either the server response or `DEFAULT_PREFERENCES` if the `GET` failed (spec: Error handling — "GET /preferences failure: fall back to the same client-side defaults the backend uses").

- [x] **Step 1: Write the failing test**

Create `frontend/tests/use-preferences.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { usePreferences } from "@/hooks/use-preferences";

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("usePreferences", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("loads preferences via GET on mount", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          weekly_goal_km: 30,
          units: "km",
          notifications_enabled: true,
          language: "en",
        }),
        { status: 200 }
      )
    );

    const { result } = renderHook(() => usePreferences(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.preferences?.language).toBe("en");
  });

  it("falls back to default preferences when the GET fails", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response("Server error", { status: 500 }));

    const { result } = renderHook(() => usePreferences(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.preferences).toEqual({
      weekly_goal_km: 30,
      units: "km",
      notifications_enabled: true,
      language: "en",
    });
  });

  it("updateNow fires a PUT immediately", async () => {
    const mockFetch = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            weekly_goal_km: 30,
            units: "km",
            notifications_enabled: true,
            language: "de",
          }),
          { status: 200 }
        )
      );

    const { result } = renderHook(() => usePreferences(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.updateNow({ language: "de" });
    });

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/preferences"),
        expect.objectContaining({ method: "PUT" })
      )
    );
  });

  it("updateDebounced collapses rapid calls into a single PUT after 500ms", async () => {
    vi.useFakeTimers();
    const mockFetch = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            weekly_goal_km: 40,
            units: "km",
            notifications_enabled: true,
            language: "en",
          }),
          { status: 200 }
        )
      );

    const { result } = renderHook(() => usePreferences(), { wrapper });

    act(() => {
      result.current.updateDebounced({ weekly_goal_km: 35 });
      result.current.updateDebounced({ weekly_goal_km: 40 });
      result.current.updateDebounced({ weekly_goal_km: 45 });
    });

    const putCallsBefore = mockFetch.mock.calls.filter(
      (call) => (call[1] as RequestInit | undefined)?.method === "PUT"
    );
    expect(putCallsBefore).toHaveLength(0);

    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    const putCallsAfter = mockFetch.mock.calls.filter(
      (call) => (call[1] as RequestInit | undefined)?.method === "PUT"
    );
    expect(putCallsAfter).toHaveLength(1);
    expect(JSON.parse((putCallsAfter[0][1] as RequestInit).body as string)).toEqual({
      weekly_goal_km: 45,
    });
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run tests/use-preferences.test.tsx`
Expected: FAIL — module `@/hooks/use-preferences` not found.

- [x] **Step 3: Add typed preferences API calls**

Create `frontend/lib/preferences-api.ts`:

```ts
import { apiFetch } from "@/lib/api";

export type Preferences = {
  weekly_goal_km: number;
  units: "km" | "mi";
  notifications_enabled: boolean;
  language: "en" | "de";
};

export function getPreferences(): Promise<Preferences> {
  return apiFetch<Preferences>("/preferences");
}

export function updatePreferences(partial: Partial<Preferences>): Promise<Preferences> {
  return apiFetch<Preferences>("/preferences", {
    method: "PUT",
    body: JSON.stringify(partial),
  });
}
```

- [x] **Step 4: Write `usePreferences`**

Create `frontend/hooks/use-preferences.ts`:

```ts
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";

import { getPreferences, Preferences, updatePreferences } from "@/lib/preferences-api";

const GOAL_DEBOUNCE_MS = 500;

export const DEFAULT_PREFERENCES: Preferences = {
  weekly_goal_km: 30,
  units: "km",
  notifications_enabled: true,
  language: "en",
};

export function usePreferences() {
  const queryClient = useQueryClient();
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["preferences"],
    queryFn: getPreferences,
  });

  // GET failure: fall back to the same defaults the backend uses for a
  // user with no row yet, so the UI still renders sensible values.
  const preferences = data ?? (isLoading ? undefined : isError ? DEFAULT_PREFERENCES : undefined);

  const mutation = useMutation({
    mutationFn: updatePreferences,
    onSuccess: (updated) => {
      queryClient.setQueryData(["preferences"], updated);
    },
  });

  function updateNow(partial: Partial<Preferences>) {
    mutation.mutate(partial);
  }

  function updateDebounced(partial: Partial<Preferences>) {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      mutation.mutate(partial);
    }, GOAL_DEBOUNCE_MS);
  }

  return {
    preferences,
    isLoading,
    updateNow,
    updateDebounced,
    error: mutation.error,
  };
}
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run tests/use-preferences.test.tsx`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add frontend/lib/preferences-api.ts frontend/hooks/use-preferences.ts frontend/tests/use-preferences.test.tsx
git commit -m "feat: add usePreferences hook with instant and debounced updates"
```

---

## Task 4: Install shadcn `select` and add language i18n keys

**Files:**
- Create: `frontend/components/ui/select.tsx` (generated by shadcn CLI)
- Modify: `frontend/package.json` (new dependency, added by the CLI)
- Modify: `frontend/messages/en.json`, `frontend/messages/de.json`

**Interfaces:**
- Produces: `Select`, `SelectTrigger`, `SelectValue`, `SelectContent`, `SelectItem` exports from `@/components/ui/select` (shadcn's standard API — used as-is in Task 5).
- Produces: i18n keys `profile.language`, `profile.english`, `profile.german`.

- [x] **Step 1: Install the shadcn `select` component**

Run: `cd frontend && npx shadcn@latest add select`

This adds `@radix-ui/react-select` to `package.json`/`package-lock.json` and generates `frontend/components/ui/select.tsx`. Confirm the generated file exports `Select`, `SelectTrigger`, `SelectValue`, `SelectContent`, `SelectItem` (shadcn's default select component API).

- [x] **Step 2: Add the language keys to `frontend/messages/en.json`**

In the `profile` object, add after `"units"`/`"kilometers"`/`"miles"`:

```json
    "language": "Language",
    "english": "English",
    "german": "German",
```

- [x] **Step 3: Add the language keys to `frontend/messages/de.json`**

In the `profile` object, add:

```json
    "language": "Sprache",
    "english": "Englisch",
    "german": "Deutsch",
```

- [x] **Step 4: Run the existing i18n test to confirm both locale files stay structurally in sync**

Run: `cd frontend && npx vitest run tests/i18n.test.tsx`
Expected: PASS (this test already asserts `en.json`/`de.json` have matching key sets — no new test needed here, it's a regression guard for this change)

- [x] **Step 5: Commit**

```bash
git add frontend/components/ui/select.tsx frontend/package.json frontend/package-lock.json frontend/messages/en.json frontend/messages/de.json
git commit -m "feat: install shadcn select and add language i18n keys"
```

---

## Task 5: Wire profile screen to real preferences + language dropdown

**Files:**
- Modify: `frontend/components/profile-screen.tsx` (entire local-state block, lines 21–23 and the goal/units/notifications `Card`s, lines 48–101)
- Test: `frontend/tests/profile-screen.test.tsx` (new)

**Interfaces:**
- Consumes: `usePreferences()` (Task 3), `Select`/`SelectTrigger`/`SelectValue`/`SelectContent`/`SelectItem` (Task 4), `useRouter`/`usePathname` from `next/navigation` (existing Next.js APIs, `usePathname` already used elsewhere in the codebase per `frontend/components/app-shell.tsx`).
- Produces: no new exports — this is a leaf component.

**Design note — goal stepper feedback (see spec's "Error handling" section, stepper exception):** every other control (units, notifications, language) is strictly non-optimistic — it displays `preferences.<field>` from `usePreferences()` directly and only changes once the server confirms. The goal stepper is a scoped exception: because its save is debounced ~500ms, waiting for server confirmation before showing any change both feels unresponsive and breaks click accumulation (each click needs to add to the *pending* total, not the last-confirmed one). It keeps its own `useState<number | null>` for the pending value, seeded to `null` (meaning "show `preferences.weekly_goal_km`"), and reset to `null` whenever `preferences.weekly_goal_km` changes (i.e., once the debounced save is confirmed) so it doesn't drift from server state after other tabs/devices change it.

- [x] **Step 1: Write the failing test**

Create `frontend/tests/profile-screen.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import { ProfileScreen } from "@/components/profile-screen";
import en from "../messages/en.json";

const pushMock = vi.fn();
const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  usePathname: () => "/en/profile",
}));

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={en}>
        {ui}
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
}

describe("ProfileScreen", () => {
  it("loads preferences and shows the current language", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          weekly_goal_km: 30,
          units: "km",
          notifications_enabled: true,
          language: "en",
        }),
        { status: 200 }
      )
    );

    renderWithProviders(<ProfileScreen locale="en" />);

    await waitFor(() => expect(screen.getByText("English")).toBeInTheDocument());
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run tests/profile-screen.test.tsx`
Expected: FAIL — `ProfileScreen` still uses hardcoded local state, no preferences fetch happens, so `English` text/select isn't rendered from fetched data (or the render throws because `usePreferences`/`Select` don't exist yet if this task runs before Tasks 3–4 land).

- [x] **Step 3: Rewrite `profile-screen.tsx`**

Replace the full contents of `frontend/components/profile-screen.tsx`:

```tsx
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { usePreferences } from "@/hooks/use-preferences";
import { apiFetch } from "@/lib/api";
import { mockUser } from "@/lib/mock-data";
import type { Preferences } from "@/lib/preferences-api";

const GOAL_STEP_KM = 5;
const MIN_GOAL_KM = 5;
const KM_TO_MI = 0.621;

export function ProfileScreen({ locale }: { locale: string }) {
  const t = useTranslations("profile");
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { preferences, isLoading, updateNow, updateDebounced, error } = usePreferences();

  // Pending, not-yet-confirmed goal value shown while the debounced save is
  // in flight. `null` means "show the server-confirmed value". Reset to
  // `null` whenever the confirmed value changes underneath us (debounced
  // save landed, or another tab/device changed it).
  const [pendingGoalKm, setPendingGoalKm] = useState<number | null>(null);
  useEffect(() => {
    setPendingGoalKm(null);
  }, [preferences?.weekly_goal_km]);

  const logOut = useMutation({
    mutationFn: () => apiFetch("/auth/logout", { method: "POST" }),
    onSuccess: () => {
      queryClient.setQueryData(["auth", "me"], null);
      router.push(`/${locale}`);
    },
  });

  if (isLoading || !preferences) {
    return (
      <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:mx-auto lg:w-full lg:max-w-[560px] lg:px-0 lg:py-9">
        <div className="text-sm text-muted">{t("weeklyGoal")}</div>
      </div>
    );
  }

  const displayedGoalKm = pendingGoalKm ?? preferences.weekly_goal_km;
  const weeklyGoalText =
    preferences.units === "km"
      ? `${displayedGoalKm} km`
      : `${Math.round(displayedGoalKm * KM_TO_MI)} mi`;

  function adjustGoal(deltaKm: number) {
    const nextGoal = Math.max(MIN_GOAL_KM, displayedGoalKm + deltaKm);
    setPendingGoalKm(nextGoal);
    updateDebounced({ weekly_goal_km: nextGoal });
  }

  function onLanguageChange(newLanguage: Preferences["language"]) {
    updateNow({ language: newLanguage });
    const segments = pathname.split("/");
    segments[1] = newLanguage;
    router.replace(segments.join("/"));
  }

  return (
    <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:mx-auto lg:w-full lg:max-w-[560px] lg:px-0 lg:py-9">
      <div className="mb-6 flex items-center gap-3.5 lg:mb-7 lg:gap-4">
        <div className="flex h-14 w-14 flex-none items-center justify-center rounded-full bg-avatar-bg text-lg font-semibold text-primary lg:h-16 lg:w-16 lg:text-xl">
          {mockUser.initials}
        </div>
        <div>
          <div className="text-lg font-bold text-primary lg:text-[22px]">{mockUser.name}</div>
          <div className="text-[13px] text-muted lg:text-sm">{mockUser.email}</div>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-xl bg-danger/10 p-3 text-[13px] text-danger">
          {t("saveFailed")}
        </div>
      )}

      <div className="flex flex-col gap-2.5 lg:gap-3">
        <Card className="flex-row items-center justify-between rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("weeklyGoal")}</div>
          <div className="flex items-center gap-3 lg:gap-3.5">
            <button
              onClick={() => adjustGoal(-GOAL_STEP_KM)}
              aria-label={t("decreaseGoal")}
              className="h-7 w-7 cursor-pointer rounded-full border border-border bg-surface text-[15px] font-semibold text-primary lg:h-8 lg:w-8 lg:text-base"
            >
              –
            </button>
            <div className="min-w-[52px] text-center font-mono text-sm font-semibold text-primary lg:min-w-[60px] lg:text-[15px]">
              {weeklyGoalText}
            </div>
            <button
              onClick={() => adjustGoal(GOAL_STEP_KM)}
              aria-label={t("increaseGoal")}
              className="h-7 w-7 cursor-pointer rounded-full border border-border bg-surface text-[15px] font-semibold text-primary lg:h-8 lg:w-8 lg:text-base"
            >
              +
            </button>
          </div>
        </Card>

        <Card className="flex-row items-center justify-between rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("units")}</div>
          <button
            onClick={() => updateNow({ units: preferences.units === "km" ? "mi" : "km" })}
            className="h-[30px] cursor-pointer rounded-full border border-border bg-surface px-3.5 text-xs font-semibold text-primary lg:h-[34px] lg:px-4 lg:text-[13px]"
          >
            {preferences.units === "km" ? t("kilometers") : t("miles")}
          </button>
        </Card>

        <Card className="flex-row items-center justify-between rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("notifications")}</div>
          <button
            onClick={() =>
              updateNow({ notifications_enabled: !preferences.notifications_enabled })
            }
            aria-pressed={preferences.notifications_enabled}
            aria-label={t("notifications")}
            className="relative h-[27px] w-[46px] flex-none cursor-pointer rounded-full"
            style={{
              background: preferences.notifications_enabled
                ? "var(--color-accent)"
                : "var(--color-border)",
            }}
          >
            <span
              className="absolute top-[3px] h-[21px] w-[21px] rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.2)] transition-[left]"
              style={{ left: preferences.notifications_enabled ? "22px" : "3px" }}
            />
          </button>
        </Card>

        <Card className="flex-row items-center justify-between rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("language")}</div>
          <Select value={preferences.language} onValueChange={onLanguageChange}>
            <SelectTrigger className="h-[30px] w-auto rounded-full border border-border bg-surface px-3.5 text-xs font-semibold text-primary lg:h-[34px] lg:px-4 lg:text-[13px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="en">{t("english")}</SelectItem>
              <SelectItem value="de">{t("german")}</SelectItem>
            </SelectContent>
          </Select>
        </Card>

        <Card className="flex-row items-center justify-between rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("memberSince")}</div>
          <div className="text-[13px] text-muted-light">{mockUser.memberSince}</div>
        </Card>
      </div>

      <button
        onClick={() => logOut.mutate()}
        disabled={logOut.isPending}
        className="mt-6 h-[50px] w-full cursor-pointer rounded-2xl border border-danger-border bg-danger-bg text-sm font-semibold text-danger disabled:cursor-not-allowed disabled:opacity-60 lg:mt-7 lg:h-[52px]"
      >
        {t("logOut")}
      </button>
    </div>
  );
}
```

Note: the goal stepper's `pendingGoalKm` local state is what makes clicking +/- feel responsive (otherwise there'd be no visible change until the debounced request lands ~500ms+network-latency later). It lives in `useState`, not the shared React Query cache, so it can't leak into other consumers of `["preferences"]` — once the debounced mutation succeeds, `usePreferences`'s `onSuccess` updates the cache, the `useEffect` above notices `preferences.weekly_goal_km` changed, and clears `pendingGoalKm` back to `null` so the display reverts to reading the server-confirmed value. Units/notifications/language don't need this since their mutations are instant and non-debounced — they read `preferences.<field>` directly, per spec.

Add one more i18n key to both message files, in the `profile` object: `"saveFailed": "Couldn't save your change. Try again."` (`en.json`) / `"saveFailed": "Änderung konnte nicht gespeichert werden. Bitte erneut versuchen."` (`de.json`).

- [x] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run tests/profile-screen.test.tsx tests/i18n.test.tsx`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add frontend/components/profile-screen.tsx frontend/tests/profile-screen.test.tsx frontend/messages/en.json frontend/messages/de.json
git commit -m "feat: wire profile screen to persisted preferences and add language dropdown"
```

---

## Task 6: Manual verification

**Files:** none (manual QA pass)

- [x] **Step 1: Run the full backend test suite**

Run: `pytest -v`
Expected: all tests PASS, including the new `tests/backend/routes/test_preferences.py` and updated `tests/data/test_db.py`.

- [x] **Step 2: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: all tests PASS.

- [ ] **Step 3: Manual smoke test in the browser**

Start the backend (`uvicorn backend.agent:app --reload` or the project's usual dev command) and the frontend (`cd frontend && npm run dev`). Log in, go to `/en/profile`:
- Click +/- on weekly goal rapidly several times; confirm the network tab shows exactly one `PUT /preferences` request ~500ms after the last click, with the final value.
- Toggle units; confirm an immediate `PUT /preferences` request.
- Toggle notifications; confirm an immediate `PUT /preferences` request.
- Change the language dropdown to German; confirm the URL changes to `/de/profile`, the page re-renders in German, and a `PUT /preferences` request fires.
- Refresh the page; confirm all four settings persisted (goal, units, notifications, language) rather than resetting to defaults.

- [ ] **Step 4: Report results to the user**

No commit for this task — it's verification only.
