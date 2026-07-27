# Strides

A personal running coach agent that lives in the terminal. Authenticates with Google, fetches real run data, and lets you chat about your training.

This is a learning project focused on the fundamentals of MCP (Model Context Protocol), system prompts, and agent memory — not a production app.

## How it fits together

- **`src/fit_server.py`** — an MCP *server*. It exposes tools (`get_runs`, `calculate`, ...) that fetch data from the Google Health API.
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

Run the OAuth flow once to authenticate and save a token to `data/strides.db`:

```bash
uv run python -m src.auth.auth
```

## Running it

Imports are rooted at the project root, so entry points must be run as modules (`-m`), not as bare scripts:

```bash
# Run the MCP server standalone (useful for testing tools directly, e.g. with MCP Inspector)
uv run python -m src.fit_server

# Run the agent (spawns fit_server.py itself, no need to start it separately)
uv run python -m src.agent
```

## Testing MCP tools directly

To call a tool (e.g. `get_runs`) and inspect its output/logs without going through the full agent chat loop, use the official [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector uv run python -m src.fit_server
```

This opens a browser UI connected to `fit_server.py` where you can pick a tool, run it with custom inputs, and see the result plus anything printed to stderr — much faster for debugging a single tool than running the whole agent.

## Status

**Phase 2 (MCP server + agent) — in progress.** See `docs/PLAN.md` for the full phased plan.

- ✅ Phase 1 — Google OAuth + SQLite token storage
- 🚧 Phase 2 — `fit_server.py` and `agent.py` are wired together and working end-to-end, but the server only exposes a generic `get_runs()` tool. Planned: `get_recent_runs(days)`, `get_run_stats(start_date, end_date)`, `get_weekly_summary()` with server-side aggregation (currently the agent's system prompt asks the LLM to do unit math itself).
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
