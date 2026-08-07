# ACCOUNT_NOT_LINKED Error Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project override:** This repo's `CLAUDE.md` defines a stricter per-task loop for backend tasks: Claude writes the failing test, the **user** implements the code change themselves (not a subagent), Claude then reviews the diff before the task is marked done. Tasks 1-3 (Python/backend) MUST follow that loop, not the standard "implementer writes test + code" pattern. Task 4 (frontend) may follow the normal TDD loop unless the user says otherwise.

**Goal:** When Google Health rejects API calls with `ACCOUNT_NOT_LINKED` (valid OAuth token, but the underlying Google account was never enrolled in Google Health), surface a specific, actionable message end-to-end instead of a generic broken/disconnected state.

**Architecture:** `get_health_data` returns a tagged error dict instead of a bare string on failure. The MCP tools in `server.py` short-circuit and pass that dict through unchanged. `backend/routes/dashboard.py` detects the tagged dict and adds a `health_error` field to its response (keeping `health_connected: true`, since the OAuth link itself is fine). The frontend dashboard renders a notice card with Google's message and a link when `health_error` is present.

**Tech Stack:** Python (FastMCP, requests, pytest), Next.js/React/TypeScript (Vitest, Testing Library).

## Global Constraints

- Error dict shape, exactly: `{"error": "<REASON>", "message": "<google message>", "redirect_uri": "<uri, if present>"}`. `redirect_uri` key is entirely absent from the dict when Google doesn't supply one (not `None`).
- `error` reason is read from the response's `error.details[]` entry whose `@type` is `"type.googleapis.com/google.rpc.ErrorInfo"`, using its `reason` field. Fallback: `"UNKNOWN_ERROR"` for HTTP errors without that shape, `"REQUEST_FAILED"` for non-HTTP exceptions.
- `redirect_uri`, when present, comes from that same `ErrorInfo` detail's `metadata.redirect_uri` — never hardcoded.
- `get_health_data`'s return type is always `dict[str, Any]` (the `| str` union is removed).
- `dashboard.py`'s existing broad `except Exception` behavior (health_connected: False on real failures) is unchanged — this is additive, not a replacement.
- Connectors screen (`connectors-screen.tsx`) is explicitly out of scope — do not touch it.

---

### Task 1: Structured errors from `get_health_data`

**Files:**
- Modify: `mcp_servers/fit_server/helpers/health_api.py`
- Test: `tests/mcp_servers/fit_server/helpers/test_health_api.py` (new file; new dirs needed: `tests/mcp_servers/`, `tests/mcp_servers/fit_server/`, `tests/mcp_servers/fit_server/helpers/`)

**Interfaces:**
- Produces: `get_health_data(access_token: str, url: str, params: dict | None = None) -> dict[str, Any]`. On success: parsed JSON body. On failure: `{"error": str, "message": str}` or `{"error": str, "message": str, "redirect_uri": str}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/mcp_servers/fit_server/helpers/test_health_api.py
import requests
import responses

from mcp_servers.fit_server.helpers.health_api import get_health_data

URL = "https://health.googleapis.com/v4/users/me/dataTypes/exercise/dataPoints"


@responses.activate
def test_account_not_linked_returns_tagged_error_with_redirect_uri():
    responses.add(
        responses.GET,
        URL,
        json={
            "error": {
                "code": 400,
                "message": "The account is not linked to Google Health.",
                "status": "FAILED_PRECONDITION",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": "ACCOUNT_NOT_LINKED",
                        "domain": "health.googleapis.com",
                        "metadata": {
                            "redirect_uri": "https://fitbit.google.com/auth/signup"
                        },
                    }
                ],
            }
        },
        status=400,
    )

    result = get_health_data("fake-token", URL)

    assert result == {
        "error": "ACCOUNT_NOT_LINKED",
        "message": "The account is not linked to Google Health.",
        "redirect_uri": "https://fitbit.google.com/auth/signup",
    }


@responses.activate
def test_http_error_without_error_info_shape_returns_unknown_error():
    responses.add(
        responses.GET,
        URL,
        json={"error": {"code": 401, "message": "Invalid credentials", "status": "UNAUTHENTICATED"}},
        status=401,
    )

    result = get_health_data("fake-token", URL)

    assert result == {"error": "UNKNOWN_ERROR", "message": "Invalid credentials"}
    assert "redirect_uri" not in result


def test_connection_failure_returns_request_failed(monkeypatch):
    def raise_connection_error(*args, **kwargs):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(requests, "get", raise_connection_error)

    result = get_health_data("fake-token", URL)

    assert result == {"error": "REQUEST_FAILED", "message": "network down"}


@responses.activate
def test_success_returns_parsed_json_unchanged():
    responses.add(responses.GET, URL, json={"point": [{"foo": "bar"}]}, status=200)

    result = get_health_data("fake-token", URL)

    assert result == {"point": [{"foo": "bar"}]}
```

