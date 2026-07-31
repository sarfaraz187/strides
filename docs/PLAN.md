# Strides — Project Plan

## What You're Building

A running coach agent, originally a personal terminal tool, now being evolved into a
multi-user product with a web chat client. It authenticates with Google, fetches real
run data from the Google Health API, and lets users chat about their training.

See `CLAUDE.md` for the full story on why Google Fit REST API was abandoned in favor of the
Google Health API, and why tokens are stored in SQLite instead of `token.json`.

## Direction change: multi-user product (decided, architecture still being worked out)

Decided so far:
- Client: web chat app, PWA-capable (phone-friendly without native app store overhead)
- Transport: MCP servers move from stdio to Streamable HTTP (stdio is single-user/single-machine only)
- Auth: Google Sign-In doubles as login + grants Health/Calendar scopes
- Database: SQLite → Cloud SQL (Postgres) — SQLite doesn't survive concurrent multi-user
  writes or container restarts
- Hosting: GCP Cloud Run (pay-per-request, fits available credits)

Decided sequencing:
1. Migrate `fit_server.py` from stdio → Streamable HTTP transport, with multi-user auth
   built in from this step (not retrofitted later)
2. Build a client that talks to it over HTTP (replacing/evolving `agent.py`)
3. Get that working end-to-end, multi-user, before adding anything new
4. Calendar (Phase 4) is explicitly a later add-on, decided only after the above works —
   not being designed now

### Confirmed target architecture

Three-way split, justified by a real constraint (stdio can't serve multiple browser
clients — this isn't preference, it's a hard wall), and deliberately not going further
than that constraint requires (no planner/evaluator agents, no gateway/microservices —
see Anthropic's "Building Effective Agents" and harness-design writeups: add complexity
only when a real wall forces it):

```
strides/
├── backend/                  # was agent.py — real web backend now
│   ├── main.py                 # FastAPI app, HTTP endpoints for the frontend
│   ├── agent.py                 # Claude loop + MCP client logic (agent.py minus input()/print())
│   └── auth.py                  # per-user session/identity handling
├── mcp_servers/
│   └── fit_server/
│       ├── server.py             # was src/fit_server.py
│       └── helpers/               # health_api.py, formatter.py
├── frontend/                  # new — web chat UI, PWA-capable
├── auth/                        # existing Google OAuth (src/auth/auth.py)
├── data/                        # db.py — migrates to Postgres later
└── docs/PLAN.md
```

Key point: `backend/` (real MCP client, holds the Claude conversation loop) and
`mcp_servers/` (pure tool providers) are separate deployable things, even if they start
in one repo. The browser only ever talks to `backend/`, never to MCP servers directly.

### Confirmed: session auth design

No email/password — every user needs a Google account anyway (Health/Calendar access
requires it), so a second auth system would be pure extra surface with no benefit.

Flow:
1. User clicks "Sign in with Google" → Google OAuth consent → backend receives identity
   + Health/Calendar access token.
2. Backend saves the Google token in the `tokens` table (as today).
3. Backend generates a random opaque session token, stores it in a new `sessions` table
   keyed to the user's email, sends it to the browser as a cookie.
4. Every subsequent request: browser auto-sends the cookie → backend looks up the token
   in `sessions` → finds the user → uses that identity to pull the right Google token
   from `tokens` for any Health/Calendar API call.
5. Logout = delete the row from `sessions`. Immediate effect.

Opaque token + DB lookup chosen over JWT: a DB is already in the picture (Google tokens
live there), real revocation matters (logout, compromised token) and is free with this
approach, and request volume doesn't yet justify JWT's stateless-verification tradeoff
(harder revocation, needs a blocklist to fix). JWT is a legitimate future upgrade once
scale actually demands it — not a now problem.

Still open — architecture details not yet worked through in detail:
- OAuth callback design (replacing the current manual paste-code-in-terminal flow)
- How `agent.py`'s chat loop maps onto a request/response (or streaming) backend API
- Database migration timing (SQLite → Cloud SQL) — not yet decided if this happens
  alongside the transport migration or after

This is a significant architecture shift from everything below (Phases 1-2, built and
verified as a single-user local CLI tool). Phases 3+ below are pre-pivot and will be
revised once the multi-user architecture is settled — treat them as historical context,
not the current plan.

---

## Phase 1 — Google OAuth ✅ Done
**Goal: Authenticate with Google so you can call the Health API.**

### Build order
1. ~~Google Cloud Console — create project, enable Fit API, create OAuth credentials~~
   Done — project `strides-01263`, Health API enabled instead of Fit API (see CLAUDE.md)
2. ~~`auth.py` — OAuth flow, token save/refresh~~ Done (`src/auth.py`)
3. ~~`db.py` — SQLite token storage~~ Done (`data/db.py`), replaces `token.json`

### Done when
```
python auth.py
→ Browser opens (first run only), you log in, token saved to SQLite (data/strides.db)
→ Subsequent runs silently reuse or refresh the saved token
```

---

## Phase 2 — Google Health MCP Server + Agent ✅ Done
**Goal: Wrap the Google Health API as an MCP server and connect an agent to it.**

### Build order
1. ~~`fit_server.py` — MCP server that calls the Google Health API using saved token~~
   Done (`src/fit_server.py`) — four tools: `get_runs` (raw), `get_recent_runs(days)`,
   `get_run_stats(start_date, end_date)`, `get_weekly_stats()`. Aggregation (unit
   conversion, totals, avg pace) happens server-side via `src/helpers/formatter.py`'s
   `parse_run()`, not in the LLM's system prompt. Also has a `calculate()` tool.
2. ~~`agent.py` — connects to fit_server, discovers tools dynamically, runs chat loop~~
   Done (`src/agent.py`) — dynamic tool discovery + full Claude tool-use loop working.
   System prompt describes all four tools and when to use each.

### Done when
```
You: how was my running this week?
→ Agent fetches real data from Google Health API and responds

You: what was my pace yesterday?
→ Agent calls the right tool and gives a real answer
```
Verified end-to-end with real data via `uv run python -m src.agent`.

---

## Phase 3 — Local Tools (when you feel the need)
**Goal: Add local tools for things Google Fit doesn't know — your goals, notes, feelings.**

### Only build this when Phase 2 is working and you feel something is missing.

### Build order
1. `tracker_server.py` — local MCP server, in-memory storage (no DB yet)
2. Update `agent.py` to connect to both MCP servers simultaneously

### Tools to build
- `set_goal(goal_type, target)` — save a running goal
- `get_goals()` — retrieve goals
- `add_note(content)` — add a note after a run
- `get_notes(limit)` — retrieve recent notes

### Done when
```
You: my goal is to run 30km this week
You: how am I tracking against my goal?
→ Agent checks Google Fit for actual km AND local tools for your goal
```

---

## Folder Structure

```
strides/
├── agent.py                  # main agent
├── fit_server.py             # Google Fit MCP server
├── tracker_server.py         # local MCP server (Phase 3)
├── auth.py                   # Google OAuth
├── token.json                # auto-created, add to .gitignore
├── .env                      # API keys
├── .gitignore
├── docs/
│   └── PLAN.md               # this file
└── pyproject.toml
```

---

## Environment Variables (.env)

```
ANTHROPIC_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

---

## What comes later (not in scope now)
- SQLite for persistent storage
- Conversation memory across sessions
- Scheduling / nightly summaries
- Frontend / chat UI
