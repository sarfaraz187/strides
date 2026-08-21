# Google Calendar planning + weather-aware dashboard

Decided 2026-08-21. Scope: add a new `calendar_server` MCP server so the agent (and the
dashboard) can read/write planned runs on a dedicated Google Calendar, plus a plain
in-process `weather_service` so both the dashboard and the agent can factor forecast data
into run planning.

## Why

The agent already has long-term memory (`memories` table) and completed-run history
(Health, via `fit_server`). It has no way to *plan* future runs anywhere durable, and no
way to reason about weather when suggesting a plan. Google Calendar becomes the source of
truth for planned/upcoming runs — same role Google Health plays for completed runs — and
weather becomes a factor both surfaced on the dashboard and available to the agent as a
tool.

## Out of scope

- Google's hosted Calendar MCP server (`calendarmcp.googleapis.com`) — Developer Preview,
  built for interactive single-user MCP hosts (Claude Desktop, Antigravity) with
  browser-paste OAuth, not documented for multi-tenant backend use. Considered and
  rejected; see decision log below.
- Third-party `workspace-mcp` (open-source, self-hosted, genuinely multi-tenant-capable) —
  considered and rejected in favor of owning the code end-to-end, matching the existing
  `fit_server` pattern, and avoiding a second auth/token architecture running alongside
  the one this project already has.
- Per-run AI-generated coaching commentary ("Ideal conditions", "Hydrate well") — dropped
  from the dashboard mockup; adds an interpretation layer not needed for v1.
- Agent-driven "Plan a run" button — the button is a plain manual quick-add form, not an
  agent invocation. Agent-assisted planning happens only through chat.
- Folding `calendar_server` into `fit_server`'s process — kept as a separate Cloud Run
  service instead, for consistency with the separate-connector/separate-token decision
  (see below) and because per-service cost at this traffic level is negligible
  (Cloud Run bills per-request, not per-idle-service).

## Decision log (from brainstorming)

- **Separate OAuth connector, separate tokens** for Calendar vs. Health, matching how
  `oauth_tokens` already stores Health — new rows with `service = "calendar"`, no schema
  change needed. Rejected combining under one broader-scope connection: least-privilege,
  independent token lifecycles, and it's the pattern this app (and most real products —
  Zapier, Claude's own MCP connectors) already uses for multi-service Google access.
- **Dedicated "Strides Runs" calendar**, not the user's primary calendar. Created via
  `calendars.insert` on first successful Calendar connect; its `calendar_id` is stored
  alongside the token. Keeps planned-run queries clean without title/color-tag filtering
  hacks.
- **Weather is not an MCP server.** Unlike Health/Calendar, it has no OAuth/per-user
  token — it's a plain public API call keyed by lat/lon. MCP indirection in this project
  exists specifically to let the backend act "as the user" via minted JWTs against
  OAuth-gated data; weather has no user identity to scope by, so it's a plain in-process
  service (`weather_service.py`), called directly by both `chat_service.py` (as a tool,
  same shape as the existing `save_memory` tool) and `dashboard.py`.
- **Weather provider: Open-Meteo.** Free, no API key/secret to manage. Covers all three
  needs found during design — forecast-by-date (per upcoming run), current conditions
  (temp/feels-like/humidity/wind, main dashboard weather card), and hourly breakdown — via
  its Forecast API `current`/`hourly` params, plus a separate free Air Quality API
  (`air-quality-api.open-meteo.com`) for AQI. One provider, two endpoints, no new secret.
