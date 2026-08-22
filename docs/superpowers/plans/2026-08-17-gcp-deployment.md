# GCP Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dockerize the FastAPI backend and MCP server, deploy both to Cloud Run in `us-central1`, and wire up a GitHub Actions pipeline (via Workload Identity Federation) that builds and deploys both on push to `main`.

**Architecture:** Two independently deployable Docker images built from the monorepo root (shared `pyproject.toml`/`uv.lock`), pushed to one Artifact Registry repo, deployed as two Cloud Run services. GitHub Actions authenticates to GCP with no stored key via WIF.

**Tech Stack:** Docker (multi-stage, `uv`), Google Artifact Registry, Cloud Run, GitHub Actions, Workload Identity Federation.

## Global Constraints

- GCP project: `strides-503723`, region: `us-central1`
- Frontend (Vercel) is out of scope — untouched by this plan
- MCP server stays coupled to the root `pyproject.toml`/`uv.lock` — no standalone split (deferred, per spec)
- Secrets passed as plain env vars from GitHub Actions secrets — no Google Secret Manager (deferred, per spec)
- No Cloud Run IAM-based service auth — inter-service auth stays at the app layer (existing JWT/JWKS) (deferred, per spec)
- Images tagged by commit SHA, never `latest`
- `--min-instances=0 --max-instances=3` on both Cloud Run services

---

### Task 1: Backend Dockerfile

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`

**Interfaces:**
- Consumes: root `pyproject.toml` / `uv.lock`, entrypoint `backend.agent:app` (FastAPI instance, confirmed at `backend/agent.py:45`)
- Produces: a runnable image that starts `uvicorn backend.agent:app` bound to `0.0.0.0:$PORT`, consumed by Task 5 (Artifact Registry push) and Task 7 (Cloud Run deploy)

- [x] **Step 1: Write `backend/.dockerignore`**

```
.venv
__pycache__
*.pyc
.git
.env
tests
.pytest_cache
.ruff_cache
frontend
node_modules
docs
```

- [x] **Step 2: Write `backend/Dockerfile`**

```dockerfile
FROM python:3.11-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.11-slim AS runtime

RUN useradd --create-home appuser
WORKDIR /app

COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

USER appuser

