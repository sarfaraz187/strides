# Strides — Project Plan

## What You're Building

A personal running coach agent that lives in your terminal. It authenticates with Google,
fetches your real run data from Google Fit, and lets you chat about your training.

---

## Phase 1 — Google OAuth
**Goal: Authenticate with Google so you can call the Fit API.**

### Build order
1. Google Cloud Console — create project, enable Fit API, create OAuth credentials
2. `auth.py` — OAuth flow, token save/refresh

### Done when
```
python auth.py
→ Browser opens, you log in, token.json is saved
```

---

## Phase 2 — Google Fit MCP Server + Agent
**Goal: Wrap Google Fit as an MCP server and connect an agent to it.**

### Build order
1. `fit_server.py` — MCP server that calls Google Fit REST API using saved token
2. `agent.py` — connects to fit_server, discovers tools dynamically, runs chat loop

### Tools to build in fit_server.py
- `get_recent_runs(days)` — runs from last N days
- `get_run_stats(start_date, end_date)` — aggregated stats for a period
- `get_weekly_summary()` — total distance, avg pace, number of runs this week

### Done when
```
You: how was my running this week?
→ Agent fetches real data from Google Fit and responds

You: what was my pace yesterday?
→ Agent calls the right tool and gives a real answer
```

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
