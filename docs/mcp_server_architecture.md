# Strides — MCP Server Authentication Architecture

**Purpose:** Migrate Strides' MCP server from single-user (stdio, hardcoded token) to multi-tenant (HTTP, per-user auth), following the pattern used by production MCP servers (Apollo GraphQL, monday.com).

---

## 1. High-Level Architecture

```
┌─────────────┐   Sign in with Google (identity)   ┌──────────────┐
│   Frontend   │ ──────────────────────────────────▶ │   FastAPI     │
│  (Strides UI)│                                      │   Backend     │
└─────────────┘                                      └──────┬───────┘
       │                                                     │
       │  "Connect Google Health" button (optional, later)   │
       └─────────────────────────────────────────────────────┤
                                                               ▼
                                                        ┌──────────────┐
                                                        │  PostgreSQL   │
                                                        │  users        │
                                                        │  google_tokens│
                                                        └──────┬───────┘
                                                               │
┌─────────────┐   Bearer <google_id_token>          ┌────────▼───────┐
│  AI Agent    │ ────────────────────────────────────▶│   MCP Server   │
│ (Strides or  │                                       │  (HTTP, state- │
│ 3rd-party    │◀──────────────────────────────────────│  less re: DB) │
│ client)      │        tool results                   └────────┬───────┘
└─────────────┘                                                 │
                                                                  ▼
                                                          ┌───────────────┐
                                                          │ Google Health  │
                                                          │      API       │
                                                          └───────────────┘
```

**Core principle:** Two independent OAuth grants, two independent lifecycles, one shared identity.

| Concern                       | Owner                                            | Token type                                                                             |
| ----------------------------- | ------------------------------------------------ | -------------------------------------------------------------------------------------- |
| "Who is this user?"           | FastAPI backend + Google Sign-In                 | `id_token` (short-lived, scope: `openid email profile`)                                |
| "Can we read their run data?" | FastAPI backend (issues) + MCP server (consumes) | `refresh_token` / `access_token` (scope: `googlehealth.activity_and_fitness.readonly`) |

These are **never merged**. The agent only ever holds and transmits the `id_token`. The MCP server never receives, stores, or forwards a Health API token from the agent — it resolves that internally via Postgres.

---

## 2. Why This Design (Industry Validation)

Researched via Apollo MCP Server and monday.com MCP Server docs:

- **monday.com**: MCP server explicitly does **not** store or log OAuth tokens — token lifecycle (storage, rotation, revocation) is the client/developer's responsibility. Their MCP server validates the bearer token per-request and is otherwise stateless.
- **Apollo**: Same statelessness, but currently does **token passthrough** (forwards the client's token directly upstream) — which Apollo's own docs flag as a security limitation they plan to move away from, toward per-user token resolution (our model).

**Conclusion:** Our design (MCP server stateless re: token storage, backend owns persistence, per-user resolution via `user_id`) is the more secure pattern of the two, and the direction Apollo itself is migrating toward.

**Why we can't do simple passthrough like monday.com currently does:** monday.com's OAuth token for MCP access _is_ their platform API token — one system, one hop. Our case has two separate OAuth grants from two different scope sets (identity vs. Health data) that must persist independently across sessions. Passthrough isn't applicable here.

---

## 3. Component Responsibilities

### 3.1 FastAPI Backend (owns all OAuth consent flows)

**Never** touches MCP protocol. Purely handles browser-based OAuth redirects/callbacks.

**Endpoint 1 — Sign in (mandatory, day one):**

```
GET /auth/google
  → redirect to Google consent screen
  → scope: openid email profile

GET /auth/google/callback?code=...
  → exchange code for id_token
  → upsert row in `users` table (id, email, google_sub)
  → start Strides session
```

**Endpoint 2 — Connect Google Health (optional, user-triggered, anytime):**

```
GET /connect/google-health
  → redirect to Google consent screen
  → scope: googlehealth.activity_and_fitness.readonly

GET /connect/google-health/callback?code=...
  → exchange code for refresh_token
  → upsert row in `google_tokens` (user_id FK, refresh_token, scope, connected_at)
```

Note: a user can exist in `users` with **no row** in `google_tokens` — this is the expected "signed in but not connected" state and must be handled gracefully everywhere downstream.

### 3.2 PostgreSQL Schema

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    google_sub TEXT UNIQUE NOT NULL,   -- Google's stable user identifier
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE google_tokens (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    refresh_token TEXT NOT NULL,
    scope TEXT NOT NULL,
    connected_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id)
);
```

Only the long-lived `refresh_token` is persisted. `access_token`s are always fetched live from Google at call time (they expire ~1hr) and are never written to disk long-term.

### 3.3 MCP Server (`fit_server.py`, FastMCP)

**Transport:** switch from `stdio` to `streamable-http`.

**Auth middleware (runs before every tool call):**

```python
from google.oauth2 import id_token
from google.auth.transport import requests as grequests

GOOGLE_CLIENT_ID = "your-client-id.apps.googleusercontent.com"

def verify_request(bearer_token: str) -> str:
    """Returns the verified user's Google `sub`, or raises on invalid token."""
    idinfo = id_token.verify_oauth2_token(
        bearer_token, grequests.Request(), GOOGLE_CLIENT_ID
    )
    return idinfo["sub"]