EXPOSE 8080
CMD ["sh", "-c", "uvicorn backend.agent:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

- [x] **Step 3: Build the image locally**

Run from repo root: `docker build -f backend/Dockerfile -t strides-backend:local .`
Expected: build completes without error, ending in `naming to docker.io/library/strides-backend:local`

- [x] **Step 4: Run the image locally to verify it boots**

```bash
docker run --rm -p 8080:8080 \
  -e DATABASE_URL="$(grep DATABASE_URL .env | cut -d= -f2-)" \
  -e ANTHROPIC_API_KEY="$(grep ANTHROPIC_API_KEY .env | cut -d= -f2-)" \
  -e TOKEN_ENCRYPTION_KEY="$(grep TOKEN_ENCRYPTION_KEY .env | cut -d= -f2-)" \
  -e GOOGLE_CLIENT_ID="$(grep GOOGLE_CLIENT_ID .env | cut -d= -f2-)" \
  -e GOOGLE_CLIENT_SECRET="$(grep GOOGLE_CLIENT_SECRET .env | cut -d= -f2-)" \
  strides-backend:local
```

Then in another terminal: `curl -i http://localhost:8080/.well-known/jwks.json`
Expected: HTTP 200 with a JSON body (the `well_known_router` route, confirms the app booted and Postgres connection via `init_db()` in `lifespan` succeeded)

- [x] **Step 5: Commit**

```bash
git add backend/Dockerfile backend/.dockerignore
git commit -m "build: add backend Dockerfile"
```

---

### Task 2: MCP server Dockerfile

**Files:**
- Create: `mcp_servers/fit_server/Dockerfile`
- Create: `mcp_servers/fit_server/.dockerignore`
- Modify: `mcp_servers/fit_server/server.py:36-38` (host/port must respect `$PORT` and bind `0.0.0.0`, not hardcoded `127.0.0.1:8001`)

**Interfaces:**
- Consumes: root `pyproject.toml`/`uv.lock`, `mcp_servers/fit_server/server.py` entrypoint (`mcp.run(transport="streamable-http")`)
- Produces: a runnable image listening on `0.0.0.0:$PORT`, consumed by Task 5 and Task 7

- [x] **Step 1: Make the server's host/port configurable**

In `mcp_servers/fit_server/server.py`, find:

```python
mcp = FastMCP(
    "strides",
    host="127.0.0.1",
    port=8001,
    token_verifier=StridesTokenVerifier(),
```

Replace with:

```python
import os

mcp = FastMCP(
    "strides",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8001)),
    token_verifier=StridesTokenVerifier(),
```

(Add the `import os` near the top of the file with the other imports if not already present.)

- [x] **Step 2: Verify locally before containerizing**

Run: `uv run python -m mcp_servers.fit_server.server` (or however it's currently started for local dev)
Expected: starts without error, still reachable at `http://127.0.0.1:8001/mcp` (default `PORT` unset locally falls back to 8001)

- [x] **Step 3: Write `mcp_servers/fit_server/.dockerignore`**

```
.venv
__pycache__
*.pyc
.git
.env
tests
.pytest_cache
.ruff_cache
frontend
node_modules
docs
```

- [x] **Step 4: Write `mcp_servers/fit_server/Dockerfile`**

```dockerfile
FROM python:3.11-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.11-slim AS runtime

RUN useradd --create-home appuser
WORKDIR /app

COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

USER appuser

EXPOSE 8080
CMD ["python", "-m", "mcp_servers.fit_server.server"]
```

- [x] **Step 5: Build the image locally**

Run from repo root: `docker build -f mcp_servers/fit_server/Dockerfile -t strides-mcp:local .`
Expected: build completes without error

- [x] **Step 6: Run the image locally to verify it boots**

```bash
docker run --rm -p 8080:8080 \
  -e PORT=8080 \
  -e DATABASE_URL="$(grep DATABASE_URL .env | cut -d= -f2-)" \
  -e TOKEN_ENCRYPTION_KEY="$(grep TOKEN_ENCRYPTION_KEY .env | cut -d= -f2-)" \
  -e GOOGLE_CLIENT_ID="$(grep GOOGLE_CLIENT_ID .env | cut -d= -f2-)" \
  -e GOOGLE_CLIENT_SECRET="$(grep GOOGLE_CLIENT_SECRET .env | cut -d= -f2-)" \
  strides-mcp:local
```

Then: `curl -i http://localhost:8080/mcp` (expect a response, e.g. 400/406 from the MCP protocol handler rejecting a bare GET — this confirms the process is listening and routing, not a connection refusal)
Expected: connection succeeds (not `curl: (7) Failed to connect`)

- [x] **Step 7: Commit**

```bash
git add mcp_servers/fit_server/Dockerfile mcp_servers/fit_server/.dockerignore mcp_servers/fit_server/server.py
git commit -m "build: add MCP server Dockerfile, make host/port configurable via PORT"
```

---

### Task 3: Cross-service URL wiring (make hardcoded URLs configurable)

**Files:**
- Modify: `backend/services/mcp_client.py:10` (`SERVER_URL` hardcoded to `http://127.0.0.1:8001/mcp`)
- Modify: `backend/agent.py:49` (`FRONTEND_URL` already env-driven — confirm it's set correctly at deploy time, no code change needed here, verification only)

**Interfaces:**
- Consumes: `MCP_SERVER_URL` env var (new)
- Produces: `SERVER_URL` used by `open_mcp_session` — must resolve to the MCP server's Cloud Run URL in production, `http://127.0.0.1:8001/mcp` in local dev

- [x] **Step 1: Make `SERVER_URL` configurable**

In `backend/services/mcp_client.py`, replace:

```python
SERVER_URL = "http://127.0.0.1:8001/mcp"
```

with:

```python
import os

SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")
```

- [x] **Step 2: Verify local dev still works unchanged**

Run the existing test suite: `uv run pytest tests/ -v -k mcp_client`
Expected: PASS (no `MCP_SERVER_URL` set in local `.env` means it falls back to the same hardcoded default as before — behavior-preserving change)

- [x] **Step 3: Commit**

```bash
git add backend/services/mcp_client.py
git commit -m "refactor: make MCP server URL configurable via MCP_SERVER_URL"
```

---

### Task 4: One-time GCP setup — Artifact Registry + Workload Identity Federation

No application files change in this task — this is `gcloud` CLI setup, run once by hand (not automated in CI, since it configures the trust relationship CI will later use).

- [x] **Step 1: Create the Artifact Registry repo**

```bash
gcloud artifacts repositories create strides \
  --project=strides-503723 \
  --repository-format=docker \
  --location=us-central1
```

Expected: `Created repository [strides].`

- [x] **Step 2: Create the deploy service account**

```bash
gcloud iam service-accounts create strides-deployer \
  --project=strides-503723 \
  --display-name="Strides GitHub Actions deployer"
```

- [x] **Step 3: Grant the service account the minimal roles it needs**

```bash
for ROLE in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding strides-503723 \
    --member="serviceAccount:strides-deployer@strides-503723.iam.gserviceaccount.com" \
    --role="$ROLE"
done
```

- [x] **Step 4: Create the Workload Identity Pool**

```bash
gcloud iam workload-identity-pools create github-pool \
  --project=strides-503723 \
  --location=global \
  --display-name="GitHub Actions pool"
```

- [x] **Step 5: Create the OIDC provider, scoped to this repo**

```bash
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --project=strides-503723 \
  --location=global \
  --workload-identity-pool=github-pool \
  --display-name="GitHub OIDC provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='sarfaraz187/strides'" \
  --issuer-uri="https://token.actions.githubusercontent.com"
```

- [x] **Step 6: Bind the pool to the service account**

```bash
gcloud iam service-accounts add-iam-policy-binding \
  strides-deployer@strides-503723.iam.gserviceaccount.com \
  --project=strides-503723 \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$(gcloud projects describe strides-503723 --format='value(projectNumber)')/locations/global/workloadIdentityPools/github-pool/attribute.repository/sarfaraz187/strides"
```

- [x] **Step 7: Record the provider resource name for the workflow**

```bash
gcloud iam workload-identity-pools providers describe github-provider \
  --project=strides-503723 \
  --location=global \
  --workload-identity-pool=github-pool \
  --format="value(name)"
```

Expected output looks like: `projects/<number>/locations/global/workloadIdentityPools/github-pool/providers/github-provider` — save this, it's needed in Task 6.

---

### Task 5: GitHub Actions workflow — build and push images

**Files:**
- Create: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: WIF provider resource name (Task 4, Step 7), service account email (`strides-deployer@strides-503723.iam.gserviceaccount.com`)
- Produces: two images pushed to Artifact Registry, consumed by Task 6 (Cloud Run deploy steps in the same workflow)

- [x] **Step 1: Write the workflow file with auth + build/push jobs**

```yaml
name: Deploy to Cloud Run

on:
  push:
    branches: [main]
    paths:
      - 'backend/**'
      - 'mcp_servers/fit_server/**'
      - 'data/**'
      - 'auth/**'
      - 'pyproject.toml'
      - 'uv.lock'

env:
  PROJECT_ID: strides-503723
  REGION: us-central1
  REPO: us-central1-docker.pkg.dev/strides-503723/strides

permissions:
  contents: read
  id-token: write

jobs:
  deploy-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: "projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
          service_account: "strides-deployer@strides-503723.iam.gserviceaccount.com"

      - uses: google-github-actions/setup-gcloud@v2

      - run: gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

      - run: |
          docker build -f backend/Dockerfile -t ${{ env.REPO }}/backend:${{ github.sha }} .
          docker push ${{ env.REPO }}/backend:${{ github.sha }}

      - run: |
          gcloud run deploy backend \
            --project=${{ env.PROJECT_ID }} \
            --region=${{ env.REGION }} \
            --image=${{ env.REPO }}/backend:${{ github.sha }} \
            --allow-unauthenticated \
            --min-instances=0 --max-instances=3 \
            --set-env-vars="DATABASE_URL=${{ secrets.DATABASE_URL }},ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }},TOKEN_ENCRYPTION_KEY=${{ secrets.TOKEN_ENCRYPTION_KEY }},GOOGLE_CLIENT_ID=${{ secrets.GOOGLE_CLIENT_ID }},GOOGLE_CLIENT_SECRET=${{ secrets.GOOGLE_CLIENT_SECRET }},FRONTEND_URL=${{ secrets.FRONTEND_URL }},MCP_SERVER_URL=${{ secrets.MCP_SERVER_URL }},LANGFUSE_SECRET_KEY=${{ secrets.LANGFUSE_SECRET_KEY }},LANGFUSE_PUBLIC_KEY=${{ secrets.LANGFUSE_PUBLIC_KEY }},LANGFUSE_BASE_URL=${{ secrets.LANGFUSE_BASE_URL }},LANGFUSE_TRACING_ENVIRONMENT=production"

  deploy-mcp-server:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: "projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
          service_account: "strides-deployer@strides-503723.iam.gserviceaccount.com"

      - uses: google-github-actions/setup-gcloud@v2

      - run: gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

      - run: |
          docker build -f mcp_servers/fit_server/Dockerfile -t ${{ env.REPO }}/mcp-server:${{ github.sha }} .
          docker push ${{ env.REPO }}/mcp-server:${{ github.sha }}

      - run: |
          gcloud run deploy mcp-server \
            --project=${{ env.PROJECT_ID }} \
            --region=${{ env.REGION }} \
            --image=${{ env.REPO }}/mcp-server:${{ github.sha }} \
            --allow-unauthenticated \
            --min-instances=0 --max-instances=3 \
            --set-env-vars="DATABASE_URL=${{ secrets.DATABASE_URL }},TOKEN_ENCRYPTION_KEY=${{ secrets.TOKEN_ENCRYPTION_KEY }},GOOGLE_CLIENT_ID=${{ secrets.GOOGLE_CLIENT_ID }},GOOGLE_CLIENT_SECRET=${{ secrets.GOOGLE_CLIENT_SECRET }},STRIDES_JWKS_URL=${{ secrets.STRIDES_JWKS_URL }}"
```

Replace `<PROJECT_NUMBER>` with the value from Task 4, Step 7's output.

- [x] **Step 2: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add GitHub Actions workflow to deploy backend and MCP server to Cloud Run"
```

(Do not push yet — Task 6 sets up the required secrets first, otherwise the first run fails on missing/empty env vars.)

---

### Task 6: GitHub repository secrets + first deploy ordering

No files change in this task — this is GitHub repo configuration (Settings → Secrets and variables → Actions) plus the first manual deploy to break the URL chicken-and-egg problem described in the spec.

- [x] **Step 1: Add repository secrets**

Add each of these (values copied from local `.env`, `git.log-visible` values excluded):
`DATABASE_URL`, `ANTHROPIC_API_KEY`, `TOKEN_ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_BASE_URL`

- [x] **Step 2: First-deploy the MCP server manually to obtain its URL**

Push only `mcp_servers/fit_server/**` changes first (or temporarily comment out the `deploy-backend` job), so `deploy-mcp-server` runs and Cloud Run assigns it a URL:

```bash
gcloud run services describe mcp-server --project=strides-503723 --region=us-central1 --format="value(status.url)"
```

- [x] **Step 3: Add the remaining URL-dependent secrets**

Add `MCP_SERVER_URL` (from Step 2's output, with `/mcp` appended — matching the local `http://127.0.0.1:8001/mcp` shape) and `FRONTEND_URL` (the Vercel deployment URL).

After the backend's first deploy, get its URL the same way and add `STRIDES_JWKS_URL` as `<backend-url>/.well-known/jwks.json`.

- [x] **Step 4: Push to trigger a full pipeline run**

Push any change matching the workflow's path filters (or an empty commit touching `backend/Dockerfile`) to run both jobs end-to-end now that all secrets exist.

---

### Task 7: End-to-end validation

No files change — this is manual verification that the deployed system actually works.

- [x] **Step 1: Confirm the backend is reachable**

```bash
curl -i https://<backend-cloud-run-url>/.well-known/jwks.json
```

Expected: HTTP 200, JSON body

- [x] **Step 2: Confirm the MCP server is reachable and can verify a JWT from the deployed backend**

Send a real chat message through the deployed frontend (pointed at the deployed backend URL) that requires a tool call, e.g. "how was my run yesterday."
Expected: a real answer referencing actual run data — confirms backend → MCP server → Google Health API → Claude → response all work end-to-end in the cloud.

- [ ] **Step 3: Confirm Langfuse traces show the deployed environment**

Check the Langfuse UI (Tracing table) for a new trace tagged `Env: production` (from `LANGFUSE_TRACING_ENVIRONMENT=production` set in Task 5's deploy step) — confirms production traffic is distinguishable from local dev traces per the spec's testing section.

---

## Self-Review Notes

- **Spec coverage:** Docker (Tasks 1-2), Artifact Registry (Task 4), WIF (Task 4), GitHub Actions workflow (Task 5), env vars/secrets (Task 6), cross-service wiring — CORS/MCP URL/JWKS (Task 3 + Task 6), first-deploy ordering (Task 6), validation (Task 7). All spec sections covered.
- **Type consistency:** `SERVER_URL`/`MCP_SERVER_URL` naming consistent between Task 3 (code) and Task 5/6 (secret name). `STRIDES_JWKS_URL` matches the existing env var name already read by `mcp_auth.py:9`, not a new invented name.
- **Placeholder scan:** `<PROJECT_NUMBER>` in Task 5 is a real substitution the implementer fills in from Task 4's actual output, not a vague TODO — flagged inline with instructions on where the value comes from.
