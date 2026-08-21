# Strides

**A personal running coach agent that lives in your browser.**

Strides connects to your Google Health data, understands your training history, and lets you chat with an AI coach about your runs — pace trends, weekly mileage, recovery, whatever you'd ask a real coach. It's a full-stack agent application: a custom MCP server for tool use, a streaming chat loop backed by Claude, long-term memory across conversations, and multi-user auth with encrypted token storage.

## Screenshots

**Sign in**
<p align="center">
  <img src="docs/images/sign-in.png" alt="Sign-in screen" width="70%" />
</p>

**Dashboard**
<p align="center">
  <img src="docs/images/dashboard.png" alt="Dashboard screen" width="70%" />
</p>

**Profile & preferences**
<p align="center">
  <img src="docs/images/profile.png" alt="Profile and preferences screen" width="70%" />
</p>

## How it works

```
+----------------+         +----------------+         +----------------+
|    Next.js     |         |    FastAPI     |         |   MCP Server   |
|    frontend    | <------>|    backend     | <------>|   (fit_server) |
|    (Vercel)    | HTTP/SSE|  (Cloud Run)   |JWT/JWKS |  (Cloud Run)   |
+----------------+         +----------------+         +----------------+

                                    |                          |
                                    v                          v
                           +----------------+         +----------------+
                           |    Postgres    |         | Google Health  |
                           |   (Supabase)   |         |      API       |
                           +----------------+         +----------------+
```

- **Frontend** — Next.js app (dashboard, chat, connectors, profile). Talks to the backend over HTTP, streams chat responses via SSE.
- **Backend** — FastAPI. Owns user sessions (Google OAuth), the Claude tool-use chat loop, and per-user preferences/memory. Signs a short-lived JWT per request to call the MCP server on the user's behalf.
- **MCP server** — a Model Context Protocol server exposing tools (`get_runs`, `get_recent_runs`, `get_weekly_stats`, …) that fetch and aggregate a user's data from the **Google Health API**. Independently verifies the backend's JWT via a JWKS endpoint — it never trusts the backend blindly.
- **Postgres (Supabase)** — users, sessions, encrypted OAuth tokens, preferences, chat history, and long-term agent memory (facts the agent chooses to remember across conversations, e.g. "training for a half marathon in October").

**Note on the data source:** this talks to the **Google Health API** (`health.googleapis.com`), not the old Google Fit REST API — that one is closed to new developers and being fully deprecated. Google Health is backed by Fitbit's account system; a user needs data actually synced there (not just the Google Fit app) for the API to return anything.

## Tech stack

| Layer | Stack |
|---|---|
| Frontend | Next.js, TypeScript, Tailwind, shadcn/ui, next-intl (en/de), React Query |
| Backend | FastAPI, Python, Anthropic SDK (Claude), `uv` for dependency management |
| MCP server | Python, [MCP SDK](https://github.com/modelcontextprotocol) (Streamable HTTP transport) |
| Database | Postgres (Supabase), AES-256-GCM at-rest token encryption |
| Auth | Google OAuth 2.0 (identity + separate Health-data grant), RS256 JWT + JWKS for backend↔MCP auth |
| Infra | Docker, Google Cloud Run, Artifact Registry, GitHub Actions (Workload Identity Federation — no stored service account keys), Vercel |
| Observability | Langfuse (LLM call tracing) |

## Local setup

Requires [`uv`](https://docs.astral.sh/uv/) (Python) and Node.js (for the frontend).

**1. Backend + MCP server**

```bash
uv sync
```

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
DATABASE_URL=postgresql://user:password@localhost:5432/postgres
TOKEN_ENCRYPTION_KEY=
```

`DATABASE_URL` points at a Postgres instance (Supabase locally or otherwise) — the schema is created automatically on startup, no manual migration step. `TOKEN_ENCRYPTION_KEY` is a symmetric AES-256-GCM key used to encrypt OAuth tokens at rest; generate one with `openssl rand -base64 32`.

```bash
# MCP server (run first — the backend calls it per-request)
uv run python -m mcp_servers.fit_server.server

# Backend
uv run uvicorn backend.agent:app --reload
```

**2. Frontend**

```bash
cd frontend
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open `http://localhost:3000`, sign in with Google, and connect your Health data from the Connectors screen.

## Deployment

Deployed as: frontend on **Vercel**, backend + MCP server as separate **Google Cloud Run** services, built and pushed via **GitHub Actions**.

- GitHub Actions authenticates to GCP with **Workload Identity Federation** — no service account JSON key stored anywhere. A GCP Workload Identity Pool trusts GitHub's OIDC tokens, scoped to this exact repo only, and lets CI impersonate a narrowly-scoped deploy service account.
- Both services are built as Docker images (multi-stage, `uv`-based), pushed to one Artifact Registry repo, tagged by commit SHA.
- Secrets (API keys, DB URL, JWT signing keys, etc.) live in GitHub Actions repository secrets and are passed to Cloud Run as env vars at deploy time.
- The backend and MCP server communicate over a custom RS256 JWT/JWKS scheme (not OAuth) — the backend mints a short-lived JWT per request, the MCP server verifies it independently against the backend's published public key.

See `docs/superpowers/plans/2026-08-17-gcp-deployment.md` for the full deployment plan and one-time GCP setup steps (Artifact Registry, IAM, Workload Identity Federation).

## Project structure

```
strides/
├── backend/                    # FastAPI app
│   ├── agent.py                  # app entrypoint, CORS, router mounting
│   ├── routes/                   # auth, chat, dashboard, preferences, profile
│   ├── services/                 # chat loop, MCP client, auth, summarization
│   ├── jwt_issuer.py              # signs backend->MCP JWTs
│   └── encryption.py              # AES-256-GCM token encryption
├── mcp_servers/
│   └── fit_server/                # MCP server exposing Google Health tools
│       ├── server.py
│       └── mcp_auth.py             # verifies backend JWTs via JWKS
├── auth/
│   └── auth.py                    # Google OAuth token exchange/refresh
├── data/
│   └── db.py                      # Postgres schema + CRUD
├── frontend/                    # Next.js app
│   ├── app/                       # routes (dashboard, chat, connectors, profile)
│   ├── components/
│   └── lib/                       # API client, React Query hooks
├── tests/
├── docs/
│   ├── PLAN.md                    # original phased project plan
│   └── superpowers/plans/         # implementation plans (auth, frontend, GCP deploy, …)
└── .github/workflows/deploy.yml # CI/CD: build, push, deploy to Cloud Run
```

## Status

Multi-user architecture is live end-to-end, deployed, and working — auth, dashboard, chat (with tool use + long-term memory), and preferences all run against real infrastructure.

**Open / not started:** local `docker-compose` for running everything together, context-window trimming for long conversations, multi-provider OAuth beyond Health, JWKS key rotation.