- **Location: stored explicitly**, not derived from Health/Calendar data (neither
  reliably implies a home location). Set via the profile screen using the browser
  Geolocation API ("Use my location" button) with a city-search fallback (geocoded via
  Open-Meteo's free geocoding endpoint) for when permission is denied or the user wants a
  different location than their current one. Add `location` (lat/lon) to the
  `preferences` table — same storage shape either way, only the input UX changes.
- **"Plan a run" is a dumb quick-add, not agent-invoked.** A form can't reason about
  training load the way the agent already does — v1 keeps the button as manual CRUD
  (title/date/time/duration/notes → `create_run_event`), and reserves actual
  weather-aware, load-aware planning intelligence for chat.

## Architecture

```
                     ┌─────────────────────────┐
                     │   Strides frontend        │
                     │ (dashboard, chat, profile)│
                     └───────────┬──────────────┘
                                 │
                     ┌───────────▼──────────────┐
                     │  Strides backend (FastAPI) │
                     │                            │
                     │  routes/auth.py            │──OAuth──▶ Google Calendar consent
                     │  routes/dashboard.py       │
                     │  routes/calendar.py (new)  │
                     │  routes/preferences.py     │
                     │  services/chat_service.py  │──in-process──▶ weather_service.py
                     │  services/mcp_client.py    │                    │
                     └───────┬──────────┬─────────┘                    ▼
                              │          │                    Open-Meteo Forecast +
                    JWT       │          │  JWT               Air Quality APIs
                              ▼          ▼
                    ┌──────────────┐  ┌──────────────────┐
                    │ fit_server    │  │ calendar_server   │
                    │ (Health data) │  │ (new)             │
                    └──────────────┘  └───────┬───────────┘
                                               │
                                               ▼
                                     Google Calendar API
                                     ("Strides Runs" calendar)
```

## Backend changes

### Auth: Calendar connector

Mirrors `backend/routes/auth.py`'s existing Health flow:

- `GET /auth/calendar/connect`, `GET /auth/calendar/callback`,
  `POST /auth/calendar/disconnect` — same shape as `/auth/health/*`.
- Scopes: `calendar` (create/manage the dedicated calendar) + `calendar.events`
  (read/write events on it).
- `oauth_tokens`: new rows with `service = "calendar"` — no schema change. Add one nullable
  column, `calendar_id`, to hold the dedicated calendar's ID once created (tied to the
  connection, not a general preference, so it belongs on this table rather than
  `preferences`).
- On first successful connect, create the "Strides Runs" calendar via `calendars.insert`
  if `calendar_id` is not already stored for this user, then persist the returned ID.
- `GET /auth/me` gains `calendar_connected: bool`, same derivation pattern as
  `health_connected` (token row present → true).
- Callback failure handling matches Health's existing pattern: redirect to `FRONTEND_URL`
  with an error query param instead of a raw 500.

### `preferences` table: add `location`

