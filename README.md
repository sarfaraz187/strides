# Strides

A personal running coach agent that lives in the terminal. Authenticates with Google, fetches real run data, and lets you chat about your training.

This is a learning project focused on the fundamentals of MCP (Model Context Protocol), system prompts, and agent memory — not a production app.

## How it fits together

- **`src/fit_server.py`** — an MCP *server*. It exposes tools (`get_runs`, `get_recent_runs`, `get_run_stats`, `get_weekly_stats`, `calculate`) that fetch and aggregate data from the Google Health API.
- **`src/agent.py`** — an MCP *client* + Claude tool-use chat loop. It spawns `fit_server.py` as a subprocess, discovers its tools over stdio, and lets you chat with Claude about your runs.
- **`src/auth/auth.py`** + **`data/db.py`** — Google OAuth flow and SQLite-backed token storage (with refresh).

Data source note: this project talks to the **Google Health API** (`health.googleapis.com`), not the old Google Fit REST API — that one is closed to new developers and being deprecated. See `CLAUDE.md` for the full backstory.

## Setup

Requires `uv`.

```bash
uv sync
```

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

## Authenticating with Google (OAuth)

Run the OAuth flow to authenticate and save a token to `data/strides.db`:

```bash
uv run python -m src.auth.auth
```

What happens:

1. Terminal prints a Google login URL — open it in a browser, log in with the account that has run data, and approve access.
2. You'll land on `google.com` with a broken-looking page — that's expected (the redirect URI is a placeholder, no local server catches it).
3. Copy the `code` value from the browser's address bar (the part after `code=` and before `&scope`).
4. Paste it back into the terminal when prompted.
5. Access + refresh tokens are saved to `data/strides.db`.

You only need to do this once — after that, `get_valid_access_token()` reuses the saved token and refreshes it automatically when it expires. If the **refresh token itself** has expired (Google's OAuth apps in "Testing" mode only keep refresh tokens alive for ~7 days), running `uv run python -m src.auth.auth` again will detect the `invalid_grant` error and automatically restart the OAuth flow from step 1.

## Running it

Make sure you've authenticated first (see above) — a token must exist in `data/strides.db` before either entry point below can fetch real data.

Imports are rooted at the project root, so entry points must be run as modules (`-m`), not as bare scripts:

```bash
# Run the MCP server standalone (useful for testing tools directly, e.g. with MCP Inspector)
uv run python -m src.fit_server

# Run the agent (spawns fit_server.py itself, no need to start it separately)
uv run python -m src.agent
```

`agent.py` starts an interactive chat loop — ask it things like "how was my week?" or "what were my last few runs?", type `quit` to exit.

## Testing MCP tools directly

To call a tool (e.g. `get_runs`) and inspect its output/logs without going through the full agent chat loop, use the official [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector uv run python -m src.fit_server
```

This opens a browser UI connected to `fit_server.py` where you can pick a tool, run it with custom inputs, and see the result plus anything printed to stderr — much faster for debugging a single tool than running the whole agent.

## Status

**Phase 2 (MCP server + agent) — done.** See `docs/PLAN.md` for the full phased plan.

- ✅ Phase 1 — Google OAuth + SQLite token storage, with automatic re-auth if the refresh token expires
- ✅ Phase 2 — `fit_server.py` exposes `get_runs` (raw), `get_recent_runs(days)`, `get_run_stats(start_date, end_date)`, and `get_weekly_stats()`, with unit conversion and aggregation done server-side. `agent.py` connects, discovers tools dynamically, and runs a Claude tool-use chat loop. Verified end-to-end with real data.
- ⏳ Phase 3 — local tools for goals/notes, not started

## Project structure

```
strides/
├── main.py
├── data/
│   └── db.py                  # SQLite token storage
├── src/
│   ├── agent.py                # MCP client + Claude chat loop
│   ├── fit_server.py            # MCP server (exposes tools)
│   ├── auth/
│   │   └── auth.py              # Google OAuth
│   └── helpers/
│       ├── health_api.py        # Google Health API request wrapper
│       └── formatter.py
├── tests/
│   └── test_fit_server.py
├── docs/
│   └── PLAN.md                  # full phased project plan
└── pyproject.toml
```