Note: this introduces the `responses` library for mocking `requests` calls. Check whether it's already a dependency; if not, this needs `uv add --dev responses` (or equivalent) before the tests can run — flag this to the user rather than installing silently, per the project's "never install new dependencies without asking first" rule.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mcp_servers/fit_server/helpers/test_health_api.py -v`
Expected: FAIL (current `get_health_data` returns a generic string on every error path, not a tagged dict; also confirm whether `responses` needs installing first — that failure should surface here too).

- [ ] **Step 3: User implements the code change**

Per the project's backend workflow, the user writes the implementation in `mcp_servers/fit_server/helpers/health_api.py` themselves. Expected shape (for Claude's review reference, not to be written by Claude):

```python
import logging
from typing import Any

import requests


def get_health_data(
    access_token: str, url: str, params: dict | None = None
) -> dict[str, Any]:
    try:
        response = requests.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        logging.error(f"Health API request failed: {e} — {e.response.text}")
        return _parse_error(e.response)
    except Exception as e:
        logging.error(f"Health API request failed: {e}")
        return {"error": "REQUEST_FAILED", "message": str(e)}


def _parse_error(response: requests.Response) -> dict[str, Any]:
    try:
        body = response.json()
        error = body["error"]
        for detail in error.get("details", []):
            if detail.get("@type") == "type.googleapis.com/google.rpc.ErrorInfo":
                result = {"error": detail["reason"], "message": error["message"]}
                redirect_uri = detail.get("metadata", {}).get("redirect_uri")
                if redirect_uri:
                    result["redirect_uri"] = redirect_uri
                return result
        return {"error": "UNKNOWN_ERROR", "message": error.get("message", "Unknown error")}
    except (ValueError, KeyError):
        return {"error": "UNKNOWN_ERROR", "message": "Health API request failed."}
```

- [ ] **Step 4: Claude reviews the diff**

Check: return type is always a dict (no leftover string paths), `redirect_uri` key is fully absent (not `None`) when not supplied, logging is preserved, no debug prints left in.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/mcp_servers/fit_server/helpers/test_health_api.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 6: Commit**

Ask the user before committing (per workflow, the commit step stays unchecked until they explicitly say to commit).

```bash
git add mcp_servers/fit_server/helpers/health_api.py tests/mcp_servers/fit_server/helpers/test_health_api.py
git commit -m "fix: return structured errors from get_health_data instead of a generic string"
```

---

### Task 2: MCP tools short-circuit on tagged errors

**Files:**
- Modify: `mcp_servers/fit_server/server.py` (lines 58-115: `get_recent_runs`, `get_run_stats`)
- Test: `tests/mcp_servers/fit_server/test_server.py` (new file)

**Interfaces:**
- Consumes: `get_health_data(...) -> dict[str, Any]` from Task 1, where a failure dict always has an `"error"` key.
- Produces: `get_recent_runs(days: int = 7)`, `get_run_stats(start_date: str, end_date: str)` — each returns the tagged error dict unchanged (instead of raising) when `get_health_data` returns one. `get_weekly_stats()` inherits this via `get_run_stats`, so it needs no separate change or test. `get_runs()` already returns `get_health_data`'s response as-is with no post-processing, so it's already correct and out of scope for this task.

- [ ] **Step 1: Write the failing tests**

```python
# tests/mcp_servers/fit_server/test_server.py
from unittest.mock import patch

from mcp_servers.fit_server import server

ERROR_RESPONSE = {
    "error": "ACCOUNT_NOT_LINKED",
    "message": "The account is not linked to Google Health.",
    "redirect_uri": "https://fitbit.google.com/auth/signup",
}


