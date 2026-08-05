# Health Connector Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mocked "Connect"/"Disconnect" behavior on the connectors screen with the real Google Health OAuth flow that already exists on the backend, and remove the unrelated mocked Google Calendar entry.

**Architecture:** `/auth/me` gains a `health_connected` boolean derived from `get_oauth_token`. The frontend's "Connect" button becomes a real link to the backend's redirect-based OAuth endpoint (not a fetch call — it's a full-page navigation to Google's consent screen). "Disconnect" becomes a real `POST`. Both flows re-derive UI state from `/auth/me` via React Query invalidation instead of local component state.

**Tech Stack:** FastAPI (backend/routes/auth.py), Postgres via data/db.py, pytest + TestClient, Next.js/React Query (frontend/lib/auth-context.tsx, frontend/lib/api.ts), Vitest.

## Global Constraints

- Google Calendar connector card is removed entirely (no backend exists for it) — not stubbed as "coming soon."
- `"pending"` status is dropped for the Health connector — status is binary: `connected` / `disconnected`.
- Session cookie auth only — no new auth mechanism; `credentials: "include"` on every `fetch`.
- Consent-denied / token-exchange failures on `/auth/health/callback` must redirect back to the frontend (never a raw 500) so the UI can show an error instead of a blank crash page.

---

## Task 1: Backend — `/auth/me` reports `health_connected` ✅ DONE (not yet committed)

**Files:**
- Modify: `backend/routes/auth.py:94-98` (the `me()` handler)
- Test: `tests/backend/routes/test_auth.py`

**Interfaces:**
- Consumes: `data.db.get_oauth_token(user_id: str, provider: str) -> tuple[str, str, int] | None` (existing, `data/db.py:156`) — returns `None` when no row exists, whether that's "never connected" or "disconnected then deleted" (confirmed by reading `delete_oauth_token`, which does a hard `DELETE`, not a status flag — so `None` always means "not connected," no extra case to handle).
- Produces: `GET /auth/me` response shape `{ email: str, name: str | None, created_at: str, health_connected: bool }` — Task 3 (frontend) depends on this exact field name and type.

- [x] **Step 1: Write the failing tests**

Add to `tests/backend/routes/test_auth.py` (uses the existing `_login` helper already defined in that file):

