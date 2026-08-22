# Calendar Planning + Weather Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project-specific note:** this repo's `CLAUDE.md` defines its own per-task loop
> (Claude writes the failing test, the human implements, Claude reviews the diff). If
> executing inline with the project owner rather than via subagents, follow that loop
> instead of writing the implementation yourself — steps below still specify the exact
> test and code content either way.
>
> **Commit policy:** we commit only once, at the end (see "Final Commit"), not after each task.

**Goal:** Add a Google Calendar MCP server (planned runs, read/write) and an in-process
weather service (Open-Meteo), wired into the dashboard and the chat agent, so Strides can
plan and display upcoming runs with forecast data.

**Architecture:** A new `calendar_server` MCP server (mirrors `fit_server`'s auth/tool
shape exactly) backed by a new `oauth_tokens` row (`provider = "calendar"`) and a
dedicated "Strides Runs" Google Calendar. A new plain `weather_service.py` module (no
OAuth, no MCP) called directly by both `dashboard.py` and `chat_service.py`. The backend
gains a second MCP client session (calendar) alongside the existing Health session so the
chat agent can plan runs directly.

**Tech Stack:** FastAPI, `psycopg`, FastMCP (Streamable HTTP), PyJWT/RS256, `httpx`,
Next.js/React Query, Open-Meteo REST APIs (Forecast + Air Quality, no key required).

**Spec:** `docs/superpowers/specs/2026-08-21-calendar-weather-integration-design.md`

## Global Constraints

- Separate OAuth connector and separate `oauth_tokens` row (`provider = "calendar"`) from
  Health — never merge scopes or tokens.
- Planned runs live only on a dedicated "Strides Runs" Google Calendar, never the user's
  primary calendar.
- Weather is a plain in-process module (`backend/services/weather_service.py`), not an MCP
  server — no OAuth/per-user token involved.
- Weather provider is Open-Meteo (Forecast API + Air Quality API) — free, no API key, so no
  new secret to provision.
- "Plan a run" is a dumb quick-add form calling `create_run_event` directly — it must never
  invoke the chat agent.
- Calendar/weather failures must degrade the dashboard gracefully (omit the affected
  section/line), never 500 the whole page.
- `calendar_server` is deployed as its own Cloud Run service, not folded into `fit_server`.

---

## File Structure

**Backend:**
- Modify: `data/db.py` — add `calendar_id` column + `get_calendar_id`/`save_calendar_id`.
- Modify: `auth/auth.py` — generalize `get_valid_access_token` to take a `provider` param.
- Modify: `backend/services/auth_service.py` — add Calendar OAuth URL/exchange functions.
- Modify: `backend/routes/auth.py` — add `/auth/calendar/*` routes, extend `/auth/me`.
- Create: `backend/services/weather_service.py` — Open-Meteo wrapper.
- Modify: `backend/services/mcp_client.py` — generalize to open a session against any
  server URL.
- Modify: `backend/services/chat_service.py` — open both MCP sessions, add
  `get_weather` local tool, route tool calls to the right session.
- Modify: `backend/agent.py` — extend `SYSTEM_PROMPT` with Calendar/weather guidance.
- Create: `backend/routes/calendar.py` — `POST /calendar/events` (quick-add).
- Modify: `backend/routes/dashboard.py` — add `upcoming_runs`/`current_weather`.
- Modify: `backend/routes/preferences.py` + `data/db.py` — add `location_lat`/`location_lon`.
- Modify: `backend/main.py` (or wherever routers are registered) — mount new router.