@patch("mcp_servers.fit_server.server.get_valid_access_token", return_value="fake-token")
@patch("mcp_servers.fit_server.server.current_user_id", return_value="user-1")
@patch("mcp_servers.fit_server.server.get_health_data", return_value=ERROR_RESPONSE)
def test_get_recent_runs_returns_error_dict_instead_of_crashing_parse_run(
    mock_get_health_data, mock_user_id, mock_token
):
    result = server.get_recent_runs(days=7)
    assert result == ERROR_RESPONSE


@patch("mcp_servers.fit_server.server.get_valid_access_token", return_value="fake-token")
@patch("mcp_servers.fit_server.server.current_user_id", return_value="user-1")
@patch("mcp_servers.fit_server.server.get_health_data", return_value=ERROR_RESPONSE)
def test_get_run_stats_returns_error_dict_instead_of_crashing_aggregation(
    mock_get_health_data, mock_user_id, mock_token
):
    result = server.get_run_stats("2026-08-01", "2026-08-07")
    assert result == ERROR_RESPONSE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mcp_servers/fit_server/test_server.py -v`
Expected: FAIL — `get_recent_runs`/`get_run_stats` currently call `parse_run(response)` on the dict without checking for `"error"`; `parse_run` will either raise a `KeyError` (no `"point"` key) or return nonsense, so the assertions on `result == ERROR_RESPONSE` fail.

- [ ] **Step 3: User implements the code change**

Expected shape (reference for review, not to be written by Claude) — add a guard after each `get_health_data` call:

```python
response = get_health_data(...)
if "error" in response:
    return response
```

in `get_recent_runs` and `get_run_stats`, before the existing `logging.info`/`parse_run`/aggregation lines.

- [ ] **Step 4: Claude reviews the diff**

Check: guard placed before `parse_run`/aggregation in both tools, no duplicate logic, existing logging statements still make sense given the early return, `get_runs` left untouched.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/mcp_servers/fit_server/test_server.py -v`
Expected: PASS (both tests)

Also re-run Task 1's tests to confirm no regression: `pytest tests/mcp_servers/fit_server/helpers/test_health_api.py -v`

- [ ] **Step 6: Commit**

Ask the user before committing.

```bash
git add mcp_servers/fit_server/server.py tests/mcp_servers/fit_server/test_server.py
git commit -m "fix: short-circuit MCP tools on structured Health API errors"
```

---

### Task 3: `/dashboard` route surfaces `health_error`

**Files:**
- Modify: `backend/routes/dashboard.py`
- Test: `tests/backend/routes/test_dashboard.py` (existing file — add one test, alongside the three already there)

**Interfaces:**
- Consumes: MCP tool call results whose `structuredContent` may be `{"error": ..., "message": ..., "redirect_uri"?: ...}` (from Task 2).
- Produces: `/dashboard` response gains an optional `health_error` field: `{"error": str, "message": str, "redirect_uri"?: str} | None`. `health_connected` stays `True` when `health_error` is set (OAuth link is valid).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/backend/routes/test_dashboard.py

def test_dashboard_connected_but_account_not_linked_returns_health_error(client):
    cookies = _session_cookie(client)
    user_id = find_or_create_user(
        "dashboard-route@example.com", "dashboard-route-sub", "Dashboard Route"
    )
    save_oauth_token(user_id, "health", "access-token", "refresh-token", 9999999999)

    health_error = {
        "error": "ACCOUNT_NOT_LINKED",
        "message": "The account is not linked to Google Health.",
        "redirect_uri": "https://fitbit.google.com/auth/signup",
    }

    with patch(
        "backend.routes.dashboard.open_mcp_session",
        _mock_session_with_error(health_error),
    ):
        response = client.get("/dashboard", cookies=cookies)

    assert response.status_code == 200
    body = response.json()
    assert body["health_connected"] is True
    assert body["health_error"] == health_error
    assert body["weekly_stats"] is None
    assert body["recent_runs"] == []
