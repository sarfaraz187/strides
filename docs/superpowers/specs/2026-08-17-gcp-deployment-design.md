# GCP Deployment Design

## Goal

Deploy the FastAPI backend and the MCP server (`mcp_servers/fit_server`) to Google Cloud Run, with GitHub Actions building and deploying both on push to `main`. The Next.js frontend stays on Vercel and is out of scope — Vercel's own git integration continues to handle it.

GCP project: `strides-503723` (has free trial credits; OAuth client already configured here — see `CLAUDE.md`).

## Scope

In scope:
- Dockerize `backend` and `mcp_servers/fit_server` as two separate images
- Push images to Artifact Registry
- Deploy both as Cloud Run services in `us-central1`
- GitHub Actions workflow authenticating via Workload Identity Federation (no long-lived service account keys)
- Wiring env vars/secrets from GitHub Actions secrets into each Cloud Run service
- CORS + inter-service URL wiring (backend ↔ MCP server, backend ↔ Vercel frontend)

Out of scope (explicitly deferred):
- Making the MCP server a standalone project with its own dependency set/lockfile — for now it stays coupled to the root `pyproject.toml`/`uv.lock`. This is a future refactor, not part of this deployment.
- Google Secret Manager — secrets are passed as plain env vars sourced from GitHub Actions secrets, not GSM-managed. (Revisit if secret count/rotation needs grow.)
- Cloud Run IAM-based service-to-service auth (relying on the existing app-level JWT/JWKS scheme instead for now).

## Architecture

```
GitHub push to main
      │
      ▼
GitHub Actions workflow (path-filtered)
      │
      ├── auth to GCP via Workload Identity Federation (OIDC, no stored key)
      │
      ├── job: deploy-backend (if backend/**, data/**, auth/**, pyproject.toml, uv.lock changed)
      │       docker build (repo root context, backend/Dockerfile)
      │       → push to Artifact Registry (tag: commit SHA)
      │       → gcloud run deploy backend
      │
      └── job: deploy-mcp-server (if mcp_servers/fit_server/**, data/**, pyproject.toml, uv.lock changed)
              docker build (repo root context, mcp_servers/fit_server/Dockerfile)
              → push to Artifact Registry (tag: commit SHA)
              → gcloud run deploy mcp-server

Runtime:
  Vercel frontend  ──HTTPS──>  Cloud Run: backend  ──HTTPS──>  Cloud Run: mcp-server
                                     │                                │
                                     └──────── JWKS fetch ◄───────────┘
                                     (mcp-server verifies backend-issued JWT)
                                     │
                                     ▼
                                Supabase Postgres (external, unaffected by this deploy)
```

## Components

### 1. Docker

Two Dockerfiles, both using the **repo root** as build context (both services import shared code — `data/db.py`, `auth/`, `logging_config.py` — from the monorepo root):

- `backend/Dockerfile` — multi-stage `uv`-based build, runs `uvicorn backend.main:app` bound to `$PORT`
- `mcp_servers/fit_server/Dockerfile` — multi-stage `uv`-based build, runs the MCP server's entrypoint bound to `$PORT`

Both stages: builder installs deps via `uv sync --frozen`, runtime stage copies the resulting venv + source, non-root user, `CMD` respects `$PORT` (Cloud Run injects this at runtime — must not hardcode a port).

### 2. Artifact Registry

One Docker repository, two image paths, tagged by commit SHA (not `latest`) for traceability/rollback:

```
us-central1-docker.pkg.dev/strides-503723/strides/backend:<sha>
us-central1-docker.pkg.dev/strides-503723/strides/mcp-server:<sha>
```

### 3. Workload Identity Federation (one-time setup, via `gcloud`, not part of the recurring workflow)

- Workload Identity Pool + GitHub OIDC provider, scoped to `sarfaraz187/strides`
- Deploy service account with minimal roles: `roles/run.admin`, `roles/artifactregistry.writer`, `roles/iam.serviceAccountUser`
- IAM binding attaching the pool to that service account

### 4. GitHub Actions workflow

Single workflow file, triggered on push to `main`, path-filtered:

```yaml
paths:
  - 'backend/**'
  - 'mcp_servers/fit_server/**'
  - 'data/**'
  - 'auth/**'
  - 'pyproject.toml'
  - 'uv.lock'
```

Two independent jobs (`deploy-backend`, `deploy-mcp-server`), each: WIF auth → `docker build` → push → `gcloud run deploy` with `--set-env-vars` populated from GitHub Actions secrets.

Per-service deploy flags:
- `--region us-central1 --platform managed`
- `--allow-unauthenticated` (both services — MCP server auth is handled at the app layer via JWT, not Cloud Run IAM, for now)
- `--min-instances=0 --max-instances=3` (scale to zero between requests; capped low since this is a personal app)

### 5. Env vars / secrets

Sourced 1:1 from the current `.env`: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_BASE_URL`, `LANGFUSE_TRACING_ENVIRONMENT` (set to `production` for the deployed service), `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, encryption key, and any others `backend`/`mcp_servers/fit_server` currently read from the environment. Stored as GitHub Actions repository secrets, passed via `--set-env-vars` at deploy time — no Google Secret Manager for now.

### 6. Cross-service wiring

- **CORS**: backend's allowed-origins list needs the deployed Vercel frontend URL added (currently dev-only, likely `localhost`)
- **Backend → MCP server URL**: backend needs `MCP_SERVER_URL` set to the MCP server's Cloud Run URL. First-deploy ordering: MCP server must deploy first so its URL exists to feed into the backend's env vars; stable across future redeploys since Cloud Run URLs don't change once the service exists.
- **JWKS reachability**: MCP server's existing JWT verification (`mcp_servers/fit_server/mcp_auth.py`) fetches the backend's `/.well-known/jwks.json` — needs to resolve to the backend's public Cloud Run URL instead of localhost.
- **Health check**: Cloud Run's default startup probe hits `/` — confirm FastAPI responds there (add a trivial health route if not), or configure a custom startup probe path.

## Error handling / edge cases

- **First deploy ordering**: MCP server deploys before backend (backend depends on its URL). Subsequent deploys can happen in any order/parallel since URLs are stable.
- **Path-filtered jobs on unrelated changes**: a frontend-only commit triggers neither job (paths don't match) — confirmed acceptable since Vercel handles frontend separately.
- **Shared-code changes** (`data/**`, `auth/**`): trigger both jobs, since both services depend on this code.
- **Rollback**: since images are tagged by commit SHA, rollback = `gcloud run services update-traffic --to-revisions=<previous-sha>=100` rather than reverting git and redeploying.

## Testing

No new application logic is introduced — this is deployment infrastructure. Validation is manual/operational:
- Local `docker build` + `docker run` for both images before wiring up Actions, confirming both boot and respond on `$PORT`
- First real deploy verified by hitting the backend's public health endpoint and sending a real chat message end-to-end (backend → MCP server → Health API → Claude → response)
- Confirm Langfuse traces appear tagged `LANGFUSE_TRACING_ENVIRONMENT=production` for the deployed service, distinguishing them from local dev traces