```python
def test_me_reports_health_connected_false_when_not_connected(client):
    session_cookie = _login(client)

    response = client.get("/auth/me", cookies={"session": session_cookie})

    assert response.status_code == 200
    assert response.json()["health_connected"] is False


def test_me_reports_health_connected_true_after_health_callback(client):
    session_cookie = _login(client)
    with patch("backend.services.auth_service.exchange_code_for_health_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "access_token": "health-access",
            "refresh_token": "health-refresh",
            "expires_in": 3600,
        }
        client.get(
            "/auth/health/callback?code=fake-code",
            cookies={"session": session_cookie},
            follow_redirects=False,
        )

    response = client.get("/auth/me", cookies={"session": session_cookie})

    assert response.status_code == 200
    assert response.json()["health_connected"] is True


def test_me_reports_health_connected_false_after_disconnect(client):
    session_cookie = _login(client)
    with patch("backend.services.auth_service.exchange_code_for_health_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "access_token": "health-access",
            "refresh_token": "health-refresh",
            "expires_in": 3600,
        }
        client.get(
            "/auth/health/callback?code=fake-code",
            cookies={"session": session_cookie},
            follow_redirects=False,
        )
    client.post("/auth/health/disconnect", cookies={"session": session_cookie})

    response = client.get("/auth/me", cookies={"session": session_cookie})

    assert response.status_code == 200
    assert response.json()["health_connected"] is False
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/backend/routes/test_auth.py -k health_connected -v`
Expected: FAIL — `KeyError: 'health_connected'` (field doesn't exist yet).

- [x] **Step 3: Implement**

In `backend/routes/auth.py`, add `get_oauth_token` to the existing import block (`from data.db import (...)`, currently at lines 9-17) and update `me()`:

```python
@router.get("/me")
def me(session: str | None = Cookie(default=None)):
    user_id = _require_user_id(session)
    email, name, created_at = get_user(user_id)
    health_connected = get_oauth_token(user_id, "health") is not None
    return {
        "email": email,
        "name": name,
        "created_at": created_at,
        "health_connected": health_connected,
    }
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/routes/test_auth.py -v`
Expected: all PASS, including the pre-existing `test_me_returns_email_and_name_for_valid_session`.

- [ ] **Step 5: Commit** (deferred — will commit later)

```bash
git add backend/routes/auth.py tests/backend/routes/test_auth.py
git commit -m "feat: report health_connected status from /auth/me"
```

---

## Task 2: Backend — redirect to frontend with an error param on Health OAuth failure ✅ DONE (not yet committed)

**Files:**
- Modify: `backend/routes/auth.py:75-84` (the `health_callback` handler)
- Test: `tests/backend/routes/test_auth.py`

**Interfaces:**
- Consumes: `auth_service.exchange_code_for_health_tokens(code: str) -> dict` (existing) — this raises `requests.HTTPError` via `response.raise_for_status()` on token-exchange failure (see `backend/services/auth_service.py`, `exchange_code_for_health_tokens`).
- Produces: on failure, redirects to `f"{FRONTEND_URL}?health_connect_error=1"` instead of letting the exception propagate to a 500. Task 4 (frontend) depends on this exact query param name.

- [x] **Step 1: Write the failing test**

Add to `tests/backend/routes/test_auth.py`:

```python
import requests


def test_health_callback_redirects_with_error_param_on_exchange_failure(client):
    session_cookie = _login(client)

    with patch("backend.services.auth_service.exchange_code_for_health_tokens") as mock_exchange:
        mock_exchange.side_effect = requests.HTTPError("token exchange failed")
        response = client.get(
            "/auth/health/callback?code=bad-code",
            cookies={"session": session_cookie},
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert "health_connect_error=1" in response.headers["location"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/routes/test_auth.py -k error_on_exchange_failure -v`
Expected: FAIL — the unhandled `HTTPError` propagates and `TestClient` raises it (or the test sees a 500), not a 307.

Also added a second test, `test_health_callback_redirects_with_error_param_on_consent_denied`, covering the consent-denied case (Google sends `?error=access_denied`, no `code`) — this was a gap identified during plan review, not in the original plan snippet. Confirmed it 422s before the fix (since `code` was a required param).

- [x] **Step 3: Implement**

```python
@router.get("/health/callback")
def health_callback(code: str, session: str | None = Cookie(default=None)):
    user_id = _require_user_id(session)
    try:
        tokens = auth_service.exchange_code_for_health_tokens(code)
    except requests.HTTPError:
        return RedirectResponse(f"{FRONTEND_URL}?health_connect_error=1")

    expires_at = int(time.time()) + tokens["expires_in"]
    save_oauth_token(
        user_id, "health", tokens["access_token"], tokens["refresh_token"], expires_at
    )
    return RedirectResponse(FRONTEND_URL)
```

Add `import requests` to the top of `backend/routes/auth.py`.

Actual implementation also made `code` optional and added an `error: str | None = None` param, redirecting immediately when `error` is present — covers the consent-denied case, not just exchange failure.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/backend/routes/test_auth.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit** (deferred — will commit later)

```bash
git add backend/routes/auth.py tests/backend/routes/test_auth.py
git commit -m "fix: redirect with error param instead of 500 on Health token exchange failure"
```

---

## Task 3: Frontend — extend `User` type and derive Health status from `/auth/me` ✅ DONE (not yet committed)

**Files:**
- Modify: `frontend/lib/auth-context.tsx`
- Test: `frontend/tests/auth-context.test.tsx`

**Interfaces:**
- Consumes: `GET /auth/me` now returning `{ email, name, created_at, health_connected }` (Task 1).
- Produces: `useAuth(): { user: User | null, isLoading: boolean }` where `User = { email: string, name: string | null, health_connected: boolean }`. Task 5 (ConnectorsScreen) depends on `user.health_connected`.

**Naming decision (deviates from original plan draft):** no snake_case→camelCase mapping layer. `User` uses the exact field names/casing the API returns (`health_connected`, not `healthConnected`) — no separate `MeResponse` type. Decided 2026-08-05: keep one casing convention end-to-end (whatever the API sends) rather than translating at the boundary; only newly-introduced local variables/state get camelCase.

- [x] **Step 1: Write the failing test**

Read the existing test file first to match its conventions:

Run: `cat frontend/tests/auth-context.test.tsx`

Then add a test asserting `health_connected` is surfaced on the `user` object when `/auth/me` returns `health_connected: true`. Follow the existing file's pattern for mocking `apiFetch`/`fetch` (match whatever mocking approach the current tests already use — inspect the file output from the `cat` above before writing this, since the exact mock shape must match the existing setup).

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run auth-context -t health_connected`
Expected: FAIL — `user.health_connected` is `undefined`.

- [x] **Step 3: Implement**

```typescript
type User = { email: string; name: string | null; created_at: string; health_connected: boolean };
type AuthState = { user: User | null; isLoading: boolean };

const AuthContext = createContext<AuthState>({ user: null, isLoading: true });

const MOCK_AUTH = process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
const MOCK_USER: User = { email: "dev@example.com", name: "Dev User", created_at: "", health_connected: false };

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useQuery<User | null>({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      try {
        return await apiFetch<User>("/auth/me");
      } catch {
        return null;
      }
    },
    enabled: !MOCK_AUTH,
  });

  const value = MOCK_AUTH ? { user: MOCK_USER, isLoading: false } : { user: data ?? null, isLoading };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