```

This test needs a `_mock_session_with_error` helper alongside the existing `_mock_session` in the same test file:

```python
def _mock_session_with_error(error_dict: dict):
    session = AsyncMock()

    async def call_tool(name, args):
        result = AsyncMock()
        if name == "get_weekly_stats":
            result.structuredContent = error_dict
        elif name == "get_recent_runs":
            result.structuredContent = error_dict
        return result

    session.call_tool.side_effect = call_tool

    @asynccontextmanager
    async def open_mcp_session(user_id):
        yield session

    return open_mcp_session
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/routes/test_dashboard.py::test_dashboard_connected_but_account_not_linked_returns_health_error -v`
Expected: FAIL — current `dashboard.py` calls `recent_result.structuredContent["result"]`, which raises `KeyError`/`TypeError` since the mocked structured content is the error dict, not `{"result": [...]}`. That exception is caught by the existing broad `except Exception`, so today's behavior would (incorrectly) report `health_connected: False` with no `health_error` key at all — the assertions fail either way.

- [ ] **Step 3: User implements the code change**

Expected shape (reference for review, not to be written by Claude):

```python
from fastapi import APIRouter, Depends

from backend.dependencies import require_user
from backend.services.mcp_client import open_mcp_session
from data.db import get_oauth_token

router = APIRouter()


@router.get("/dashboard")
async def dashboard(user_id: str = Depends(require_user)):
    health_connected = get_oauth_token(user_id, "health") is not None
    weekly_stats, recent_runs, health_error = None, [], None

    if health_connected:
        try:
            async with open_mcp_session(user_id) as session:
                weekly_result = await session.call_tool("get_weekly_stats", {})
                recent_result = await session.call_tool("get_recent_runs", {"days": 7})

            weekly_content = weekly_result.structuredContent
            recent_content = recent_result.structuredContent

            if isinstance(weekly_content, dict) and "error" in weekly_content:
                health_error = weekly_content
            elif isinstance(recent_content, dict) and "error" in recent_content:
                health_error = recent_content
            else:
                weekly_stats = weekly_content
                recent_runs = recent_content["result"]
        except Exception:
            health_connected = False

    return {
        "weekly_stats": weekly_stats,
        "recent_runs": recent_runs,
        "health_connected": health_connected,
        "health_error": health_error,
    }
```

- [ ] **Step 4: Claude reviews the diff**

Check: `health_connected` stays `True` on the error path, `weekly_stats`/`recent_runs` stay at their empty defaults, the existing broad `except Exception` still wraps genuine MCP/token failures (so it still sets `health_connected: False`), no regression to the three existing dashboard tests.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/backend/routes/test_dashboard.py -v`
Expected: PASS (all 5 tests: the 4 existing + the new one)

- [ ] **Step 6: Commit**

Ask the user before committing.

```bash
git add backend/routes/dashboard.py tests/backend/routes/test_dashboard.py
git commit -m "feat: surface ACCOUNT_NOT_LINKED as health_error on the dashboard route"
```

---

### Task 4: Frontend notice card for `health_error`

**Files:**
- Modify: `frontend/lib/dashboard-api.ts`
- Modify: `frontend/components/dashboard-screen.tsx`
- Modify: `frontend/messages/en.json`, `frontend/messages/de.json` (add `dashboard.healthErrorAction` translation key)
- Test: `frontend/tests/dashboard-screen.test.tsx` (existing file — add a case)

**Interfaces:**
- Consumes: `/dashboard` response's `health_error?: { error: string; message: string; redirect_uri?: string } | null` field (from Task 3).
- Produces: `Dashboard` type in `dashboard-api.ts` gains `health_error`; `DashboardScreen` renders a notice card instead of the stats/recent-runs blocks when it's present.

- [ ] **Step 1: Add the type**

```typescript
// frontend/lib/dashboard-api.ts
import { apiFetch } from "@/lib/api";

export type WeeklyStats = {
  run_count: number;
  total_distance_km: number;
  total_duration_min: number;
  avg_pace_min_per_km: number | null;
};

export type RecentRun = {
  date: string;
  distance_km: number;
  duration_min: number;
  pace_min_per_km: number | null;
  calories: number | null;
};

export type HealthError = {
  error: string;
  message: string;
  redirect_uri?: string;
};

export type Dashboard = {
  weekly_stats: WeeklyStats | null;
  recent_runs: RecentRun[];
  health_error?: HealthError | null;
};

export function getDashboard(): Promise<Dashboard> {
  return apiFetch<Dashboard>("/dashboard");
}
```

