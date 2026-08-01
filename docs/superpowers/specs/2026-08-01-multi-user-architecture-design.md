# Strides — Architecture

Decided in architecture discussion, 2026-08-01. Reflects the target state for the
multi-user pivot described in `PLAN.md`. `AUTH_IMPLEMENTATION.md` covers the build plan
for the auth layer specifically; this file is the overall system picture it fits into.

## Deployment model

Open source, supports two usage modes on the same codebase — no branching logic, one
deployment serves N users (N=1 for self-hosters):

- **Hosted**: runs on the author's GCP account, anyone can use it via the web frontend.
- **Self-hosted**: anyone clones the repo, runs their own instance (own GCP/Supabase/
  wherever, own Google OAuth credentials, own `.env`).

## Components

| Component | Where it runs | Deployment unit |
|---|---|---|
| Frontend | Vercel | separate, not yet built |
| Backend (`backend/`) | GCP Cloud Run | own Dockerfile, own Cloud Run service |
| MCP server (`mcp_servers/fit_server/`) | GCP Cloud Run | own Dockerfile, own Cloud Run service, separate from backend |
| Database | Supabase Postgres (free tier) | external managed service |

Backend and MCP server are deliberately separate deployable units (justified by a real
constraint — see `PLAN.md`'s "Confirmed target architecture" section — not preference).
The frontend only ever talks to the backend; it never calls the MCP server directly.

## Why Supabase over Cloud SQL

Cloud SQL has no free tier — smallest instance still costs money 24/7 regardless of
actual usage. Supabase free tier (500MB DB, unlimited API requests, 50k MAU) is
sufficient at personal/early-open-source scale and costs $0. Same Postgres underneath
either way (no lock-in) — only the connection string changes if this is ever migrated.
Caveat: Supabase free-tier projects pause after 1 week of inactivity; acceptable for
personal use (the one person hitting it is also the one who left it idle), would need
Supabase Pro ($25/mo) if the hosted instance needs to guarantee uptime for others.

## Request flow: Frontend → Backend → MCP

```
User sends message
        │
        ▼
Frontend (Vercel) — attaches session cookie (httpOnly, opaque token)
        │
        ▼
Backend /chat (Cloud Run, stateless instance)
  1. read session cookie → look up `sessions` table → resolve user_id
     (reject if missing/expired)
  2. load conversation history for this user from `messages` table
  3. look up `oauth_tokens` row (user_id, provider="health") → decrypt access_token
     (refresh via refresh_token first if expired)
  4. build prompt: system + past messages + new message
  5. call Claude
        │
        ▼ (if Claude requests a tool)
  MCP fit_server (separate Cloud Run service)
     receives plaintext Google token as a call parameter
     calls Google Health API directly
     returns tool result to backend
        │
        ▼
  6. Claude produces final reply
  7. save new user message + assistant reply → messages table
        │
        ▼
Response returned to frontend, shown to user
```

Key point: the backend Cloud Run instance holds no state between requests. Continuity
(conversation history, identity, tokens) all comes from Postgres round-trips, not
in-memory session state — this is what makes stateless/scale-to-zero compute viable.

The MCP server never touches Postgres and never sees encrypted tokens — it only
receives a plaintext token as a call argument for the duration of one request, which
keeps the trust boundary (decrypt authority) at the backend.

## Authentication

Two separate OAuth purposes, not one combined consent flow (Option B — decided over
Option A specifically so a user can be logged in without having granted Health access,
and so future data sources can be connected independently later):

1. **App login** — Google identity scopes only (`openid email profile`). Establishes
   who the user is in Strides.
2. **Health connect** — separate consent, `googlehealth.activity_and_fitness.readonly`
   scope. Requires an existing valid session. Optional / can happen later than login.

Session mechanism: **opaque random token + `sessions` table lookup**, sent as an
httpOnly cookie — not JWT. Chosen because a DB round-trip is already required (Google
tokens live there too), real revocation matters (logout must take effect immediately),
and request volume doesn't justify JWT's stateless-verification tradeoff (would need a
blocklist to get revocation back, which defeats the point of being stateless).

### Token lifetimes

| Token | Lifetime | Renewal |
|---|---|---|
| App session (`sessions.expires_at`) | days-to-weeks (implementer's choice) | re-login, or sliding expiry on activity |
| Google `access_token` | ~1 hour | silently refreshed via `refresh_token` (existing logic in `auth/auth.py`) |
| Google `refresh_token` | 7 days while OAuth app is in "Testing" publish status; effectively indefinite once "In Production" (until revoked or 6mo unused) | re-consent flow if expired/revoked (`invalid_grant`) |

### Revocation — two distinct actions

- **Logout** (`POST /auth/logout`): deletes the `sessions` row only. Kills the app
  login immediately. Health connection (`oauth_tokens`) is left intact, so the user
  doesn't have to re-consent to Health access on next login.
- **Disconnect Health** (separate action, not tied to logout): revokes the token with
  Google's revoke endpoint and deletes the `oauth_tokens` row. This is the actual
  "remove my Health access" action.

## Data model (Supabase Postgres)

All tables scoped by `user_id`, one DB, no separate memory infra (no vector store —
evaluated and explicitly not needed for this project's scope):

- `users` — id, email, google_sub, created_at
- `sessions` — token (PK), user_id, created_at, expires_at
- `oauth_tokens` — id, user_id, provider, access_token (encrypted), refresh_token
  (encrypted), expires_at — one row per (user, provider), supports adding non-Health
  providers later without schema change
- `preferences` — long-term facts/settings about the user (not yet built)
- `goals` — explicit user-set targets, e.g. "sub-2hr half marathon" (Phase 3, not built)
- `conversations` / `messages` — chat history, append-only (not yet built)

## Token encryption

`access_token` / `refresh_token` are never stored in plaintext. AES-256-GCM at the app
layer, key from `TOKEN_ENCRYPTION_KEY` env var — encrypted before every write, decrypted
only at the point of use (calling Health API, or refreshing). Same code path for
self-hosters (raw env var in their own `.env`) and the hosted instance (env var sourced
from GCP Secret Manager). Optional hardening on the hosted instance only: wrap the
symmetric key with GCP KMS (envelope encryption) instead of storing it raw in Secret
Manager — not required for self-hosters to replicate.

## Context window management (not yet implemented)

Sending full conversation history on every request doesn't scale — hits the model's
context window and risks hallucination from stale/irrelevant context. Decided approach
when this becomes necessary:

- Scope conversations more tightly (new `conversation_id` per session/day rather than
  one infinite thread), so history sent per-request stays bounded by default.
- Long-term facts come from `preferences` / `goals` tables, not from scrollback — so
  raw message history only needs to cover the current session, not all-time context.
- Summarization (collapse older messages into a stored running summary) only if a
  single session itself gets long enough to need it.

Explicitly rejected: a bare sliding window alone (silently drops context with no
signal), and Redis as a fix (Redis addresses latency/DB load, not context-window size
or content relevance — orthogonal problem).

## Cost estimate (personal-scale usage)

- Cloud Run (backend + MCP server, 2 services): ~$0-5/mo (free tier covers light
  traffic, scale-to-zero when idle)
- Supabase (Postgres): $0/mo (free tier)
- Secret Manager: ~$0/mo (free tier)
- Google OAuth / Health API: $0 (no usage cost at this scale)

Total: roughly **$0-5/month** at current expected usage (personal use, low traffic).
Cloud SQL was evaluated and rejected specifically because of its ~$10-20/mo baseline
with no free tier, which isn't justified without real multi-user traffic.

## Explicitly deferred / out of scope for now

- Frontend implementation (Vercel) — architecture assumes it, not built yet
- Dockerfiles / docker-compose for backend + MCP server — separate task from auth layer
- `preferences`, `goals`, `conversations`/`messages` tables — memory/Phase 3 work
- Vector embeddings / semantic memory — evaluated, not needed for this project's scope
- Redis caching layer — legitimate future latency optimization, not a fix for context
  window growth, not needed yet
- Multi-provider OAuth beyond Health (e.g. Strava) — schema supports it
  (`oauth_tokens.provider`) but no second provider is being built now