```

Also remove the stale "Dev-only bypass... /auth/me isn't implemented" comment above `MOCK_AUTH` — it no longer applies now that `/auth/me` is real; replace with a one-line note that `NEXT_PUBLIC_MOCK_AUTH=true` skips the real auth check for local UI work without a backend running.

- [x] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run auth-context`
Expected: all PASS.

- [ ] **Step 5: Commit** (deferred — will commit later)

```bash
git add frontend/lib/auth-context.tsx frontend/tests/auth-context.test.tsx
git commit -m "feat: surface health_connected on the auth context User type"
```

---

## Task 4: Frontend — add `useHealthDisconnect` mutation and a query-invalidation-on-mount effect for the OAuth return ✅ DONE (not yet committed)

**Files:**
- Create: `frontend/hooks/use-health-connector.ts`
- Test: `frontend/tests/use-health-connector.test.tsx`

**Interfaces:**
- Consumes: `apiFetch` from `frontend/lib/api.ts` (existing); `useQueryClient` from `@tanstack/react-query` (already a project dependency, used by `auth-context.tsx`'s `useQuery`).
- Produces:
  - `HEALTH_CONNECT_URL = ${NEXT_PUBLIC_API_URL}/auth/health/connect` (exported constant) — Task 5 uses this directly as an `<a href>`, no fetch involved.
  - `useHealthDisconnect(): { disconnect: () => Promise<void>, isPending: boolean, error: Error | null }` — calls `POST /auth/health/disconnect`, invalidates the `["auth", "me"]` query on success.
  - `useHealthConnectErrorFromUrl(): boolean` — reads `?health_connect_error=1` from `window.location.search` on mount, returns `true` if present (for Task 5's error banner). Does not need to clear the param from the URL — out of scope for this task.

- [x] **Step 1: Write the failing tests**

```typescript
// frontend/tests/use-health-connector.test.tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { useHealthDisconnect, useHealthConnectErrorFromUrl, HEALTH_CONNECT_URL } from "@/hooks/use-health-connector";

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient();
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useHealthDisconnect", () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "disconnected" }) });
  });

  it("posts to /auth/health/disconnect", async () => {
    const { result } = renderHook(() => useHealthDisconnect(), { wrapper });

    await result.current.disconnect();

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/auth/health/disconnect"),
        expect.objectContaining({ method: "POST", credentials: "include" })
      );
    });
  });
});

describe("useHealthConnectErrorFromUrl", () => {
  it("returns true when the URL has health_connect_error=1", () => {
    window.history.pushState({}, "", "/?health_connect_error=1");
    const { result } = renderHook(() => useHealthConnectErrorFromUrl());
    expect(result.current).toBe(true);
  });

  it("returns false otherwise", () => {
    window.history.pushState({}, "", "/");
    const { result } = renderHook(() => useHealthConnectErrorFromUrl());
    expect(result.current).toBe(false);
  });
});

describe("HEALTH_CONNECT_URL", () => {
  it("points at the backend health connect route", () => {
    expect(HEALTH_CONNECT_URL).toContain("/auth/health/connect");
  });
});
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run use-health-connector`
Expected: FAIL — module `@/hooks/use-health-connector` doesn't exist.

- [x] **Step 3: Implement**

```typescript
// frontend/hooks/use-health-connector.ts
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { apiFetch } from "./api";

export const HEALTH_CONNECT_URL = `${process.env.NEXT_PUBLIC_API_URL}/auth/health/connect`;

export function useHealthDisconnect() {
  const queryClient = useQueryClient();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function disconnect() {
    setIsPending(true);
    setError(null);
    try {
      await apiFetch("/auth/health/disconnect", { method: "POST" });
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    } catch (err) {
      setError(err instanceof Error ? err : new Error("Disconnect failed"));
    } finally {
      setIsPending(false);
    }
  }

  return { disconnect, isPending, error };
}

export function useHealthConnectErrorFromUrl(): boolean {
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setHasError(params.get("health_connect_error") === "1");
  }, []);

  return hasError;
}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run use-health-connector`
Expected: all PASS.

- [ ] **Step 5: Commit** (deferred — will commit later)

```bash
git add frontend/hooks/use-health-connector.ts frontend/tests/use-health-connector.test.tsx
git commit -m "feat: add health disconnect mutation and OAuth-error URL detection hook"
```

---

## Task 5: Frontend — rewrite `ConnectorsScreen` against real state, drop mock connectors ✅ DONE (not yet committed)

**Files:**
- Modify: `frontend/components/connectors-screen.tsx`
- Modify: `frontend/lib/mock-data.ts` (remove `mockConnectors`, `Connector`, `ConnectorStatus`)
- Modify: `frontend/messages/en.json`, `frontend/messages/de.json` (add one error string under `"connectors"`)
- Test: `frontend/tests/connectors-screen.test.tsx` (create if it doesn't exist — check first: `find frontend/tests -iname "*connector*"`)

**Interfaces:**
- Consumes: `useAuth()` from `frontend/lib/auth-context.tsx` (Task 3) for `user.health_connected`; `useHealthDisconnect`, `useHealthConnectErrorFromUrl`, `HEALTH_CONNECT_URL` from `frontend/hooks/use-health-connector.ts` (Task 4).
- Produces: `ConnectorsScreen` — no other component depends on this, it's a leaf screen component.

- [x] **Step 1: Check for an existing test file**

Run: `find frontend/tests -iname "*connector*"`

If one exists, read it to see what it currently asserts against the mocked version — those assertions will need rewriting since the mock data and `pending` state are gone.

- [x] **Step 2: Write the failing test**

```typescript
// frontend/tests/connectors-screen.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConnectorsScreen } from "@/components/connectors-screen";

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { email: "runner@example.com", name: "Runner", created_at: "", health_connected: true },
    isLoading: false,
  }),
}));

vi.mock("@/hooks/use-health-connector", () => ({
  HEALTH_CONNECT_URL: "http://localhost:8000/auth/health/connect",
  useHealthDisconnect: () => ({ disconnect: vi.fn(), isPending: false, error: null }),
  useHealthConnectErrorFromUrl: () => false,
}));

describe("ConnectorsScreen", () => {
  it("shows Google Health as connected and offers disconnect", () => {
    render(<ConnectorsScreen />);

    expect(screen.getByText("Google Health")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /disconnect/i })).toBeInTheDocument();
  });

  it("does not render a Google Calendar card", () => {
    render(<ConnectorsScreen />);

    expect(screen.queryByText("Google Calendar")).not.toBeInTheDocument();
  });
});
```

- [x] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run connectors-screen`
Expected: FAIL — either the component still renders the old mocked two-connector list, or the mocked modules don't match current imports.

- [x] **Step 4: Remove mock connector data**

In `frontend/lib/mock-data.ts`, delete the `ConnectorStatus` type, `Connector` type, and `mockConnectors` array (lines 4-13 and 37-56 per the current file — confirm nothing else in the codebase imports them first: `grep -rn "mockConnectors\|ConnectorStatus" frontend --include="*.tsx" --include="*.ts" -l`).

- [x] **Step 5: Add the error-state translation string**

In `frontend/messages/en.json`, under `"connectors"`:
```json
"connectFailed": "Couldn't connect to Google Health. Please try again."
```
In `frontend/messages/de.json`, under `"connectors"`, add the German equivalent (match the tone of the existing German strings in that block).

- [x] **Step 6: Implement**

```typescript
"use client";

import { useTranslations } from "next-intl";

import { Card } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import {
  HEALTH_CONNECT_URL,
  useHealthConnectErrorFromUrl,
  useHealthDisconnect,
} from "@/hooks/use-health-connector";

export function ConnectorsScreen() {
  const t = useTranslations("connectors");
  const { user } = useAuth();
  const { disconnect, isPending, error: disconnectError } = useHealthDisconnect();
  const showConnectError = useHealthConnectErrorFromUrl();

  const isConnected = user?.health_connected ?? false;

  return (
    <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:mx-auto lg:w-full lg:max-w-[720px] lg:px-0 lg:py-9">
      <div className="mb-5 lg:mb-[26px]">
        <div className="text-2xl font-bold tracking-[-0.3px] text-primary lg:text-[30px]">
          {t("title")}
        </div>
        <div className="mt-1 text-[13px] text-muted lg:mt-1.5 lg:text-sm">{t("subtitle")}</div>
      </div>

      {(showConnectError || disconnectError) && (
        <div className="mb-4 rounded-xl bg-danger/10 p-3 text-[13px] text-danger">
          {t("connectFailed")}
        </div>
      )}

      <div className="flex flex-col gap-2.5 lg:gap-3">
        <Card className="flex-row items-center justify-between gap-3 rounded-2xl p-[14px_16px] lg:gap-[14px] lg:px-5 lg:py-[18px]">
          <div className="flex min-w-0 items-center gap-3 lg:gap-[14px]">
            <div
              className="flex h-[38px] w-[38px] flex-none items-center justify-center rounded-[10px] text-[13px] font-semibold lg:h-[42px] lg:w-[42px] lg:text-sm"
              style={{ background: "var(--color-icon-tile)", color: "var(--color-accent)" }}
            >
              GH
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-primary lg:text-[15px]">Google Health</div>
              <div
                className="text-xs lg:text-[13px]"
                style={{
                  color: isConnected
                    ? "var(--color-status-connected)"
                    : "var(--color-status-disconnected)",
                }}
              >
                {isConnected ? t("connected") : t("notConnected")}
              </div>
              <div className="mt-0.5 text-[11px] text-disclaimer lg:text-xs">
                Reads activity, heart rate & sleep
              </div>
            </div>
          </div>

          {isConnected ? (
            <button
              onClick={() => disconnect()}
              disabled={isPending}
              className="flex-none cursor-pointer px-1 py-1.5 text-xs font-semibold text-danger lg:text-[13px] disabled:opacity-50"
            >
              {t("disconnect")}
            </button>
          ) : (
            <a
              href={HEALTH_CONNECT_URL}
              className="h-8 flex-none cursor-pointer rounded-full border border-primary bg-card px-3.5 text-xs font-semibold text-primary lg:h-9 lg:px-[18px] lg:text-[13px] flex items-center"
            >
              {t("connect")}
            </a>
          )}
        </Card>
      </div>
    </div>
  );
}
```

Note: `t("connecting")` / the `"pending"` string in the translation files is now unused by this component — leave the translation key in place (harmless, low-value cleanup) rather than touching unrelated i18n files further.

- [x] **Step 7: Run tests to verify they pass**

Run: `cd frontend && npx vitest run connectors-screen mock-data`
Expected: all PASS. Also run the full frontend suite to catch anything else that imported the removed mock exports: `cd frontend && npx vitest run`

- [ ] **Step 8: Commit** (deferred — will commit later)

```bash
git add frontend/components/connectors-screen.tsx frontend/lib/mock-data.ts frontend/messages/en.json frontend/messages/de.json frontend/tests/connectors-screen.test.tsx
git commit -m "feat: wire connectors screen to real Health OAuth flow, drop mocked Calendar card"
```

---

## Task 6: Manual end-to-end verification

**Files:** none — this is a verification pass, no code changes expected unless it surfaces a bug.

- [x] **Step 1: Start backend and frontend locally**

Run backend: `uvicorn backend.agent:app --reload` (or whatever the project's existing run command is — check `docs/PLAN.md` or `README` if unsure).
Run frontend: `cd frontend && npm run dev`

- [x] **Step 2: Log in, confirm disconnected state**

Log in via Google. On the connectors screen, confirm Google Health shows "Not connected" and a "Connect" button (assuming this account has no prior Health token — if the DB already has one from earlier manual testing, disconnect first).

- [x] **Step 3: Click Connect, complete Google's consent screen**

Confirm it lands back on the app and the connectors screen now shows "Connected" with a "Disconnect" button, without a manual page refresh.

- [x] **Step 4: Click Disconnect**

Confirm it flips back to "Not connected" without a manual refresh.

- [x] **Step 5: Verify the chat still works with a fresh Health connection**

Ask the chat something that requires a tool call (e.g. "how'd my week look?") and confirm it returns real data — this exercises the token this task just wrote through the full path down to the MCP server.

- [x] **Step 6: Report back**

No commit for this task — it's verification only. If any step fails, that's a bug to fix as a follow-up, not something to paper over here.