New nullable column(s) for lat/lon, set via the profile screen: a "Use my location" button
(browser Geolocation API) as the primary path, with a city-search input (geocoded via
Open-Meteo's free geocoding endpoint) as a fallback for denied permission or a
non-current location. Used by `weather_service` calls from both dashboard and chat.

### New MCP server: `mcp_servers/calendar_server/`

Same skeleton as `mcp_servers/fit_server/`:

- FastMCP app, Streamable HTTP transport, JWT-verified against the backend's existing
  JWKS endpoint (`jwt_issuer.py` mints tokens for both servers already — no new signing
  infrastructure).
- `auth/auth.py` — per-user Postgres lookup for the Calendar OAuth token, same
  `SELECT ... FOR UPDATE` row-locking pattern `fit_server` uses to guard concurrent
  refreshes.
- Tools:
  - `list_upcoming_runs(user_id, days_ahead: int = 7) -> list[dict]` — events from the
    dedicated calendar within a date range.
  - `create_run_event(user_id, title: str, start_time: str, duration_minutes: int, notes: str = "") -> dict`
  - `update_run_event(user_id, event_id: str, ...) -> dict`
  - `delete_run_event(user_id, event_id: str) -> dict`
- Deployed as its own Cloud Run service, added to `.github/workflows/deploy.yml` alongside
  the existing backend/`fit_server` build+push+deploy steps, watching
  `mcp_servers/calendar_server/**` (and the shared `data/**`, `auth/**`, `pyproject.toml`,
  `uv.lock` paths already watched for the other services).

`backend/services/mcp_client.py` gets a second client instance pointed at
`CALENDAR_MCP_SERVER_URL`, alongside the existing Health one.

### `weather_service.py` (new, plain module — not an MCP server)

- `get_forecast(lat, lon, date) -> dict` — per-date forecast, used for each upcoming-run
  card.
- `get_current_conditions(lat, lon) -> dict` — temp, feels-like, humidity, wind, condition,
  hourly breakdown — used once per dashboard load for the current-weather card.
- `get_air_quality(lat, lon) -> dict` — AQI, separate Open-Meteo endpoint, same call
  pattern.
- Registered as a plain Anthropic tool in `chat_service.py` (same shape as the existing
  `save_memory` tool) so the agent can call it directly while reasoning about a plan,
  independent of the dashboard's calls.

### `backend/routes/calendar.py` (new)

- `POST /calendar/events` — the "Plan a run" quick-add form's endpoint. Body:
  `{ title, start_time, duration_minutes, notes? }`. Protected via `require_user`, calls
  `calendar_server.create_run_event`.
- Mirrors `preferences.py`'s shape (auth dependency, MCP client call, typed response).

### `backend/routes/dashboard.py`

`GET /dashboard` gains, alongside the existing `weekly_stats`/`recent_runs`:

```json
{
  "weekly_stats": {...},
  "recent_runs": [...],
  "upcoming_runs": [
    { "title": "...", "start_time": "...", "forecast": { "temp": 18, "condition": "clear" } }
  ],
  "current_weather": { "temp": 27, "feels_like": 30, "humidity": 74, "wind": 9, "aqi": 42, "hourly": [...] }
}
```

Data flow:

```
GET /dashboard
  ├─ fit_server: weekly_stats, recent_runs        (existing, unchanged)
  ├─ calendar_server: list_upcoming_runs           (new)
  ├─ weather_service.get_forecast(date) per run    (new, one call per upcoming event)
  ├─ weather_service.get_current_conditions()      (new, once)
  └─ weather_service.get_air_quality()             (new, once)
```

### `backend/agent.py`

`SYSTEM_PROMPT` gains instructions for when to call `create_run_event` — only after the
user confirms a proposed plan in conversation, never proactively without asking (mirrors
the existing caution already documented for `save_memory`).

## Frontend changes

### Dashboard

New sections, added without touching the existing stats card or Recent Runs:

- **Current weather card** — temp, feels-like, humidity, wind, AQI, hourly strip, sourced
  from `current_weather`. Positioned alongside the stats card (top area).
- **Upcoming Runs section** — same card-grid pattern as Recent Runs, sourced from
  `upcoming_runs`, each card showing date/time/title + a compact forecast line (temp +
  condition only — no coaching commentary, per decision log).
- **"+ Plan a run" button** — opens a modal (title, date, time, duration, notes) →
  `POST /calendar/events` → on success, close modal and refetch/optimistically update
  `upcoming_runs`.
- If Calendar isn't connected: "Upcoming" section shows a connect prompt instead of an
  empty state (same pattern as Health's `health_connected` gate elsewhere in the app), and
  the "Plan a run" button is disabled or hidden rather than allowed to hit a doomed
  request.

### Profile / preferences screen

Add a location control: a "Use my location" button (browser Geolocation API) as the
primary path, plus a city-search input (geocoded on save via Open-Meteo's geocoding
endpoint) as a fallback, stored via the existing preferences form pattern.

### Connectors screen

Google Calendar row re-added (it was explicitly removed as mock-only in the
2026-08-05 Health-connector-wiring spec) — now backed by the real
`/auth/calendar/connect` / `/auth/calendar/disconnect` flow, same component pattern as
Health.

## Error handling

| Scenario | Behavior |
|---|---|
| Calendar not connected, dashboard loads | "Upcoming" section shows a connect prompt instead of empty state |
| Calendar not connected, "Plan a run" clicked | Button disabled/hidden — don't let the user hit a doomed request |
| `create_run_event` fails (Google API error, expired/revoked token) | Backend returns a clear error; modal stays open, form input preserved |
| Weather API unreachable | Card/run still renders using Calendar/Health data alone; weather line/card omitted — weather is enrichment, never blocks core content |
| Forecast unavailable for a far-out event date | Same: omit weather line silently, no "N/A" clutter |
| Calendar token expired mid-request | Row-locked refresh (same pattern as Health) handles it silently; surfaced to the user only if refresh itself fails, at which point it presents as "not connected," prompting reconnect |

## Testing

Learning-project precedent (per the Health-connector-wiring spec) is to flag testing as
optional and ask. Worth asking the user, once implementation starts, whether they want:

- Backend test for `/auth/me` returning `calendar_connected` correctly.
- Backend test for the Calendar OAuth callback's error-redirect path.
- `calendar_server` tool tests (mocked Google Calendar API responses), matching whatever
  test coverage `fit_server`'s tools currently have.
- `weather_service` tests against mocked Open-Meteo responses.

## Open questions for implementer

- `preferences.location`: resolved above — store as lat/lon, set via browser Geolocation
  API primary path + Open-Meteo city-search fallback.
- Forecast horizon: Open-Meteo's forecast reliability drops beyond ~7-10 days out: confirm
  the cutoff used by `get_forecast` for deciding when to omit the weather line versus
  attempt the call.