- [ ] **Step 2: Add the translation key**

```json
// frontend/messages/en.json, inside "dashboard"
"healthErrorAction": "Continue setup"
```

```json
// frontend/messages/de.json, inside "dashboard"
"healthErrorAction": "Einrichtung fortsetzen"
```

- [ ] **Step 3: Write the failing test**

```typescript
// add to frontend/tests/dashboard-screen.test.tsx

function mockFetchResponsesWithHealthError() {
  vi.spyOn(global, "fetch").mockImplementation((url) => {
    if (String(url).endsWith("/dashboard")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            weekly_stats: null,
            recent_runs: [],
            health_error: {
              error: "ACCOUNT_NOT_LINKED",
              message: "The account is not linked to Google Health.",
              redirect_uri: "https://fitbit.google.com/auth/signup",
            },
          })
        )
      );
    }
    if (String(url).endsWith("/preferences")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            weekly_goal_km: 30,
            units: "km",
            notifications_enabled: true,
            language: "en",
          })
        )
      );
    }
    return Promise.reject(new Error(`Unexpected fetch to ${url}`));
  });
}

describe("DashboardScreen health_error state", () => {
  it("renders the account-not-linked notice with a link instead of stats", async () => {
    mockFetchResponsesWithHealthError();
    renderWithProviders(<DashboardScreen locale="en" />);

    await waitFor(() =>
      expect(
        screen.getByText("The account is not linked to Google Health.")
      ).toBeInTheDocument()
    );

    const link = screen.getByRole("link", { name: en.dashboard.healthErrorAction });
    expect(link).toHaveAttribute("href", "https://fitbit.google.com/auth/signup");
  });
});
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/dashboard-screen.test.tsx`
Expected: FAIL — `DashboardScreen` doesn't read `health_error` yet, so neither the message text nor the link exist.

- [ ] **Step 5: Implement**