**MCP server:**
- Create: `mcp_servers/calendar_server/server.py`
- Create: `mcp_servers/calendar_server/mcp_auth.py` (copy of `fit_server`'s, same JWKS)
- Create: `mcp_servers/calendar_server/helpers/common.py` (copy of `fit_server`'s)
- Create: `mcp_servers/calendar_server/helpers/calendar_api.py` — raw Calendar REST calls.
- Create: `mcp_servers/calendar_server/Dockerfile`

**Frontend:**
- Create: `frontend/lib/calendar-api.ts`
- Create: `frontend/hooks/use-calendar-connector.ts`
- Create: `frontend/hooks/use-plan-run.ts`
- Modify: `frontend/lib/dashboard-api.ts` — add `upcoming_runs`/`current_weather` types.
- Modify: `frontend/lib/preferences-api.ts` — add `location_lat`/`location_lon`.
- Modify: `frontend/components/dashboard-screen.tsx` — add Upcoming Runs + Weather card +
  Plan a run button/modal.
- Modify: `frontend/components/connectors-screen.tsx` — re-add Google Calendar row.

**CI:**
- Modify: `.github/workflows/deploy.yml` — add `deploy-calendar-server` job.

**Tests:** one test file per modified/created backend module, under `tests/`, matching the
existing mirrored structure (`tests/data/test_db.py`, `tests/auth/test_auth.py`,
`tests/mcp_servers/calendar_server/...`, `tests/backend/routes/...`,
`tests/backend/services/...`).

---

### Task 1: DB — calendar token storage (`calendar_id` column)

**Files:**
- Modify: `data/db.py`
- Test: `tests/data/test_db.py`

**Interfaces:**
- Produces: `get_calendar_id(user_id: str) -> str | None`,
  `save_calendar_id(user_id: str, calendar_id: str) -> None`.

- [ ] **Step 1: Write the failing test**

Add to `tests/data/test_db.py`:

```python
def test_save_and_get_calendar_id_roundtrip():
    user_id = find_or_create_user("runner@example.com", "google-sub-1", "Runner")
    db.save_oauth_token(user_id, "calendar", "access-1", "refresh-1", 9999999999)

    assert db.get_calendar_id(user_id) is None

    db.save_calendar_id(user_id, "strides-runs-calendar-id")

    assert db.get_calendar_id(user_id) == "strides-runs-calendar-id"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/data/test_db.py::test_save_and_get_calendar_id_roundtrip -v`
Expected: FAIL with `AttributeError: module 'data.db' has no attribute 'get_calendar_id'`

- [ ] **Step 3: Add the column and functions**

In `data/db.py`, inside `init_db()`, after the existing `oauth_tokens` table creation
block, add:

```python
        conn.execute(
            "ALTER TABLE oauth_tokens ADD COLUMN IF NOT EXISTS calendar_id TEXT"
        )
```

Then add two new functions near `get_oauth_token`/`delete_oauth_token`:

```python
def get_calendar_id(user_id: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT calendar_id FROM oauth_tokens
            WHERE user_id = %s AND provider = 'calendar'
            """,
            (user_id,),
        ).fetchone()
    return row[0] if row is not None else None


def save_calendar_id(user_id: str, calendar_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE oauth_tokens SET calendar_id = %s
            WHERE user_id = %s AND provider = 'calendar'
            """,
            (calendar_id, user_id),
        )
        conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/data/test_db.py::test_save_and_get_calendar_id_roundtrip -v`
Expected: PASS

---

### Task 2: DB — `preferences.location_lat` / `location_lon`

**Files:**
- Modify: `data/db.py`
- Test: `tests/data/test_db.py`

**Interfaces:**
- Consumes: `Preferences` dataclass (Task 1's file, already defined).
- Produces: `Preferences.location_lat: float | None`, `Preferences.location_lon: float | None`;
  `upsert_preferences(..., location_lat: float | None = None, location_lon: float | None = None)`.

- [ ] **Step 1: Write the failing test**

```python
def test_upsert_preferences_stores_and_returns_location():
    user_id = find_or_create_user("runner@example.com", "google-sub-2", "Runner")

    result = db.upsert_preferences(user_id, location_lat=17.385, location_lon=78.4867)

    assert result.location_lat == 17.385
    assert result.location_lon == 78.4867

    fetched = db.get_preferences(user_id)
    assert fetched.location_lat == 17.385
    assert fetched.location_lon == 78.4867


def test_get_preferences_defaults_location_to_none():
    user_id = find_or_create_user("runner2@example.com", "google-sub-3", "Runner Two")
    assert db.get_preferences(user_id).location_lat is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/data/test_db.py -k location -v`
Expected: FAIL with `TypeError: upsert_preferences() got an unexpected keyword argument 'location_lat'`

- [ ] **Step 3: Implement**

In `data/db.py`:

```python
        conn.execute(
            "ALTER TABLE preferences ADD COLUMN IF NOT EXISTS location_lat DOUBLE PRECISION"
        )
        conn.execute(
            "ALTER TABLE preferences ADD COLUMN IF NOT EXISTS location_lon DOUBLE PRECISION"
        )
```

Update the `Preferences` dataclass:

```python
@dataclass
class Preferences:
    weekly_goal_km: float
    units: str
    notifications_enabled: bool
    language: str
    location_lat: float | None = None
    location_lon: float | None = None
```

`_DEFAULT_PREFERENCES` stays as-is (dataclass defaults cover the new fields as `None`).

Update `upsert_preferences`:

```python
def upsert_preferences(
    user_id: str,
    weekly_goal_km: float | None = None,
    units: str | None = None,
    notifications_enabled: bool | None = None,
    language: str | None = None,
    location_lat: float | None = None,
    location_lon: float | None = None,
) -> Preferences:
    current = get_preferences(user_id)
    weekly_goal_km = (
        current.weekly_goal_km if weekly_goal_km is None else weekly_goal_km
    )
    units = current.units if units is None else units
    notifications_enabled = (
        current.notifications_enabled
        if notifications_enabled is None
        else notifications_enabled
    )
    language = current.language if language is None else language
    location_lat = current.location_lat if location_lat is None else location_lat
    location_lon = current.location_lon if location_lon is None else location_lon

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO preferences
                (user_id, weekly_goal_km, units, notifications_enabled, language, location_lat, location_lon)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                weekly_goal_km = excluded.weekly_goal_km,
                units = excluded.units,
                notifications_enabled = excluded.notifications_enabled,
                language = excluded.language,
                location_lat = excluded.location_lat,
                location_lon = excluded.location_lon
            """,
            (user_id, weekly_goal_km, units, notifications_enabled, language, location_lat, location_lon),
        )
        conn.commit()
    return Preferences(
        weekly_goal_km=float(weekly_goal_km),
        units=units,
        notifications_enabled=notifications_enabled,
        language=language,
        location_lat=location_lat,
        location_lon=location_lon,
    )
```

Update `get_preferences`:

```python
def get_preferences(user_id: str) -> Preferences:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT weekly_goal_km, units, notifications_enabled, language, location_lat, location_lon
            FROM preferences WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return _DEFAULT_PREFERENCES
    weekly_goal_km, units, notifications_enabled, language, location_lat, location_lon = row
    return Preferences(
        weekly_goal_km=float(weekly_goal_km),
        units=units,
        notifications_enabled=notifications_enabled,
        language=language,
        location_lat=location_lat,
        location_lon=location_lon,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/data/test_db.py -k location -v`
Expected: PASS

---

### Task 3: `auth/auth.py` — generalize token refresh to any provider

**Files:**
- Modify: `auth/auth.py`
- Test: `tests/auth/test_auth.py`

**Interfaces:**
- Consumes: `get_connection` (`data/db.py`), `encrypt`/`decrypt` (`backend/encryption.py`).
- Produces: `get_valid_access_token(user_id: str, provider: str = "health") -> str`
  (existing call sites in `fit_server` keep working unchanged since `provider` defaults to
  `"health"`).

- [ ] **Step 1: Write the failing test**

Add to `tests/auth/test_auth.py`:

```python
def test_returns_stored_token_for_calendar_provider():
    import time

    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    save_oauth_token(
        user_id, "calendar", "calendar-access", "refresh-1", int(time.time()) + 3600
    )

    assert get_valid_access_token(user_id, provider="calendar") == "calendar-access"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/auth/test_auth.py::test_returns_stored_token_for_calendar_provider -v`
Expected: FAIL — `get_valid_access_token()` returns the `"health"` row (`None`/error), not
the calendar one, since `provider` isn't threaded through yet.

- [ ] **Step 3: Implement**

In `auth/auth.py`, replace the hardcoded `"health"` provider with a parameter:

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

        response = refresh_access_token(decrypt(refresh_token))
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

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/auth/test_auth.py -v`
Expected: PASS (all tests, including the two pre-existing ones — confirms the default
`provider="health"` didn't break `fit_server`'s call sites)

---

### Task 4: `backend/services/auth_service.py` — Calendar OAuth URL + exchange

**Files:**
- Modify: `backend/services/auth_service.py`
- Test: `tests/backend/services/test_auth_service.py` (new file)

**Interfaces:**
- Produces: `build_calendar_connect_url() -> str`,
  `exchange_code_for_calendar_tokens(code: str) -> dict`.

- [ ] **Step 1: Write the failing test**

Create `tests/backend/services/test_auth_service.py`:

```python
from unittest.mock import MagicMock, patch

from backend.services import auth_service


def test_build_calendar_connect_url_includes_calendar_scope():
    url = auth_service.build_calendar_connect_url()

    assert "calendar" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url


@patch("backend.services.auth_service.requests.post")
def test_exchange_code_for_calendar_tokens_posts_to_google(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {"access_token": "a", "refresh_token": "r", "expires_in": 3600}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    result = auth_service.exchange_code_for_calendar_tokens("some-code")

    assert result["access_token"] == "a"
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["data"]["code"] == "some-code"
    assert call_kwargs["data"]["grant_type"] == "authorization_code"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/services/test_auth_service.py -v`
Expected: FAIL with `AttributeError: module 'backend.services.auth_service' has no
attribute 'build_calendar_connect_url'`

- [ ] **Step 3: Implement**

Append to `backend/services/auth_service.py`:

```python
CALENDAR_SCOPE = (
    "https://www.googleapis.com/auth/calendar "
    "https://www.googleapis.com/auth/calendar.events"
)
CALENDAR_CALLBACK_URL = os.environ.get(
    "GOOGLE_CALENDAR_CALLBACK_URL", "http://localhost:8000/auth/calendar/callback"
)


def build_calendar_connect_url() -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": CALENDAR_CALLBACK_URL,
        "response_type": "code",
        "scope": CALENDAR_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        params
    )


def exchange_code_for_calendar_tokens(code: str) -> dict:
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": CALENDAR_CALLBACK_URL,
            "grant_type": "authorization_code",
        },
    )
    response.raise_for_status()
    return response.json()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backend/services/test_auth_service.py -v`
Expected: PASS

---

### Task 5: `backend/routes/auth.py` — Calendar connect/callback/disconnect routes

**Files:**
- Modify: `backend/routes/auth.py`
- Test: `tests/backend/routes/test_auth.py`

**Interfaces:**
- Consumes: `auth_service.build_calendar_connect_url`,
  `auth_service.exchange_code_for_calendar_tokens` (Task 4);
  `save_oauth_token`, `delete_oauth_token`, `get_oauth_token` (existing, `data/db.py`).
- Produces: `GET /auth/calendar/connect`, `GET /auth/calendar/callback`,
  `POST /auth/calendar/disconnect`; `/auth/me` response gains `calendar_connected: bool`.

- [ ] **Step 1: Write the failing test**

Add to `tests/backend/routes/test_auth.py` (follow that file's existing fixture/client
setup for the equivalent Health tests — reuse the same `client` fixture):

```python
def test_calendar_connect_redirects_to_google(client, logged_in_session):
    response = client.get("/auth/calendar/connect", follow_redirects=False)

    assert response.status_code == 307
    assert "accounts.google.com" in response.headers["location"]


def test_calendar_callback_saves_token_and_redirects(client, logged_in_session, monkeypatch):
    monkeypatch.setattr(
        "backend.routes.auth.auth_service.exchange_code_for_calendar_tokens",
        lambda code: {"access_token": "a", "refresh_token": "r", "expires_in": 3600},
    )

    response = client.get(
        "/auth/calendar/callback", params={"code": "abc"}, follow_redirects=False
    )

    assert response.status_code == 307
    from data.db import get_oauth_token

    assert get_oauth_token(logged_in_session["user_id"], "calendar") is not None


def test_me_reports_calendar_connected_false_by_default(client, logged_in_session):
    response = client.get("/auth/me")
    assert response.json()["calendar_connected"] is False
```

Adjust fixture names/shape to whatever `tests/backend/routes/test_auth.py` already uses
for its Health-flow tests (`logged_in_session`, `client`, etc.) — copy that file's
existing fixtures rather than reinventing them.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/routes/test_auth.py -k calendar -v`
Expected: FAIL with 404 (routes don't exist yet) / `KeyError: 'calendar_connected'`

- [ ] **Step 3: Implement**

In `backend/routes/auth.py`, add after the existing Health routes:

```python
@router.get("/calendar/connect")
def calendar_connect(session: str | None = Cookie(default=None)):
    _require_user_id(session)
    return RedirectResponse(auth_service.build_calendar_connect_url())


@router.get("/calendar/callback")
def calendar_callback(
    code: str | None = None,
    error: str | None = None,
    session: str | None = Cookie(default=None),
):
    user_id = _require_user_id(session)
    if error is not None:
        return RedirectResponse(f"{FRONTEND_URL}?calendar_connect_error=1")
    try:
        tokens = auth_service.exchange_code_for_calendar_tokens(code)
    except requests.HTTPError:
        return RedirectResponse(f"{FRONTEND_URL}?calendar_connect_error=1")

    expires_at = int(time.time()) + tokens["expires_in"]

    save_oauth_token(
        user_id,
        "calendar",
        tokens["access_token"],
        tokens["refresh_token"],
        expires_at,
    )
    return RedirectResponse(FRONTEND_URL)


@router.post("/calendar/disconnect")
def calendar_disconnect(session: str | None = Cookie(default=None)):
    user_id = _require_user_id(session)
    delete_oauth_token(user_id, "calendar")
    return {"status": "disconnected"}
```

Update the `me()` handler to add the new field:

```python
@router.get("/me")
def me(session: str | None = Cookie(default=None)):
    user_id = _require_user_id(session)
    email, name, created_at, avatar_path = get_user(user_id)
    health_token = get_oauth_token(user_id, "health")
    calendar_token = get_oauth_token(user_id, "calendar")

    avatar_url = create_signed_url(avatar_path) if avatar_path is not None else None
    return {
        "email": email,
        "name": name,
        "created_at": created_at,
        "avatar_url": avatar_url,
        "health_connected": health_token is not None,
        "calendar_connected": calendar_token is not None,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backend/routes/test_auth.py -v`
Expected: PASS (all, including pre-existing Health tests)

---

### Task 6: `calendar_server` — scaffold, auth, and calendar-creation helper

**Files:**
- Create: `mcp_servers/calendar_server/mcp_auth.py`
- Create: `mcp_servers/calendar_server/helpers/common.py`
- Create: `mcp_servers/calendar_server/helpers/calendar_api.py`
- Test: `tests/mcp_servers/calendar_server/helpers/test_calendar_api.py`

**Interfaces:**
- Produces: `ensure_calendar(access_token: str, user_id: str) -> str` (returns
  `calendar_id`, creating "Strides Runs" on Google + persisting via `save_calendar_id` if
  none stored yet).

- [ ] **Step 1: Copy auth scaffolding verbatim**

`mcp_servers/calendar_server/mcp_auth.py` — identical content to
`mcp_servers/fit_server/mcp_auth.py` (same JWKS URL, same `AUDIENCE = "strides-mcp"` — one
JWT signer already serves both servers, confirmed in `backend/jwt_issuer.py`, no change
needed there).

`mcp_servers/calendar_server/helpers/common.py` — identical content to
`mcp_servers/fit_server/helpers/common.py` (`current_user_id()`).

- [ ] **Step 2: Write the failing test for `ensure_calendar`**

Create `tests/mcp_servers/calendar_server/helpers/test_calendar_api.py`:

```python
from unittest.mock import patch

from mcp_servers.calendar_server.helpers.calendar_api import ensure_calendar


@patch("mcp_servers.calendar_server.helpers.calendar_api.save_calendar_id")
@patch("mcp_servers.calendar_server.helpers.calendar_api.get_calendar_id", return_value=None)
@patch("mcp_servers.calendar_server.helpers.calendar_api.requests.post")
def test_ensure_calendar_creates_when_none_stored(mock_post, mock_get, mock_save):
    mock_post.return_value.json.return_value = {"id": "new-cal-id"}
    mock_post.return_value.raise_for_status.return_value = None

    result = ensure_calendar("fake-token", "user-1")

    assert result == "new-cal-id"
    mock_post.assert_called_once()
    assert mock_post.call_args.kwargs["json"]["summary"] == "Strides Runs"
    mock_save.assert_called_once_with("user-1", "new-cal-id")


@patch("mcp_servers.calendar_server.helpers.calendar_api.save_calendar_id")
@patch("mcp_servers.calendar_server.helpers.calendar_api.get_calendar_id", return_value="existing-cal-id")
@patch("mcp_servers.calendar_server.helpers.calendar_api.requests.post")
def test_ensure_calendar_reuses_stored_id(mock_post, mock_get, mock_save):
    result = ensure_calendar("fake-token", "user-1")

    assert result == "existing-cal-id"
    mock_post.assert_not_called()
    mock_save.assert_not_called()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/mcp_servers/calendar_server/helpers/test_calendar_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_servers.calendar_server'`

- [ ] **Step 4: Implement**

Create `mcp_servers/calendar_server/helpers/calendar_api.py`:

```python
import requests

from data.db import get_calendar_id, save_calendar_id

BASE_URL = "https://www.googleapis.com/calendar/v3"


def ensure_calendar(access_token: str, user_id: str) -> str:
    """Return the user's dedicated 'Strides Runs' calendar ID, creating it on
    first use."""
    existing = get_calendar_id(user_id)
    if existing is not None:
        return existing

    response = requests.post(
        f"{BASE_URL}/calendars",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"summary": "Strides Runs"},
    )
    response.raise_for_status()
    calendar_id = response.json()["id"]
    save_calendar_id(user_id, calendar_id)
    return calendar_id
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/mcp_servers/calendar_server/helpers/test_calendar_api.py -v`
Expected: PASS

---

### Task 7: `calendar_server` — event CRUD helpers (list/create/update/delete)

**Files:**
- Modify: `mcp_servers/calendar_server/helpers/calendar_api.py`
- Test: `tests/mcp_servers/calendar_server/helpers/test_calendar_api.py`

**Interfaces:**
- Consumes: `ensure_calendar` (Task 6, same file).
- Produces: `list_events(access_token, calendar_id, time_min, time_max) -> list[dict]`,
  `create_event(access_token, calendar_id, title, start_time, duration_minutes, notes) -> dict`,
  `update_event(access_token, calendar_id, event_id, **fields) -> dict`,
  `delete_event(access_token, calendar_id, event_id) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/mcp_servers/calendar_server/helpers/test_calendar_api.py`:

```python
from datetime import timedelta

from mcp_servers.calendar_server.helpers.calendar_api import (
    create_event,
    delete_event,
    list_events,
    update_event,
)


@patch("mcp_servers.calendar_server.helpers.calendar_api.requests.get")
def test_list_events_queries_the_given_calendar(mock_get):
    mock_get.return_value.json.return_value = {"items": [{"id": "e1", "summary": "Easy 5K"}]}
    mock_get.return_value.raise_for_status.return_value = None

    result = list_events("token", "cal-1", "2026-08-22T00:00:00Z", "2026-08-29T00:00:00Z")

    assert result == [{"id": "e1", "summary": "Easy 5K"}]
    called_url = mock_get.call_args.args[0]
    assert "cal-1" in called_url


@patch("mcp_servers.calendar_server.helpers.calendar_api.requests.post")
def test_create_event_posts_start_and_end_time(mock_post):
    mock_post.return_value.json.return_value = {"id": "e2", "summary": "Tempo run"}
    mock_post.return_value.raise_for_status.return_value = None

    result = create_event(
        "token", "cal-1", "Tempo run", "2026-08-25T07:00:00", 45, "Race pace effort"
    )

    assert result["id"] == "e2"
    body = mock_post.call_args.kwargs["json"]
    assert body["summary"] == "Tempo run"
    assert body["description"] == "Race pace effort"
    assert body["start"]["dateTime"] == "2026-08-25T07:00:00"
    assert body["end"]["dateTime"] == "2026-08-25T07:45:00"


@patch("mcp_servers.calendar_server.helpers.calendar_api.requests.patch")
def test_update_event_patches_given_fields(mock_patch):
    mock_patch.return_value.json.return_value = {"id": "e2", "summary": "Renamed"}
    mock_patch.return_value.raise_for_status.return_value = None

    result = update_event("token", "cal-1", "e2", summary="Renamed")

    assert result["summary"] == "Renamed"
    assert mock_patch.call_args.kwargs["json"] == {"summary": "Renamed"}


@patch("mcp_servers.calendar_server.helpers.calendar_api.requests.delete")
def test_delete_event_calls_delete_endpoint(mock_delete):
    mock_delete.return_value.raise_for_status.return_value = None

    delete_event("token", "cal-1", "e2")

    assert "cal-1" in mock_delete.call_args.args[0]
    assert "e2" in mock_delete.call_args.args[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp_servers/calendar_server/helpers/test_calendar_api.py -v`
Expected: FAIL with `ImportError: cannot import name 'create_event'`

- [ ] **Step 3: Implement**

Append to `mcp_servers/calendar_server/helpers/calendar_api.py`:

```python
from datetime import datetime, timedelta


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def list_events(
    access_token: str, calendar_id: str, time_min: str, time_max: str
) -> list[dict]:
    response = requests.get(
        f"{BASE_URL}/calendars/{calendar_id}/events",
        headers=_headers(access_token),
        params={
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime",
        },
    )
    response.raise_for_status()
    return response.json().get("items", [])


def create_event(
    access_token: str,
    calendar_id: str,
    title: str,
    start_time: str,
    duration_minutes: int,
    notes: str = "",
) -> dict:
    start = datetime.fromisoformat(start_time)
    end = start + timedelta(minutes=duration_minutes)

    response = requests.post(
        f"{BASE_URL}/calendars/{calendar_id}/events",
        headers=_headers(access_token),
        json={
            "summary": title,
            "description": notes,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        },
    )
    response.raise_for_status()
    return response.json()


def update_event(access_token: str, calendar_id: str, event_id: str, **fields) -> dict:
    response = requests.patch(
        f"{BASE_URL}/calendars/{calendar_id}/events/{event_id}",
        headers=_headers(access_token),
        json=fields,
    )
    response.raise_for_status()
    return response.json()


def delete_event(access_token: str, calendar_id: str, event_id: str) -> None:
    response = requests.delete(
        f"{BASE_URL}/calendars/{calendar_id}/events/{event_id}",
        headers=_headers(access_token),
    )
    response.raise_for_status()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp_servers/calendar_server/helpers/test_calendar_api.py -v`
Expected: PASS

---

### Task 8: `calendar_server` — MCP tools + FastMCP app

**Files:**
- Create: `mcp_servers/calendar_server/server.py`
- Test: `tests/mcp_servers/calendar_server/test_server.py`

**Interfaces:**
- Consumes: `current_user_id` (Task 6), `get_valid_access_token(user_id, provider="calendar")`
  (Task 3), `ensure_calendar`, `list_events`, `create_event`, `update_event`, `delete_event`
  (Tasks 6–7), `verify_bearer_token` (Task 6's `mcp_auth.py`).
- Produces: MCP tools `list_upcoming_runs`, `create_run_event`, `update_run_event`,
  `delete_run_event` (importable as `server.list_upcoming_runs` etc. for testing, same
  pattern as `fit_server.server`).

- [ ] **Step 1: Write the failing tests**

Create `tests/mcp_servers/calendar_server/test_server.py`:

```python
from unittest.mock import patch

from mcp_servers.calendar_server import server


@patch("mcp_servers.calendar_server.server.list_events", return_value=[{"id": "e1", "summary": "Easy 5K"}])
@patch("mcp_servers.calendar_server.server.ensure_calendar", return_value="cal-1")
@patch("mcp_servers.calendar_server.server.get_valid_access_token", return_value="fake-token")
@patch("mcp_servers.calendar_server.server.current_user_id", return_value="user-1")
def test_list_upcoming_runs_returns_events(mock_uid, mock_token, mock_ensure, mock_list):
    result = server.list_upcoming_runs(days_ahead=7)

    assert result == [{"id": "e1", "summary": "Easy 5K"}]
    mock_list.assert_called_once()
    assert mock_list.call_args.args[1] == "cal-1"


@patch("mcp_servers.calendar_server.server.create_event", return_value={"id": "e2"})
@patch("mcp_servers.calendar_server.server.ensure_calendar", return_value="cal-1")
@patch("mcp_servers.calendar_server.server.get_valid_access_token", return_value="fake-token")
@patch("mcp_servers.calendar_server.server.current_user_id", return_value="user-1")
def test_create_run_event_creates_on_dedicated_calendar(mock_uid, mock_token, mock_ensure, mock_create):
    result = server.create_run_event(
        title="Tempo run",
        start_time="2026-08-25T07:00:00",
        duration_minutes=45,
        notes="Race pace",
    )

    assert result == {"id": "e2"}
    mock_create.assert_called_once_with(
        "fake-token", "cal-1", "Tempo run", "2026-08-25T07:00:00", 45, "Race pace"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp_servers/calendar_server/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_servers.calendar_server.server'`

- [ ] **Step 3: Implement**

Create `mcp_servers/calendar_server/server.py`:

```python
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from auth.auth import get_valid_access_token
from logging_config import setup_logging
from mcp_servers.calendar_server.helpers.calendar_api import (
    create_event,
    delete_event,
    ensure_calendar,
    list_events,
    update_event,
)
from mcp_servers.calendar_server.helpers.common import current_user_id
from mcp_servers.calendar_server.mcp_auth import verify_bearer_token

setup_logging()


class StridesTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            user_id = verify_bearer_token(token)
        except Exception:
            return None
        return AccessToken(
            token=token, client_id="strides-backend", scopes=[], subject=user_id
        )


mcp = FastMCP(
    "strides-calendar",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8002)),
    token_verifier=StridesTokenVerifier(),
    auth=AuthSettings(
        issuer_url="http://localhost:8000",
        resource_server_url="http://localhost:8002",
    ),
)


@mcp.tool()
def list_upcoming_runs(days_ahead: int = 7) -> list[dict[str, Any]]:
    """List planned runs from the user's dedicated 'Strides Runs' Google Calendar
    for the next N days (default 7). Returns raw Calendar event dicts (empty list
    if none scheduled, not an error)."""
    user_id = current_user_id()
    access_token = get_valid_access_token(user_id, provider="calendar")
    calendar_id = ensure_calendar(access_token, user_id)

    now = datetime.now(timezone.utc)
    time_min = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_max = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ")

    return list_events(access_token, calendar_id, time_min, time_max)


@mcp.tool()
def create_run_event(
    title: str, start_time: str, duration_minutes: int, notes: str = ""
) -> dict[str, Any]:
    """Create a planned run on the user's dedicated 'Strides Runs' Google Calendar.
    Only call this after the user has explicitly confirmed a proposed plan — never
    schedule proactively without confirmation. start_time is an ISO 8601 local
    datetime, e.g. '2026-08-25T07:00:00'."""
    user_id = current_user_id()
    access_token = get_valid_access_token(user_id, provider="calendar")
    calendar_id = ensure_calendar(access_token, user_id)

    return create_event(access_token, calendar_id, title, start_time, duration_minutes, notes)


@mcp.tool()
def update_run_event(event_id: str, **fields: Any) -> dict[str, Any]:
    """Update a planned run (e.g. reschedule) on the user's dedicated Calendar.
    fields are any Google Calendar event fields to patch, e.g. summary, start, end."""
    user_id = current_user_id()
    access_token = get_valid_access_token(user_id, provider="calendar")
    calendar_id = ensure_calendar(access_token, user_id)

    return update_event(access_token, calendar_id, event_id, **fields)


@mcp.tool()
def delete_run_event(event_id: str) -> dict[str, str]:
    """Cancel a planned run by deleting its Calendar event."""
    user_id = current_user_id()
    access_token = get_valid_access_token(user_id, provider="calendar")
    calendar_id = ensure_calendar(access_token, user_id)

    delete_event(access_token, calendar_id, event_id)
    return {"status": "deleted"}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp_servers/calendar_server/test_server.py -v`
Expected: PASS

---

### Task 9: `calendar_server` — Dockerfile

**Files:**
- Create: `mcp_servers/calendar_server/Dockerfile`

**Interfaces:** none (deployment artifact only).

- [ ] **Step 1: Look at the existing `fit_server` Dockerfile**

Read `mcp_servers/fit_server/Dockerfile` for the exact base image, `uv sync` invocation,
and `CMD` pattern used.

- [ ] **Step 2: Create `mcp_servers/calendar_server/Dockerfile`**

Copy `mcp_servers/fit_server/Dockerfile` content, changing only the final `CMD`/entrypoint
module path from `mcp_servers.fit_server.server` to `mcp_servers.calendar_server.server`
(and the exposed `PORT` default if the original hardcodes `8001` anywhere — use `8002` to
match Task 8's default).

- [ ] **Step 3: Build locally to confirm it builds**

Run: `docker build -f mcp_servers/calendar_server/Dockerfile -t calendar-server-test .`
Expected: build succeeds with no errors.

---

### Task 10: `weather_service.py` — Open-Meteo wrapper

**Files:**
- Create: `backend/services/weather_service.py`
- Test: `tests/backend/services/test_weather_service.py`

**Interfaces:**
- Produces: `async get_forecast(lat: float, lon: float, date: str) -> dict | None`,
  `async get_current_conditions(lat: float, lon: float) -> dict`,
  `async get_air_quality(lat: float, lon: float) -> dict`.

- [ ] **Step 1: Write the failing tests**

Create `tests/backend/services/test_weather_service.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest

from backend.services import weather_service


@pytest.mark.asyncio
@patch("backend.services.weather_service.httpx.AsyncClient.get")
async def test_get_forecast_returns_temp_and_condition_for_date(mock_get):
    mock_response = AsyncMock()
    mock_response.json = lambda: {
        "daily": {
            "time": ["2026-08-25"],
            "temperature_2m_max": [22.0],
            "weathercode": [0],
        }
    }
    mock_response.raise_for_status = lambda: None
    mock_get.return_value = mock_response

    result = await weather_service.get_forecast(17.385, 78.4867, "2026-08-25")

    assert result == {"temp": 22.0, "condition": "clear"}


@pytest.mark.asyncio
@patch("backend.services.weather_service.httpx.AsyncClient.get")
async def test_get_forecast_returns_none_when_date_not_in_response(mock_get):
    mock_response = AsyncMock()
    mock_response.json = lambda: {"daily": {"time": [], "temperature_2m_max": [], "weathercode": []}}
    mock_response.raise_for_status = lambda: None
    mock_get.return_value = mock_response

    result = await weather_service.get_forecast(17.385, 78.4867, "2026-09-30")

    assert result is None


@pytest.mark.asyncio
@patch("backend.services.weather_service.httpx.AsyncClient.get")
async def test_get_current_conditions_maps_fields(mock_get):
    mock_response = AsyncMock()
    mock_response.json = lambda: {
        "current": {
            "temperature_2m": 27.0,
            "apparent_temperature": 30.0,
            "relative_humidity_2m": 74,
            "wind_speed_10m": 9.0,
            "weathercode": 1,
        },
        "hourly": {"time": ["2026-08-21T18:00"], "temperature_2m": [28.0]},
    }
    mock_response.raise_for_status = lambda: None
    mock_get.return_value = mock_response

    result = await weather_service.get_current_conditions(17.385, 78.4867)

    assert result["temp"] == 27.0
    assert result["feels_like"] == 30.0
    assert result["humidity"] == 74
    assert result["wind"] == 9.0
    assert result["condition"] == "partly cloudy"


@pytest.mark.asyncio
@patch("backend.services.weather_service.httpx.AsyncClient.get")
async def test_get_air_quality_returns_aqi(mock_get):
    mock_response = AsyncMock()
    mock_response.json = lambda: {"current": {"us_aqi": 42}}
    mock_response.raise_for_status = lambda: None
    mock_get.return_value = mock_response

    result = await weather_service.get_air_quality(17.385, 78.4867)

    assert result == {"aqi": 42}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/services/test_weather_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.weather_service'`

- [ ] **Step 3: Implement**

Create `backend/services/weather_service.py`:

```python
import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

_WEATHER_CODES = {
    0: "clear",
    1: "partly cloudy",
    2: "partly cloudy",
    3: "cloudy",
    45: "fog",
    48: "fog",
    51: "drizzle",
    61: "rain",
    63: "rain",
    65: "rain",
    71: "snow",
    73: "snow",
    75: "snow",
    80: "showers",
    95: "storm",
}


def _condition_from_code(code: int) -> str:
    return _WEATHER_CODES.get(code, "unknown")


async def get_forecast(lat: float, lon: float, date: str) -> dict | None:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,weathercode",
                "start_date": date,
                "end_date": date,
                "timezone": "auto",
            },
        )
        response.raise_for_status()
        data = response.json()

    times = data["daily"]["time"]
    if date not in times:
        return None

    index = times.index(date)
    return {
        "temp": data["daily"]["temperature_2m_max"][index],
        "condition": _condition_from_code(data["daily"]["weathercode"][index]),
    }


async def get_current_conditions(lat: float, lon: float) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weathercode",
                "hourly": "temperature_2m",
                "timezone": "auto",
            },
        )
        response.raise_for_status()
        data = response.json()

    current = data["current"]
    return {
        "temp": current["temperature_2m"],
        "feels_like": current["apparent_temperature"],
        "humidity": current["relative_humidity_2m"],
        "wind": current["wind_speed_10m"],
        "condition": _condition_from_code(current["weathercode"]),
        "hourly": data["hourly"],
    }


async def get_air_quality(lat: float, lon: float) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            AIR_QUALITY_URL,
            params={"latitude": lat, "longitude": lon, "current": "us_aqi"},
        )
        response.raise_for_status()
        data = response.json()

    return {"aqi": data["current"]["us_aqi"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backend/services/test_weather_service.py -v`
Expected: PASS

---

### Task 11: `backend/routes/calendar.py` — "Plan a run" quick-add endpoint

**Files:**
- Create: `backend/routes/calendar.py`
- Modify: wherever routers are mounted (check `backend/main.py` for the
  `app.include_router(...)` calls and add this one alongside `dashboard`/`preferences`).
- Test: `tests/backend/routes/test_calendar.py`

**Interfaces:**
- Consumes: `require_user` (`backend/dependencies.py`), `open_mcp_session` generalized in
  Task 12 — **write this task's test with `open_mcp_session` mocked at the module level so
  it doesn't depend on Task 12's signature change landing first**; wire the real
  multi-server call in Task 12.

- [ ] **Step 1: Write the failing test**

Create `tests/backend/routes/test_calendar.py` (mirror `tests/backend/routes/test_preferences.py`'s
client/session-cookie fixture setup):

```python
from unittest.mock import AsyncMock, MagicMock, patch


def test_plan_run_creates_calendar_event(client, logged_in_session):
    fake_session = AsyncMock()
    fake_session.call_tool.return_value = MagicMock(
        structuredContent={"id": "e1", "summary": "Easy 5K"}
    )

    with patch("backend.routes.calendar.open_mcp_session") as mock_open:
        mock_open.return_value.__aenter__.return_value = fake_session
        response = client.post(
            "/calendar/events",
            json={
                "title": "Easy 5K",
                "start_time": "2026-08-25T07:00:00",
                "duration_minutes": 30,
                "notes": "",
            },
        )

    assert response.status_code == 200
    fake_session.call_tool.assert_called_once_with(
        "create_run_event",
        {
            "title": "Easy 5K",
            "start_time": "2026-08-25T07:00:00",
            "duration_minutes": 30,
            "notes": "",
        },
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/routes/test_calendar.py -v`
Expected: FAIL with 404 (route/module doesn't exist)

- [ ] **Step 3: Implement**

Create `backend/routes/calendar.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.dependencies import require_user
from backend.services.mcp_client import open_mcp_session

router = APIRouter(prefix="/calendar")


class PlanRunRequest(BaseModel):
    title: str
    start_time: str
    duration_minutes: int
    notes: str = ""


@router.post("/events")
async def plan_run(body: PlanRunRequest, user_id: str = Depends(require_user)):
    async with open_mcp_session(user_id) as session:
        result = await session.call_tool(
            "create_run_event",
            {
                "title": body.title,
                "start_time": body.start_time,
                "duration_minutes": body.duration_minutes,
                "notes": body.notes,
            },
        )
    return result.structuredContent
```

Register it: find where `dashboard.router`/`preferences.router` are included (search
`backend/main.py` for `include_router`) and add
`app.include_router(calendar.router)` with the matching import, same pattern as the
existing routers.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backend/routes/test_calendar.py -v`
Expected: PASS

---

### Task 12: `mcp_client.py` — support multiple MCP servers

**Files:**
- Modify: `backend/services/mcp_client.py`
- Test: `tests/backend/services/test_mcp_client.py` (new file; check if one already exists
  under `tests/backend/` — if so, extend it instead of creating a duplicate)

**Interfaces:**
- Produces: `open_mcp_session(user_id: str, server_url: str = SERVER_URL)` (existing
  callers — `dashboard.py`, `chat_service.py`, Task 11's `calendar.py` — keep working
  unchanged via the default; Task 13 passes `CALENDAR_SERVER_URL` explicitly).
- New constant: `CALENDAR_SERVER_URL = os.environ.get("CALENDAR_MCP_SERVER_URL", "http://127.0.0.1:8002/mcp")`.

- [ ] **Step 1: Write the failing test**

Create `tests/backend/services/test_mcp_client.py`:

```python
import inspect

from backend.services.mcp_client import CALENDAR_SERVER_URL, open_mcp_session


def test_open_mcp_session_accepts_a_server_url_override():
    params = inspect.signature(open_mcp_session).parameters
    assert "server_url" in params


def test_calendar_server_url_has_a_default():
    assert CALENDAR_SERVER_URL.endswith("/mcp")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/services/test_mcp_client.py -v`
Expected: FAIL — `open_mcp_session` has no `server_url` parameter yet;
`CALENDAR_SERVER_URL` doesn't exist.

- [ ] **Step 3: Implement**

In `backend/services/mcp_client.py`, add the new constant and generalize the function
signature (keep the existing error message wording pattern, just parameterize the URL):

```python
SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")
CALENDAR_SERVER_URL = os.environ.get(
    "CALENDAR_MCP_SERVER_URL", "http://127.0.0.1:8002/mcp"
)


@asynccontextmanager
async def open_mcp_session(user_id: str, server_url: str = SERVER_URL):
    """Open a fresh, per-caller MCP session authenticated as user_id.

    Short-lived by design, matching the 5-minute JWT it mints — a cached,
    long-lived session couldn't carry a fresh token per request anyway."""
    token = mint_token(user_id)
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http_client:
        try:
            async with streamable_http_client(server_url, http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        except* httpx.ConnectError as eg:
            raise HTTPException(
                status_code=503,
                detail=f"A data service is unavailable — is the MCP server running on {server_url}?",
            ) from eg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backend/services/test_mcp_client.py -v`
Expected: PASS. Also run the full existing suite to confirm no regressions:
`uv run pytest tests/backend -v`

---

### Task 13: `chat_service.py` — dual MCP sessions + `get_weather` local tool

**Files:**
- Modify: `backend/services/chat_service.py`
- Test: `tests/backend/services/test_chat_service.py`

**Interfaces:**
- Consumes: `open_mcp_session(user_id, server_url)` (Task 12),
  `weather_service.get_forecast`/`get_current_conditions` (Task 10),
  `data.db.get_preferences` (Task 2, for location).
- Produces: `LOCAL_TOOL_SCHEMAS` gains a `get_weather` entry; `LOCAL_TOOLS["get_weather"]`;
  `process_query` opens both the Health and Calendar MCP sessions and merges their tool
  schemas; `call_tools` routes each `tool_use` block to whichever session actually owns
  that tool name.

- [ ] **Step 1: Write the failing tests**

Add to `tests/backend/services/test_chat_service.py` (check the existing file's fixtures
for how `process_query`/`call_tools` are already tested — likely with a fake
`ClientSession`; follow that pattern):

```python
import pytest
from unittest.mock import AsyncMock, patch

from backend.services import chat_service


@pytest.mark.asyncio
async def test_get_weather_tool_uses_stored_location():
    with patch("backend.services.chat_service.db.get_preferences") as mock_prefs, \
         patch("backend.services.chat_service.weather_service.get_current_conditions") as mock_weather:
        mock_prefs.return_value.location_lat = 17.385
        mock_prefs.return_value.location_lon = 78.4867
        mock_weather.return_value = {"temp": 27, "condition": "clear"}

        result = await chat_service._get_weather("user-1")

    mock_weather.assert_called_once_with(17.385, 78.4867)
    assert "27" in result or "clear" in result


@pytest.mark.asyncio
async def test_call_tools_routes_to_calendar_session_for_calendar_tool_names():
    health_session = AsyncMock()
    calendar_session = AsyncMock()
    calendar_session.call_tool.return_value = AsyncMock(__str__=lambda self: "ok")

    block = AsyncMock()
    block.type = "tool_use"
    block.name = "create_run_event"
    block.input = {"title": "Easy 5K"}
    block.id = "tool-1"

    sessions_by_tool = {"create_run_event": calendar_session}

    results = await chat_service.call_tools(
        "user-1", health_session, [block], sessions_by_tool=sessions_by_tool
    )

    calendar_session.call_tool.assert_called_once_with("create_run_event", {"title": "Easy 5K"})
    health_session.call_tool.assert_not_called()
    assert results[0]["tool_use_id"] == "tool-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/services/test_chat_service.py -v`
Expected: FAIL — `AttributeError: module 'backend.services.chat_service' has no attribute
'_get_weather'`, and `call_tools() got an unexpected keyword argument 'sessions_by_tool'`

- [ ] **Step 3: Implement**

In `backend/services/chat_service.py`, add the import and local tool:

```python
from backend.services import weather_service
from backend.services.mcp_client import CALENDAR_SERVER_URL, get_tool_schemas, open_mcp_session
```

Add to `LOCAL_TOOL_SCHEMAS`:

```python
    {
        "name": "get_weather",
        "description": (
            "Get the current weather conditions (temperature, condition, "
            "humidity, wind) at the user's stored location. Use this when "
            "reasoning about whether/how to plan an upcoming run."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
```

Add the handler and register it:

```python
async def _get_weather(user_id: str) -> str:
    prefs = db.get_preferences(user_id)
    if prefs.location_lat is None or prefs.location_lon is None:
        return "No location set for this user — ask them to set one in their profile."
    conditions = await weather_service.get_current_conditions(
        prefs.location_lat, prefs.location_lon
    )
    return (
        f"{conditions['temp']}°C, {conditions['condition']}, "
        f"feels like {conditions['feels_like']}°C, humidity {conditions['humidity']}%, "
        f"wind {conditions['wind']} km/h"
    )


LOCAL_TOOLS: dict = {"save_memory": _save_memory, "get_weather": _get_weather}
```

Update `call_tools` to accept an optional per-tool session map, falling back to the
default `session` for anything not in it (this keeps the existing single-session callers —
if any exist beyond `process_query` — working unchanged):

```python
async def call_tools(user_id, session, content_blocks, sessions_by_tool: dict | None = None):
    """Execute every tool_use block and return their results as tool_result blocks."""
    sessions_by_tool = sessions_by_tool or {}
    tool_results = []
    for block in content_blocks:
        if block.type == "tool_use":
            with langfuse_client.start_as_current_observation(
                as_type="tool", name=block.name, input=block.input
            ) as tool_obs:
                try:
                    if block.name in LOCAL_TOOLS:
                        result = await LOCAL_TOOLS[block.name](user_id, **block.input)
                    else:
                        target_session = sessions_by_tool.get(block.name, session)
                        result = await target_session.call_tool(block.name, block.input)
                    content = str(result)
                    if len(content) > MAX_TOOL_RESULT_CHARS:
                        content = content[:MAX_TOOL_RESULT_CHARS] + "... [truncated]"
                except Exception as e:
                    logger.exception(
                        "Tool call failed: %s(%s)", block.name, block.input
                    )
                    content = f"Tool error: {e}"
                    tool_obs.update(level="ERROR", status_message=str(e))

                tool_obs.update(output=content)

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                }
            )

    return tool_results
```

Update `process_query` to open both sessions and build the routing map (replace the
existing `async with open_mcp_session(user_id) as session:` block):

```python
        async with (
            open_mcp_session(user_id) as health_session,
            open_mcp_session(user_id, server_url=CALENDAR_SERVER_URL) as calendar_session,
        ):
            health_tools = await get_tool_schemas(health_session)
            calendar_tools = await get_tool_schemas(calendar_session)
            tools = health_tools + calendar_tools + LOCAL_TOOL_SCHEMAS
            sessions_by_tool = {t["name"]: calendar_session for t in calendar_tools}
```

(the rest of `process_query`'s loop body is unchanged, except every call to
`call_tools(user_id, session, response.content)` becomes
`call_tools(user_id, health_session, response.content, sessions_by_tool=sessions_by_tool)`
— `health_session` is the default fallback for any tool not in the calendar map.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backend/services/test_chat_service.py -v`
Expected: PASS. Also run `uv run pytest tests/backend -v` for regressions.

---

### Task 14: `backend/agent.py` — system prompt guidance

**Files:**
- Modify: `backend/agent.py`

**Interfaces:** none (prompt text only, no new function signatures).

- [ ] **Step 1: Read the current `SYSTEM_PROMPT`**

Read `backend/agent.py` to find the existing prompt text and its section for `save_memory`
guidance, to match tone/structure.

- [ ] **Step 2: Add a paragraph on Calendar + weather planning**

Append to `SYSTEM_PROMPT` (exact wording is a judgment call — write in the same voice as
existing sections), covering:
- Use `get_weather` and `list_upcoming_runs`/recent Health data when a user asks for a
  run plan.
- Only call `create_run_event`/`update_run_event`/`delete_run_event` after the user has
  explicitly confirmed a specific proposed plan — never schedule proactively.
- Consider forecast conditions (heat, rain) when suggesting when/what type of run.

- [ ] **Step 3: Manually verify via the chat endpoint**

Since this is prompt text with no unit-testable behavior, verify manually: start the
backend + both MCP servers locally, connect Health and Calendar for a test user, ask the
chat agent "plan my runs for this week" and confirm it calls `get_weather` and
`list_upcoming_runs` before proposing anything, and does not call `create_run_event`
without an explicit confirmation turn.

---

### Task 15: `backend/routes/dashboard.py` — upcoming runs + current weather

**Files:**
- Modify: `backend/routes/dashboard.py`
- Test: `tests/backend/routes/test_dashboard.py`

**Interfaces:**
- Consumes: `CALENDAR_SERVER_URL`, `open_mcp_session` (Task 12),
  `weather_service.get_forecast`/`get_current_conditions`/`get_air_quality` (Task 10),
  `get_preferences` (Task 2), `get_oauth_token` (existing).
- Produces: `GET /dashboard` response gains `upcoming_runs: list[dict]`,
  `calendar_connected: bool`, `current_weather: dict | None`.

- [ ] **Step 1: Write the failing test**

Add to `tests/backend/routes/test_dashboard.py` (follow that file's existing pattern for
mocking `open_mcp_session`/health calls):

```python
from unittest.mock import AsyncMock, MagicMock, patch


def test_dashboard_includes_upcoming_runs_when_calendar_connected(client, logged_in_session):
    fake_calendar_session = AsyncMock()
    fake_calendar_session.call_tool.return_value = MagicMock(
        structuredContent=[{"id": "e1", "summary": "Easy 5K", "start": {"dateTime": "2026-08-25T07:00:00"}}]
    )

    with patch("backend.routes.dashboard.get_oauth_token", return_value=("a", "r", 999999999)), \
         patch("backend.routes.dashboard.open_mcp_session") as mock_open, \
         patch("backend.routes.dashboard.weather_service.get_forecast", new=AsyncMock(return_value=None)), \
         patch("backend.routes.dashboard.weather_service.get_current_conditions", new=AsyncMock(return_value=None)), \
         patch("backend.routes.dashboard.weather_service.get_air_quality", new=AsyncMock(return_value=None)):
        mock_open.return_value.__aenter__.return_value = fake_calendar_session
        response = client.get("/dashboard")

    body = response.json()
    assert body["calendar_connected"] is True
    assert body["upcoming_runs"][0]["summary"] == "Easy 5K"


def test_dashboard_omits_upcoming_runs_when_calendar_not_connected(client, logged_in_session):
    with patch("backend.routes.dashboard.get_oauth_token", return_value=None):
        response = client.get("/dashboard")

    body = response.json()
    assert body["calendar_connected"] is False
    assert body["upcoming_runs"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/routes/test_dashboard.py -v`
Expected: FAIL — `KeyError: 'calendar_connected'` / `'upcoming_runs'`

- [ ] **Step 3: Implement**

Modify `backend/routes/dashboard.py`:

```python
from fastapi import APIRouter, Depends

from backend.dependencies import require_user
from backend.services import weather_service
from backend.services.mcp_client import CALENDAR_SERVER_URL, open_mcp_session
from data.db import get_oauth_token, get_preferences

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

    calendar_connected = get_oauth_token(user_id, "calendar") is not None
    upcoming_runs = []
    current_weather = None
    prefs = get_preferences(user_id)

    if calendar_connected:
        try:
            async with open_mcp_session(user_id, server_url=CALENDAR_SERVER_URL) as session:
                result = await session.call_tool("list_upcoming_runs", {"days_ahead": 7})
            events = result.structuredContent or []

            for event in events:
                forecast = None
                if prefs.location_lat is not None and prefs.location_lon is not None:
                    start = event.get("start", {}).get("dateTime", "")
                    date = start[:10] if start else None
                    if date:
                        forecast = await weather_service.get_forecast(
                            prefs.location_lat, prefs.location_lon, date
                        )
                upcoming_runs.append({**event, "forecast": forecast})
        except Exception:
            calendar_connected = False

    if prefs.location_lat is not None and prefs.location_lon is not None:
        try:
            conditions = await weather_service.get_current_conditions(
                prefs.location_lat, prefs.location_lon
            )
            air_quality = await weather_service.get_air_quality(
                prefs.location_lat, prefs.location_lon
            )
            current_weather = {**conditions, **air_quality}
        except Exception:
            current_weather = None

    return {
        "weekly_stats": weekly_stats,
        "recent_runs": recent_runs,
        "health_connected": health_connected,
        "health_error": health_error,
        "calendar_connected": calendar_connected,
        "upcoming_runs": upcoming_runs,
        "current_weather": current_weather,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backend/routes/test_dashboard.py -v`
Expected: PASS

---

### Task 16: `backend/routes/preferences.py` — location field

**Files:**
- Modify: `backend/routes/preferences.py`
- Test: `tests/backend/routes/test_preferences.py`

**Interfaces:**
- Consumes: `upsert_preferences(..., location_lat, location_lon)` (Task 2).

- [ ] **Step 1: Write the failing test**

Add to `tests/backend/routes/test_preferences.py`:

```python
def test_write_preferences_accepts_location(client, logged_in_session):
    response = client.put(
        "/preferences", json={"location_lat": 17.385, "location_lon": 78.4867}
    )

    assert response.status_code == 200
    assert response.json()["location_lat"] == 17.385
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/routes/test_preferences.py -v`
Expected: FAIL — `422 Unprocessable Entity` (unknown fields) or missing key in response

- [ ] **Step 3: Implement**

In `backend/routes/preferences.py`:

```python
class PreferencesUpdate(BaseModel):
    weekly_goal_km: float | None = None
    units: str | None = None
    notifications_enabled: bool | None = None
    language: str | None = None
    location_lat: float | None = None
    location_lon: float | None = None


@router.put("")
def write_preferences(body: PreferencesUpdate, user_id: str = Depends(require_user)):
    return upsert_preferences(
        user_id,
        weekly_goal_km=body.weekly_goal_km,
        units=body.units,
        notifications_enabled=body.notifications_enabled,
        language=body.language,
        location_lat=body.location_lat,
        location_lon=body.location_lon,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backend/routes/test_preferences.py -v`
Expected: PASS

---

### Task 17: CI — deploy `calendar_server`

**Files:**
- Modify: `.github/workflows/deploy.yml`

**Interfaces:** none (CI config only).

- [ ] **Step 1: Add the new job**

In `.github/workflows/deploy.yml`, add a `deploy-calendar-server` job, copied from
`deploy-mcp-server` with these changes: build context stays repo root, `-f
mcp_servers/calendar_server/Dockerfile`, image tag `${{ env.REPO }}/calendar-server:${{
github.sha }}`, `gcloud run deploy calendar-server`, and env vars
`DATABASE_URL,TOKEN_ENCRYPTION_KEY,GOOGLE_CLIENT_ID,GOOGLE_CLIENT_SECRET,STRIDES_JWKS_URL`
(identical set to `deploy-mcp-server` — same JWKS/signing setup, same DB, same OAuth
client).

Add `mcp_servers/calendar_server/**` to the top-level `paths:` trigger list, alongside the
existing `mcp_servers/fit_server/**`.

Add `CALENDAR_MCP_SERVER_URL` (pointing at the new Cloud Run service's URL, once known post
first-deploy) to the `deploy-backend` job's `--set-env-vars`, alongside the existing
`MCP_SERVER_URL`.

- [ ] **Step 2: Confirm YAML is well-formed**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))"`
Expected: no error.

Note: this task needs a follow-up manual step outside this plan — after first deploy,
retrieve the new service's URL from Cloud Run and set it as the `CALENDAR_MCP_SERVER_URL`
GitHub secret (mirroring how `MCP_SERVER_URL` was set per the GCP deployment plan's
troubleshooting notes), then add the calendar OAuth client redirect URI
(`https://backend-.../auth/calendar/callback`) in Google Cloud Console, same as was done
for `GOOGLE_HEALTH_CALLBACK_URL`.

---

### Task 18: Frontend — `calendar-api.ts` + `use-calendar-connector.ts`

**Files:**
- Create: `frontend/lib/calendar-api.ts`
- Create: `frontend/hooks/use-calendar-connector.ts`
- Test: `frontend/tests/use-calendar-connector.test.tsx`

**Interfaces:**
- Produces: `CALENDAR_CONNECT_URL`, `useCalendarDisconnect()`,
  `useCalendarConnectErrorFromUrl()`, `planRun(input): Promise<PlannedRun>`.

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/use-calendar-connector.test.tsx`, copying
`frontend/tests/use-health-connector.test.tsx` structure exactly, replacing `health` with
`calendar` throughout (endpoint `/auth/calendar/disconnect`, query key invalidated,
`calendar_connect_error` param name).

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- use-calendar-connector` (from `frontend/`)
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

Create `frontend/lib/calendar-api.ts`:

```typescript
import { apiFetch } from "@/lib/api";

export type PlanRunInput = {
  title: string;
  start_time: string;
  duration_minutes: number;
  notes?: string;
};

export type PlannedRun = {
  id: string;
  summary: string;
  start: { dateTime: string };
};

export function planRun(input: PlanRunInput): Promise<PlannedRun> {
  return apiFetch<PlannedRun>("/calendar/events", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
```

Create `frontend/hooks/use-calendar-connector.ts` (mirror `use-health-connector.ts`
verbatim, substituting `calendar` for `health`):

```typescript
// frontend/hooks/use-calendar-connector.ts
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiFetch } from "@/lib/api";

export const CALENDAR_CONNECT_URL = `${process.env.NEXT_PUBLIC_API_URL}/auth/calendar/connect`;

export function useCalendarDisconnect() {
  const queryClient = useQueryClient();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function disconnect() {
    setIsPending(true);
    setError(null);
    try {
      await apiFetch("/auth/calendar/disconnect", { method: "POST" });
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    } catch (err) {
      setError(err instanceof Error ? err : new Error("Disconnect failed"));
    } finally {
      setIsPending(false);
    }
  }

  return { disconnect, isPending, error };
}

export function useCalendarConnectErrorFromUrl(): boolean {
  const [hasError] = useState(() => {
    if (typeof window === "undefined") return false;
    const params = new URLSearchParams(window.location.search);
    return params.get("calendar_connect_error") === "1";
  });

  return hasError;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- use-calendar-connector` (from `frontend/`)
Expected: PASS

---

### Task 19: Frontend — re-add Google Calendar row to connectors screen

**Files:**
- Modify: `frontend/components/connectors-screen.tsx`
- Test: `frontend/tests/connectors-screen.test.tsx`

**Interfaces:**
- Consumes: `useAuth()`'s `calendar_connected` field (already returned by `/auth/me` per
  Task 5 — confirm `frontend/lib/auth-context.tsx`'s `User`/`AuthState` type includes it;
  add it there if it's explicitly typed rather than inferred).
- Consumes: `CALENDAR_CONNECT_URL`, `useCalendarDisconnect` (Task 18).

- [ ] **Step 1: Read the current file**

Read `frontend/components/connectors-screen.tsx` in full to see exactly how the Health row
is rendered (the 2026-08-05 health-connector-wiring spec removed the old mocked Calendar
row — confirm it's actually gone before re-adding).

- [ ] **Step 2: Write the failing test**

Add to `frontend/tests/connectors-screen.test.tsx`, following that file's existing
Health-row test structure: assert a "Google Calendar" row renders, shows "Connect" when
`calendar_connected` is false and "Disconnect" when true, and that clicking "Disconnect"
calls the calendar disconnect endpoint.

- [ ] **Step 3: Run test to verify it fails**

Run: `npm test -- connectors-screen` (from `frontend/`)
Expected: FAIL — no Calendar row found

- [ ] **Step 4: Implement**

Add a second row to `ConnectorsScreen`, structurally identical to the Health row, sourced
from `useAuth()`'s `calendar_connected`, using `CALENDAR_CONNECT_URL` for the connect link
and `useCalendarDisconnect()` for disconnect — same component, same conditional
rendering logic as the Health row, just pointed at the Calendar hook/URL/field.

- [ ] **Step 5: Run test to verify it passes**

Run: `npm test -- connectors-screen` (from `frontend/`)
Expected: PASS

---

### Task 20: Frontend — dashboard `upcoming_runs`/`current_weather` types + fetch

**Files:**
- Modify: `frontend/lib/dashboard-api.ts`
- Test: none new (type-only change; covered by Task 21's rendering test)

**Interfaces:**
- Produces: `UpcomingRun`, `CurrentWeather` types; `Dashboard` type gains
  `upcoming_runs: UpcomingRun[]`, `calendar_connected: boolean`,
  `current_weather: CurrentWeather | null`.

- [ ] **Step 1: Implement**

```typescript
export type UpcomingRun = {
  id: string;
  summary: string;
  start: { dateTime: string };
  forecast: { temp: number; condition: string } | null;
};

export type CurrentWeather = {
  temp: number;
  feels_like: number;
  humidity: number;
  wind: number;
  condition: string;
  aqi: number;
  hourly: { time: string[]; temperature_2m: number[] };
};

export type Dashboard = {
  weekly_stats: WeeklyStats | null;
  recent_runs: RecentRun[];
  health_error?: HealthError | null;
  calendar_connected: boolean;
  upcoming_runs: UpcomingRun[];
  current_weather: CurrentWeather | null;
};
```

- [ ] **Step 2: Type-check**

Run: `npx tsc --noEmit` (from `frontend/`)
Expected: no new errors.

---

### Task 21: Frontend — Upcoming Runs section + Weather card + Plan a run modal

**Files:**
- Modify: `frontend/components/dashboard-screen.tsx`
- Create: `frontend/hooks/use-plan-run.ts`
- Test: `frontend/tests/dashboard-screen.test.tsx`

**Interfaces:**
- Consumes: `Dashboard.upcoming_runs`/`current_weather`/`calendar_connected` (Task 20),
  `planRun` (Task 18).
- Produces: `usePlanRun()` — a mutation hook wrapping `planRun`, invalidating the
  `["dashboard"]` query on success (check `use-dashboard.ts` for the exact query key
  already used, to invalidate the right one).

- [ ] **Step 1: Write the failing test**

Add to `frontend/tests/dashboard-screen.test.tsx`, following that file's existing
mock-`Dashboard`-response pattern: render with a `Dashboard` fixture that includes one
`upcoming_runs` entry and a `current_weather` object, assert both render; render with
`calendar_connected: false` and assert a connect prompt shows instead; click "+ Plan a
run", fill the modal fields, submit, assert `planRun` (mocked) was called with the right
payload.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- dashboard-screen` (from `frontend/`)
Expected: FAIL — no "Upcoming" section, no "+ Plan a run" button found

- [ ] **Step 3: Implement `use-plan-run.ts`**

```typescript
// frontend/hooks/use-plan-run.ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { planRun, type PlanRunInput } from "@/lib/calendar-api";

export function usePlanRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: PlanRunInput) => planRun(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
```

(Confirm `["dashboard"]` matches `use-dashboard.ts`'s actual query key before using it —
adjust if that file uses a different key shape.)

- [ ] **Step 4: Implement dashboard sections**

In `frontend/components/dashboard-screen.tsx`:
- Add a "+ Plan a run" button (top-right, per the approved mockup) that opens a modal with
  controlled inputs for `title`, `date`, `time`, `duration_minutes`, `notes`; on submit,
  combine date+time into an ISO `start_time` string and call `usePlanRun().mutate(...)`;
  close the modal and show a form-level error on failure (keep inputs populated, per the
  spec's error-handling table); disable/hide the button when `calendar_connected` is
  false.
- Add a "Weather" card (near the existing stats card) rendering `current_weather` fields
  when non-null; render nothing (or a minimal placeholder) when `current_weather` is null
  — never block the rest of the dashboard.
- Add an "Upcoming Runs" section below "Recent Runs", same card-grid component/style,
  mapping `upcoming_runs` to cards showing `summary`, formatted `start.dateTime`, and
  `forecast.temp`/`forecast.condition` when `forecast` is non-null (omit the weather line
  silently when `forecast` is null, per the spec).
- When `calendar_connected` is false, render a connect prompt (matching the existing
  Health-disconnected pattern elsewhere in this component) in place of the Upcoming Runs
  section.

- [ ] **Step 5: Run test to verify it passes**

Run: `npm test -- dashboard-screen` (from `frontend/`)
Expected: PASS

- [ ] **Step 6: Manually verify in the browser**

Run the dev server, log in as a test user with both Health and Calendar connected, and a
location set in preferences. Confirm: Upcoming Runs section renders with real Calendar
data, weather card shows real Open-Meteo data, "+ Plan a run" successfully creates an
event visible on next dashboard refresh and in the actual Google Calendar.

---

### Task 22: Frontend — profile screen location input

**Files:**
- Modify: `frontend/lib/preferences-api.ts`
- Modify: the profile/preferences form component (find it via
  `grep -r "weekly_goal_km" frontend/components` — it's the same component the existing
  preferences form lives in)
- Test: whichever test file already covers that component's preferences form.

**Interfaces:**
- Consumes: `updatePreferences` (existing, `preferences-api.ts`).

- [ ] **Step 1: Update the `Preferences` type**

In `frontend/lib/preferences-api.ts`:

```typescript
export type Preferences = {
  weekly_goal_km: number;
  units: "km" | "mi";
  notifications_enabled: boolean;
  language: "en" | "de";
  location_lat: number | null;
  location_lon: number | null;
};
```

- [ ] **Step 2: Write the failing tests**

In the profile form's existing test file, add tests asserting:
1. A "Use my location" button exists; clicking it calls (a mocked)
   `navigator.geolocation.getCurrentPosition`, and on success calls `updatePreferences`
   with the returned `coords.latitude`/`coords.longitude`.
2. A city-search text input exists as a fallback; typing a query and selecting a result
   (mock the Open-Meteo geocoding fetch) calls `updatePreferences` with the geocoded
   `location_lat`/`location_lon`.
3. Geolocation failure/denial (mock `getCurrentPosition`'s error callback) does not throw
   and leaves the city-search fallback usable.

- [ ] **Step 3: Run test to verify it fails**

Run: `npm test -- <profile-form-test-file>` (from `frontend/`)
Expected: FAIL — no location controls found

- [ ] **Step 4: Implement**

Add `frontend/lib/geocoding-api.ts`:

```typescript
const GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search";

export type GeocodingResult = {
  name: string;
  latitude: number;
  longitude: number;
  admin1?: string;
  country?: string;
};

export async function searchCities(query: string): Promise<GeocodingResult[]> {
  if (query.trim().length < 2) return [];
  const response = await fetch(
    `${GEOCODING_URL}?name=${encodeURIComponent(query)}&count=5`
  );
  const data = await response.json();
  return data.results ?? [];
}
```

In the preferences form component, add two controls:
- A **"Use my location" button** that calls `navigator.geolocation.getCurrentPosition`,
  and on success calls `updatePreferences({ location_lat: coords.latitude, location_lon: coords.longitude })`
  (same instant-update pattern as `units`/`notifications`). On error (denied/unsupported),
  show an inline message pointing at the fallback below — do not throw.
- A **debounced city-search text input** (same debounce pattern as the `weekly_goal_km`
  stepper) that calls `searchCities`, renders matches in a small dropdown, and on
  selecting one calls `updatePreferences` with that result's `latitude`/`longitude`.

If a location is already set, show it read-only above both controls (e.g. resolved city
name from the last geocode, or plain "Location set" if set via geolocation) with an "Edit"
affordance that reveals the two controls again.

- [ ] **Step 5: Run test to verify it passes**

Run: `npm test -- <profile-form-test-file>` (from `frontend/`)
Expected: PASS

---

## Final Commit

With all tasks implemented and tests green, make a single commit at the end:

- [ ] **Step 1: Commit everything at the end**

```bash
git add .
git commit -m "feat: add calendar planning and weather integration"
```

---

## Self-Review Notes

- **Spec coverage:** every section of the design doc maps to a task — auth/connector
  (Tasks 3–5), dedicated calendar (Task 6), event CRUD tools (Tasks 7–8), deployment
  (Tasks 9, 17), weather service (Task 10), quick-add endpoint (Task 11), dual-session
  chat wiring (Tasks 12–14), dashboard data (Task 15), location storage (Tasks 2, 16, 22),
  frontend surface (Tasks 18–21).
- **Placeholder scan:** no TBDs; the two spec-flagged open questions (location input UX,
  forecast horizon cutoff) are resolved with explicit decisions in Tasks 10 and 22
  rather than left open, since a plan can't ship a placeholder — if the user disagrees
  with either choice during review, only those two tasks need revision.
- **Type consistency:** `provider="calendar"` (not `service`) used everywhere, matching
  the actual `oauth_tokens.provider` column name — the spec's prose used "service"
  generically; this plan corrects it to the real schema. `get_valid_access_token`'s new
  `provider` parameter, `CALENDAR_SERVER_URL`, `open_mcp_session(user_id, server_url=...)`,
  and `sessions_by_tool` are used identically across every task that references them.