```

`verify_oauth2_token` auto-discovers Google's public signing keys via Google's well-known OIDC discovery endpoint — no manual key management needed. This is the functional equivalent of Apollo's config-driven `auth.servers: [https://accounts.google.com]`, expressed in code since FastMCP doesn't have a declarative auth-server config block.

**Internal helper (NOT an MCP tool — private, never exposed to the agent):**

```python
def get_google_health_client(user_id: str):
    row = db.query(
        "SELECT refresh_token FROM google_tokens WHERE user_id = %s", (user_id,)
    )
    if not row:
        return None  # user hasn't connected Health yet
    return build_google_client(row.refresh_token)  # handles access_token refresh internally
```

**MCP tools (what the agent actually sees and calls):**

```python
@mcp.tool()
def get_recent_runs(days: int) -> dict:
    """Get the user's recent runs from Google Health."""
    client = get_google_health_client(current_user_id)  # from verified bearer token
    if client is None:
        return {"error": "Google Health not connected. Ask the user to connect it in their dashboard."}
    return client.fetch_runs(days)
```

**Key architectural rule:** the agent only ever sees tool names like `get_recent_runs`, `set_goal`, `log_run`. It never sees, calls, or has access to `get_google_health_client`, `verify_request`, or any DB/token logic. That entire layer is invisible plumbing inside the MCP server.

### 3.4 Agent

- Holds the user's `id_token` (obtained via the Strides session/login)
- Sends it as `Authorization: Bearer <id_token>` on every MCP request
- Never touches Google Health tokens, refresh logic, or the database in any way
- Handles the "not connected" tool response conversationally (prompts user to connect via dashboard)

---

## 4. Request-Time Sequence (Steady State)

```
1. Agent → MCP server: Authorization: Bearer <id_token>
2. MCP server verifies id_token signature via Google's public keys → extracts `sub`
3. MCP server queries Postgres: google_tokens WHERE user_id = sub
4a. Not found → tool returns "not connected" message
4b. Found → check cached access_token validity
5. If access_token expired → exchange refresh_token for new access_token (Google call)
6. Call Google Health API with valid access_token
7. Return tool result to agent
```

**Note:** the `id_token` is verified on every request, but this never triggers a database write — it's pure identity verification. Only the Health `access_token` involves a live Google exchange, and only when actually expired (not per-request).

---

## 5. New User Flow

```
1. New user signs in → FastAPI creates row in `users` (no google_tokens row yet)
2. Agent already has a valid id_token for this user — no special handling needed
3. User chats → MCP tools return "not connected" (expected, not an error)
4. User clicks "Connect Google Health" whenever they choose → FastAPI OAuth flow → google_tokens row created
5. All subsequent MCP calls succeed normally
```

There is no separate "new user" code path in the MCP server — the same lookup-and-check logic handles both cases uniformly.

---

## 6. Multi-Tenancy / Reusability Model

This MCP server is designed as **one hosted service** that multiple Strides users/clients connect to — the same model as `mcp.apollo.io` or `mcp.monday.com`. It is **not** designed to be forked/self-hosted with swappable databases; the Postgres implementation is internal infrastructure, invisible to any client.

- Any client (Strides web agent, future mobile app, third-party integrations) can connect, as long as they present a valid Google-issued `id_token` for a real Strides user.
- The database technology (Postgres) is an implementation detail with zero bearing on clients — they never interact with it directly, directly or indirectly.
- If self-hostable/open-source distribution is ever desired, the token-storage layer would need to be abstracted behind an interface (`TokenStore`) — **out of scope for current build.**

---

## 7. Explicitly Rejected Approaches (and why)

| Approach                                                  | Why rejected                                                                                                                                                          |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Auth0 / WorkOS as identity provider                       | Unnecessary extra hop — Google Sign-In already is a full OAuth 2.1 IdP; no need for a second layer since we only support Google login                                 |
| Custom Strides-signed JWT for MCP auth                    | Adds signing/key management burden for no benefit when Google's `id_token` already serves this purpose                                                                |
| Token passthrough (agent's token forwarded to Google API) | The agent's `id_token` and Google Health's `access_token` come from different scopes/consents — not interchangeable. Also flagged as a security risk by Apollo itself |
| MCP server stores/logs OAuth tokens                       | Contradicts both Apollo and monday.com's production practice; violates least-privilege/separation of concerns                                                         |

---

## 8. Build Checklist

- [ ] Google Cloud Console: add `openid email profile` scopes; add production redirect URI; move consent screen Testing → Production (also resolves 7-day refresh token expiry in testing mode)
- [ ] Postgres: create/migrate `users` and `google_tokens` tables per schema above
- [ ] FastAPI: implement `/auth/google` (+ callback) and `/connect/google-health` (+ callback)
- [ ] MCP server: switch `mcp.run(transport=...)` from stdio to `streamable-http`
- [ ] MCP server: add bearer-token verification middleware (`verify_oauth2_token`)
- [ ] MCP server: refactor tools to use `current_user_id` from verified token; add "not connected" handling
- [ ] Agent: update to call MCP over HTTP with `Authorization: Bearer <id_token>` header per request