```tsx
// frontend/components/dashboard-screen.tsx
"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import { Avatar } from "@/components/avatar";
import { Card } from "@/components/ui/card";
import { useDashboard } from "@/hooks/use-dashboard";
import { usePreferences } from "@/hooks/use-preferences";
import { useAuth } from "@/lib/auth-context";
import type { RecentRun } from "@/lib/dashboard-api";

function formatPace(paceMinPerKm: number | null): string {
  if (paceMinPerKm === null) return "–";
  const minutes = Math.floor(paceMinPerKm);
  const seconds = Math.round((paceMinPerKm - minutes) * 60);
  return `${minutes}:${seconds.toString().padStart(2, "0")}/km`;
}

function formatRun(run: RecentRun, locale: string) {
  const date = new Date(run.date);
  return {
    day: date.toLocaleDateString(locale, { weekday: "long" }),
    time: date.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" }),
    distance: `${run.distance_km} km`,
    pace: formatPace(run.pace_min_per_km),
  };
}

export function DashboardScreen({ locale }: { locale: string }) {
  const t = useTranslations("dashboard");
  const { user } = useAuth();
  const { dashboard, isLoading } = useDashboard();
  const { preferences } = usePreferences();
  const today = new Date().toLocaleDateString(locale, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });

  const weeklyGoalKm = preferences?.weekly_goal_km ?? 30;
  const weekStats = [
    { value: isLoading ? "–" : String(dashboard?.weekly_stats?.total_distance_km ?? 0), label: "km" },
    {
      value: isLoading
        ? "–"
        : formatPace(dashboard?.weekly_stats?.avg_pace_min_per_km ?? null).replace("/km", ""),
      label: "avg /km",
    },
    { value: isLoading ? "–" : String(dashboard?.weekly_stats?.run_count ?? 0), label: "runs" },
  ];
  const weekGoalPct = dashboard?.weekly_stats
    ? Math.min(100, Math.round((dashboard.weekly_stats.total_distance_km / weeklyGoalKm) * 100))
    : 0;
  const recentRuns = dashboard?.recent_runs.map((run) => formatRun(run, locale)) ?? [];
  const healthError = dashboard?.health_error;

  return (
    <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:px-[44px] lg:py-9">
      <div className="mb-[22px] flex items-center justify-between lg:mb-[26px] lg:items-end">
        <div>
          <div className="text-[13px] text-muted lg:text-sm">{today}</div>
          <div className="text-2xl font-bold tracking-[-0.3px] text-primary lg:text-[30px]">
            {t("thisWeek")}
          </div>
        </div>
        <Link href={`/${locale}/profile`} className="lg:hidden">
          <Avatar
            user={{ name: user?.name ?? null, avatar_url: user?.avatar_url ?? null }}
            size="md"
            className="h-[38px] w-[38px] rounded-xl"
          />
        </Link>
      </div>

      {healthError ? (
        <Card className="rounded-[20px] p-[22px] lg:p-7">
          <div className="mb-2 text-sm font-semibold text-primary">{healthError.message}</div>
          {healthError.redirect_uri && (
            <a
              href={healthError.redirect_uri}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block text-sm font-semibold text-accent-light underline"
            >
              {t("healthErrorAction")}
            </a>
          )}
        </Card>
      ) : (
        <>
          <div className="lg:mb-7">
            <div className="mb-4 flex flex-col gap-4 rounded-[20px] bg-primary p-[22px] lg:mb-0 lg:gap-[18px] lg:p-7">
              <div className="flex justify-between">
                {weekStats.map((stat) => (
                  <div key={stat.label} className="flex flex-col gap-1">
                    <div className="font-mono text-[26px] font-bold text-primary-foreground lg:text-[32px]">
                      {stat.value}
                    </div>
                    <div className="text-[11px] font-medium uppercase text-stat-label">
                      {stat.label}
                    </div>
                  </div>
                ))}
              </div>
              <div className="h-px bg-primary-foreground/10" />
              <div className="flex items-center justify-between">
                <div className="text-[13px] text-goal-label lg:text-sm">
                  {t("goal", { distance: weeklyGoalKm })}
                </div>
                <div className="font-mono text-[13px] font-semibold text-primary-foreground lg:text-sm">
                  {weekGoalPct}%
                </div>
              </div>
              <div className="h-[6px] w-full overflow-hidden rounded-full bg-primary-foreground/[0.14]">
                <div
                  className="h-full rounded-full bg-accent-light"
                  style={{ width: `${weekGoalPct}%` }}
                />
              </div>
            </div>
          </div>

          <div className="mb-2.5 mt-5 text-[13px] font-semibold uppercase text-muted lg:mt-0">
            {t("recentRuns")}
          </div>
          <div className="flex flex-col gap-2.5 lg:grid lg:grid-cols-2 lg:gap-3">
            {recentRuns.map((run) => (
              <Card
                key={`${run.day}-${run.time}`}
                className="flex flex-row items-center justify-between rounded-[16px] p-4 lg:px-5 lg:py-[18px]"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-icon-tile lg:h-[38px] lg:w-[38px]">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                      <path d="M13 3L4 14h7l-1 7 9-11h-7l1-7z" fill="#5C7A5E" />
                    </svg>
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-primary">{run.day}</div>
                    <div className="text-xs text-muted-light">{run.time}</div>
                  </div>
                </div>
                <div className="text-right font-mono">
                  <div className="text-sm font-semibold text-primary">{run.distance}</div>
                  <div className="text-xs text-muted-light">{run.pace}</div>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npx vitest run tests/dashboard-screen.test.tsx`
Expected: PASS (all cases, including the pre-existing ones — confirm the non-error path still renders stats/recent-runs unchanged)

- [ ] **Step 7: Commit**

Ask the user before committing.

```bash
git add frontend/lib/dashboard-api.ts frontend/components/dashboard-screen.tsx frontend/messages/en.json frontend/messages/de.json frontend/tests/dashboard-screen.test.tsx
git commit -m "feat: show account-not-linked notice on the dashboard instead of empty stats"
```

---

### Task 5: Commit the design spec

**Files:**
- Existing: `docs/superpowers/specs/2026-08-07-account-not-linked-error-handling-design.md` (already written and reviewed)

- [ ] **Step 1: Commit**

Ask the user before committing.

```bash
git add docs/superpowers/specs/2026-08-07-account-not-linked-error-handling-design.md docs/superpowers/plans/2026-08-07-account-not-linked-error-handling.md
git commit -m "docs: add design spec and implementation plan for ACCOUNT_NOT_LINKED handling"
```
