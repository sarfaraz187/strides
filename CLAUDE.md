# Strides

A personal running coach agent that lives in the terminal. Authenticates with Google, fetches real run data, lets you chat about your training. Full plan: `docs/PLAN.md`. This is a learning project — explain things simply, present a plan before writing code, and wait for approval before implementing (see also the user's global CLAUDE.md).

I am learning about Generative AI, AI agents and this project i am focusing on setting up MCP, system prompts, memory concepts.

## Status: Phase 2 (MCP server + agent) — done

Phase 1 (Google OAuth) is done — `auth.py` + `db.py` working with SQLite token storage (`data/strides.db`), including refresh, plus a fallback to re-run the full OAuth flow when the refresh token itself has expired (Google returns `invalid_grant`).

Phase 2 is done — `mcp_servers/fit_server/server.py` (MCP server) exposes four tools: `get_runs` (raw), `get_recent_runs(days)`, `get_run_stats(start_date, end_date)`, and `get_weekly_stats()`. Unit conversion (millimeters→km, seconds-string→minutes) and aggregation (totals, average pace) happen server-side in `mcp_servers/fit_server/helpers/formatter.py`'s `parse_run()`, not in the LLM's system prompt. `backend/agent.py` connects via MCP Streamable HTTP (`http://127.0.0.1:8000/mcp`), discovers tools dynamically, and runs the Claude tool-use chat loop. Verified end-to-end with real data. See `docs/PLAN.md` Phase 2 for details; Phase 3 (local tools for goals/notes) not started.

Repo layout was split per the plan's target architecture: `backend/agent.py` (Claude loop + MCP client), `mcp_servers/fit_server/` (pure tool provider), `auth/auth.py` (Google OAuth), `logging_config.py` (shared, top-level — imported by both `auth.py` and `fit_server.py`). Old `src/` package removed.

### Google Health API filter syntax (learned the hard way)

The `dataPoints.list` `filter` query param follows Google's AIP-160 filter syntax, not what you'd guess from the JSON field names:
- String literals need **double quotes**, not single quotes.
- The filterable field for exercise start time is `exercise.interval.civil_start_time` (a "civil"/local timestamp, e.g. `"2026-07-20T00:00:00"`, no trailing `Z`) — not `exercise.interval.start_time` (which exists in the JSON response but isn't a valid filter member) and not the raw JSON field name `startTime`.
- Range filters use `AND`, e.g. `exercise.interval.civil_start_time>="..." AND exercise.interval.civil_start_time<"..."`.
- Build the filter value via `requests`' `params=` dict, not hand-built into the URL string — reserved characters (colons, quotes) need proper percent-encoding or the API returns `INVALID_DATA_POINT_FILTER_SYNTAX`.

### MCP stdio logging gotcha

stdio transport reserves stdout for the JSON-RPC protocol — any stray `print()` without `file=sys.stderr` (or plain `logging` output not routed to stderr) can corrupt the connection. (No longer a live constraint now that `fit_server.py` runs over Streamable HTTP, but kept as the reason logging is routed the way it is.) All logging in this project goes through top-level `logging_config.py`'s `setup_logging()`, called once per entry point (`fit_server.py`, `auth.py`), writing to stderr only.

### FastMCP tool return-type gotcha

`@mcp.tool()`-decorated functions need their return type annotation to actually match what they return, and a bare `dict` annotation (unparameterized) causes `FastMCP` to fail with "Tool has an output schema but did not return structured content" — use `dict[str, Any]` instead.

## Key discovery: data source is not the Google Fit REST API

PLAN.md originally assumed the Google Fit REST API. That API is **closed to new developer sign-ups since May 2024** and fully deprecated end of 2026 — not usable for this project.

The real replacement is the **Google Health API** (`health.googleapis.com`), a separate product from the Fit app:

- Cloud-based, OAuth 2.0, server/Python-friendly (unlike Health Connect, which is Android-only, on-device, no OAuth).
- It is backed by **Fitbit's account/data system**. Historical data from the Google Fit _app_ does NOT automatically carry over — the API only sees data explicitly entered into or synced with a Google Health profile. A user must sign up at Google Health and have data there (manual entry or a Fitbit/synced source) for the API to return anything. First attempt without this returned `ACCOUNT_NOT_LINKED` / `FAILED_PRECONDITION`.

## GCP setup (already done)

- Project: `strides-01263` (billing linked, required even for free usage)
- API enabled: `health.googleapis.com`
- OAuth consent screen: External audience, test user `sarfarazflame@gmail.com` (the account with run data — separate from the GCP owner account `sarfarazmohammed187@gmail.com`)
- OAuth Client: **Web application** type, redirect URI `https://www.google.com` (placeholder — no local server, auth code is copy-pasted manually from the browser address bar)
- Scope registered on Data Access page: `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly`
- Credentials in `.env`: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`

## API reference notes

- Correct endpoint for run/exercise data: `GET https://health.googleapis.com/v4/users/me/dataTypes/exercise/dataPoints` (there is no dedicated "activity log" or "sessions" resource — everything is generic `dataTypes.dataPoints`)
- Token exchange: `POST https://oauth2.googleapis.com/token`
- Refresh tokens expire after 7 days while the OAuth app is in "Testing" publish status; don't expire (until revoked/unused 6mo) once "In Production"

## Storage decision

Using SQLite (`db.py`, `strides.db`) for token storage instead of the `token.json` file PLAN.md originally specified. Table: `tokens (id, access_token, refresh_token, expires_at)`.
