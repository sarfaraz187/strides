# ACCOUNT_NOT_LINKED error handling

## Problem

A user can complete the Health OAuth flow successfully (valid token stored in
`oauth_tokens`), but Google Health still rejects every data request with:

```json
{
  "error": {
    "code": 400,
    "message": "The account is not linked to Google Health.",
    "status": "FAILED_PRECONDITION",
    "details": [{
      "@type": "type.googleapis.com/google.rpc.ErrorInfo",
      "reason": "ACCOUNT_NOT_LINKED",
      "domain": "health.googleapis.com",
      "metadata": { "redirect_uri": "https://fitbit.google.com/auth/signup" }
    }]
  }
}
```

This happens when the underlying Google account has never signed up for
Google Health (a separate product from the Fit app, backed by Fitbit).
Reconnecting the OAuth flow does not fix this — the token is fine, the
account just isn't enrolled.

Today `get_health_data` (`mcp_servers/fit_server/helpers/health_api.py`)
collapses every failure — this one included — into a generic error
**string**. That string then gets fed into `parse_run()`, which expects a
dict, so the failure mode is a crash/garbage output rather than a
meaningful message. `backend/routes/dashboard.py`'s broad
`except Exception` catches whatever happens as a result and reports
`health_connected: False`, which is also wrong: the connection is valid,
there's just no data.

## Goals

- Distinguish `ACCOUNT_NOT_LINKED` (and other structured Google errors)
  from real connection failures (MCP down, invalid/expired token).
- Surface Google's own message and its `redirect_uri` for fixing the
  problem, rather than inventing our own copy or guessing a URL.
- Don't crash `parse_run`/stat aggregation when the underlying API call
  fails.
- Chat should be able to explain the situation to the user without new
  chat-specific code.

## Non-goals

- Surfacing this on the connectors screen (`connectors-screen.tsx`).
  `/auth/me` only checks for the presence of an OAuth token row — it
  never calls the Health API — so it has no way to know about
  `ACCOUNT_NOT_LINKED` without adding a live API call to every auth
  check. Only `/dashboard` actually calls the MCP tools and can see this
  error. The connectors screen keeps showing plain "Connected", which is
  accurate (the OAuth link itself is valid).
- Handling every possible Google error reason specially. Only
  `ACCOUNT_NOT_LINKED` gets a tailored frontend message for now; anything
  else with a recognizable `reason` still gets tagged and passed through,
  but has no bespoke UI treatment yet.

## Design

### 1. `mcp_servers/fit_server/helpers/health_api.py`

`get_health_data`'s return type changes from `dict | str` to always
`dict[str, Any]`. On success: parsed JSON, unchanged. On failure: a
tagged error dict built from Google's response shape:

```python
{
    "error": "ACCOUNT_NOT_LINKED",
    "message": "The account is not linked to Google Health.",
    "redirect_uri": "https://fitbit.google.com/auth/signup",
}
```

- `error` comes from `error.details[].reason` where the detail's
  `@type` is `type.googleapis.com/google.rpc.ErrorInfo`. Falls back to
  `"UNKNOWN_ERROR"` if the response body doesn't have that shape.
- `message` comes from Google's top-level `error.message`.
- `redirect_uri` comes from that same `ErrorInfo` detail's
  `metadata.redirect_uri`, when present. Omitted (not present in the
  dict) when Google doesn't supply one.
- Non-HTTP exceptions (timeouts, connection errors) return
  `{"error": "REQUEST_FAILED", "message": "..."}` with no `redirect_uri`.

### 2. `mcp_servers/fit_server/server.py`

Each tool that calls `get_health_data` and then post-processes the result
(`get_runs`, `get_recent_runs`, `get_run_stats`) adds a guard:

```python
if "error" in response:
    return response
```

placed before the response is handed to `parse_run`/aggregation. The
tagged dict becomes the tool's structured content, unchanged, for
whichever caller invoked it (backend `/dashboard` route or the chat
agent).

`get_weekly_stats` calls `get_run_stats` internally, so it inherits this
behavior with no separate change.

Chat gets this for free: the LLM agent already reads tool
`structuredContent` and can explain `{"error": "ACCOUNT_NOT_LINKED", ...}`
conversationally — no new code in `chat.py` or `chat_service.py`.

### 3. `backend/routes/dashboard.py`

After calling `get_weekly_stats`/`get_recent_runs`, check whether the
structured content carries an `"error"` key. If so:

- `health_connected` stays `True` (the OAuth link is valid).
- A new `health_error` field is added to the response, carrying the
  tagged dict as-is: `{"error": ..., "message": ..., "redirect_uri": ...}`.
- `weekly_stats` stays `None`, `recent_runs` stays `[]`.

The existing broad `except Exception` (MCP down, token failure, etc.)
is unchanged and still collapses to `health_connected: False`,
`health_error` absent/`None`.

Final response shape:

```json
{
  "weekly_stats": null,
  "recent_runs": [],
  "health_connected": true,
  "health_error": {
    "error": "ACCOUNT_NOT_LINKED",
    "message": "The account is not linked to Google Health.",
    "redirect_uri": "https://fitbit.google.com/auth/signup"
  }
}
```

### 4. Frontend

`frontend/lib/dashboard-api.ts` — add the type and field:

```ts
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
```

`frontend/components/dashboard-screen.tsx` — when
`dashboard?.health_error` is present, render a notice card in place of
the weekly-stats card and recent-runs list (the header with today's date
and "This week" stays as-is above it). The notice shows Google's
`message` as body text and, when `redirect_uri` is present, a
link/button to it (e.g. "Continue setup"). When `redirect_uri` is
absent, the notice renders without a link.

Connectors screen: no change (see Non-goals).

## Data flow

```
Google Health API (400 ACCOUNT_NOT_LINKED)
  -> health_api.py: tagged dict {error, message, redirect_uri}
  -> server.py tools: pass dict straight through (short-circuit before parse_run)
  -> dashboard.py: health_connected stays True, health_error = tagged dict
  -> frontend: dashboard-screen.tsx renders notice card instead of empty stats
  -> chat.py: unaffected -- LLM agent sees the same tagged dict from tool
     calls and explains it conversationally
```

## Testing

Per the project's TDD workflow (Claude writes failing tests, user
implements):

- `health_api.py`: parsing of a Google `ErrorInfo`-shaped 400 into the
  tagged dict (reason, message, redirect_uri); fallback to
  `UNKNOWN_ERROR` for a differently-shaped error body; `REQUEST_FAILED`
  for a non-HTTP exception (e.g. connection error).
- `server.py` tools: each of `get_runs`, `get_recent_runs`,
  `get_run_stats` returns the tagged dict unchanged when
  `get_health_data` returns one, instead of raising inside
  `parse_run`/aggregation.
- `backend/routes/dashboard.py`: new
  `test_dashboard_connected_but_account_not_linked_returns_health_error`,
  alongside the three existing dashboard tests (all of which should
  continue to pass unchanged).
- Frontend: a case in `dashboard-screen.test.tsx` asserting the notice
  card renders (message + link) when `health_error` is present, and the
  normal stats/recent-runs UI renders when it's absent.
