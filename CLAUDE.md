# Strides

A personal running coach agent that lives in the terminal. Authenticates with Google, fetches real run data, lets you chat about your training. Full plan: `docs/PLAN.md`. This is a learning project — explain things simply, present a plan before writing code, and wait for approval before implementing (see also the user's global CLAUDE.md).

I am learning about Generative AI, AI agents and this project i am focusing on setting up MCP, system prompts, memory concepts.

## Status: Phase 2 (MCP server + agent) — in progress

Phase 1 (Google OAuth) is done — `auth.py` + `db.py` working with SQLite token storage (`data/strides.db`), including refresh. `test_fetch.py` (the throwaway reference script) is gone from the repo now that the real flow lives in `auth.py`.

Phase 2: `fit_server.py` (MCP server) and `agent.py` (Claude tool-use chat loop) both exist and are wired together, but `fit_server.py` only exposes one generic `get_runs()` tool — the planned `get_recent_runs(days)` / `get_run_stats(start_date, end_date)` / `get_weekly_summary()` tools (with server-side aggregation) aren't built yet. Right now the agent's system prompt asks the LLM to do the unit math (m→km, ms→min, pace) itself instead. See `docs/PLAN.md` Phase 2 for details.

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
