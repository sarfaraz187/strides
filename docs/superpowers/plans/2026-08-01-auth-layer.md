# Auth Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-user SQLite/CLI-paste auth with a multi-tenant auth layer on Supabase Postgres — separate app-login and Health-connect OAuth flows, encrypted Google tokens, opaque-token sessions — per `docs/superpowers/specs/2026-08-01-multi-user-architecture-design.md`.

**Architecture:** FastAPI routes for `/auth/login`, `/auth/callback`, `/auth/health/connect`, `/auth/health/callback`, `/auth/logout` sit alongside the existing `backend/routes/chat.py`. A `data/db.py` rewrite backs everything with Postgres (Supabase). A new `backend/encryption.py` wraps AES-256-GCM for token-at-rest encryption. A FastAPI dependency resolves the session cookie to a `user_id` on every protected route.

**Tech Stack:** FastAPI, `psycopg[binary]` (sync Postgres client, matching the existing sync `sqlite3` style in `data/db.py`), `cryptography` (AES-256-GCM), Supabase Postgres, `pytest`.

## Global Constraints

- Session mechanism is opaque random token + `sessions` table lookup — not JWT (per spec's Authentication section).
- Two separate OAuth flows: app login (identity scopes only) and Health connect (Health scope, requires existing session) — not combined.
- `access_token` / `refresh_token` in `oauth_tokens` must never be written to Postgres unencrypted.
- MCP server verifies its own bearer token and independently resolves the user's Health token from Postgres.
- All new tables scoped by `user_id`.

---

## Task 1: Dependencies and environment ✅ DONE

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example` (create if it doesn't exist, based on current `.env` usage in `auth/auth.py`)

**Interfaces:**
- Produces: `DATABASE_URL`, `TOKEN_ENCRYPTION_KEY` env vars, available to all later tasks via `os.environ`.

- [x] **Step 1: Add dependencies**

Run:
```bash
uv add "psycopg[binary]" cryptography
```

- [x] **Step 2: Add a test-database dependency group entry**

Edit `pyproject.toml`, under `[dependency-groups] dev`, no change needed — `pytest` already present. Confirm `psycopg` and `cryptography` now appear under `[project] dependencies`.

- [x] **Step 3: Document new env vars**

Read the current `.env` usage:
```bash
grep -rn "os.environ" auth/ backend/ mcp_servers/
```

Create or update `.env.example` with:
```
ANTHROPIC_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
DATABASE_URL=postgresql://user:password@host:5432/postgres
TOKEN_ENCRYPTION_KEY=
```

- [x] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock .env.example
git commit -m "chore: add psycopg and cryptography dependencies"
```

---

## Task 2: Token encryption module ✅ DONE

**Files:**
- Create: `backend/encryption.py`
- Test: `tests/backend/test_encryption.py`

**Interfaces:**
- Produces: `encrypt(plaintext: str) -> str`, `decrypt(ciphertext: str) -> str`. Both read the key from `os.environ["TOKEN_ENCRYPTION_KEY"]` (base64-encoded 32-byte key) at call time.
- Consumes: nothing from other tasks.

- [x] **Step 1: Write the failing tests**

```python
# tests/backend/test_encryption.py
import base64
import os

import pytest

from backend.encryption import decrypt, encrypt


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key)


def test_encrypt_then_decrypt_returns_original():
    plaintext = "ya29.a0AfH6SMC_example_access_token"
    ciphertext = encrypt(plaintext)

    assert ciphertext != plaintext
    assert decrypt(ciphertext) == plaintext


def test_encrypt_is_nondeterministic():
    plaintext = "same-input"
    assert encrypt(plaintext) != encrypt(plaintext)


def test_decrypt_rejects_tampered_ciphertext():
    ciphertext = encrypt("secret-value")
    tampered = ciphertext[:-4] + ("AAAA" if ciphertext[-4:] != "AAAA" else "BBBB")

    with pytest.raises(Exception):
        decrypt(tampered)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/backend/test_encryption.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.encryption'`

- [x] **Step 3: Implement the module**

```python
# backend/encryption.py
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_SIZE = 12


def _load_key() -> bytes:
    encoded_key = os.environ["TOKEN_ENCRYPTION_KEY"]
    return base64.urlsafe_b64decode(encoded_key)


def encrypt(plaintext: str) -> str:
    key = _load_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_SIZE)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    key = _load_key()
    aesgcm = AESGCM(key)
    raw = base64.urlsafe_b64decode(ciphertext)
    nonce, encrypted = raw[:NONCE_SIZE], raw[NONCE_SIZE:]
    plaintext = aesgcm.decrypt(nonce, encrypted, None)
    return plaintext.decode("utf-8")
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/backend/test_encryption.py -v`
Expected: PASS (3 tests)

- [x] **Step 5: Commit**

```bash
git add backend/encryption.py tests/backend/test_encryption.py
git commit -m "feat: add AES-256-GCM token encryption module"
```

---

## Task 3: Postgres connection and schema ✅ DONE (verified against real Supabase Postgres, session pooler)

**Files:**
- Modify: `data/db.py` (replace `sqlite3` implementation entirely)
- Test: `tests/data/test_db.py`

**Interfaces:**
- Produces: `init_db() -> None`, `get_connection() -> psycopg.Connection` (reads `DATABASE_URL` from env per call, no module-level connection so tests can point at a test DB via `monkeypatch`).
- Consumes: `DATABASE_URL` env var (Task 1).

**Setup note for whoever implements this:** tests in this task and Task 4/5 run against a real Postgres. Point `DATABASE_URL` at a throwaway Supabase project or local Postgres via docker: `docker run -e POSTGRES_PASSWORD=test -p 5432:5432 postgres:16` then `DATABASE_URL=postgresql://postgres:test@localhost:5432/postgres`.

- [x] **Step 1: Write the failing test**

```python
# tests/data/test_db.py
import os

import psycopg
import pytest

from data.db import get_connection, init_db


@pytest.fixture(autouse=True)
def clean_schema():
    init_db()
    yield
    with get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS oauth_tokens CASCADE")
        conn.execute("DROP TABLE IF EXISTS sessions CASCADE")
        conn.execute("DROP TABLE IF EXISTS users CASCADE")
        conn.commit()


def test_init_db_creates_users_table():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users'"
        ).fetchall()
    columns = {row[0] for row in result}
    assert columns == {"id", "email", "google_sub", "created_at"}


def test_init_db_creates_sessions_table():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'sessions'"
        ).fetchall()
    columns = {row[0] for row in result}
    assert columns == {"token", "user_id", "created_at", "expires_at"}


def test_init_db_creates_oauth_tokens_table():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'oauth_tokens'"
        ).fetchall()
    columns = {row[0] for row in result}
    assert columns == {
        "id",
        "user_id",
        "provider",
        "access_token",
        "refresh_token",
        "expires_at",
    }


def test_init_db_is_idempotent():
    init_db()
    init_db()  # must not raise
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/data/test_db.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_connection' from 'data.db'`

- [x] **Step 3: Implement schema and connection**

```python
# data/db.py
import os

import psycopg


def get_connection() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"])


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email TEXT UNIQUE NOT NULL,
                google_sub TEXT UNIQUE NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ DEFAULT now(),
                expires_at TIMESTAMPTZ NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at BIGINT NOT NULL,
                UNIQUE (user_id, provider)
            )
        """)
        conn.commit()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/data/test_db.py -v`
Expected: PASS (4 tests) — confirmed passing against real Supabase Postgres.

- [x] **Step 5: Commit**

```bash
git add data/db.py tests/data/test_db.py
git commit -m "feat: replace SQLite with Postgres schema (users, sessions, oauth_tokens)"
```

---

## Task 4: User and session CRUD ✅ DONE (verified passing against real Supabase Postgres)

**Files:**
- Modify: `data/db.py`
- Test: `tests/data/test_db.py`

**Interfaces:**
- Consumes: `get_connection()` (Task 3)
- Produces: `find_or_create_user(email: str, google_sub: str) -> str` (returns `user_id`), `create_session(user_id: str, expires_at: datetime) -> str` (returns opaque token), `get_session_user_id(token: str) -> str | None`, `delete_session(token: str) -> None`.

- [x] **Step 1: Write the failing tests**

```python
# append to tests/data/test_db.py
import secrets
from datetime import datetime, timedelta, timezone

from data.db import (
    create_session,
    delete_session,
    find_or_create_user,
    get_session_user_id,
)


def test_find_or_create_user_creates_new_user():
    user_id = find_or_create_user("runner@example.com", "google-sub-123")
    assert user_id is not None


def test_find_or_create_user_returns_same_id_for_existing_sub():
    first_id = find_or_create_user("runner@example.com", "google-sub-123")
    second_id = find_or_create_user("runner@example.com", "google-sub-123")
    assert first_id == second_id


def test_create_session_then_get_session_user_id_round_trips():
    user_id = find_or_create_user("runner@example.com", "google-sub-123")
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    token = create_session(user_id, expires_at)
    resolved_user_id = get_session_user_id(token)

    assert resolved_user_id == user_id


def test_get_session_user_id_returns_none_for_unknown_token():
    assert get_session_user_id(secrets.token_urlsafe(32)) is None


def test_get_session_user_id_returns_none_for_expired_session():
    user_id = find_or_create_user("runner@example.com", "google-sub-123")
    expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    token = create_session(user_id, expired_at)

    assert get_session_user_id(token) is None


def test_delete_session_invalidates_token():
    user_id = find_or_create_user("runner@example.com", "google-sub-123")
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))

    delete_session(token)

    assert get_session_user_id(token) is None
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/data/test_db.py -v`
Expected: FAIL — `ImportError: cannot import name 'find_or_create_user'`

- [x] **Step 3: Implement CRUD functions**

```python
# append to data/db.py
import secrets
from datetime import datetime


def find_or_create_user(email: str, google_sub: str) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE google_sub = %s", (google_sub,)
        ).fetchone()
        if row is not None:
            return str(row[0])

        row = conn.execute(
            """
            INSERT INTO users (email, google_sub)
            VALUES (%s, %s)
            RETURNING id
            """,
            (email, google_sub),
        ).fetchone()
        conn.commit()
        return str(row[0])


def create_session(user_id: str, expires_at: datetime) -> str:
    token = secrets.token_urlsafe(32)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO sessions (token, user_id, expires_at)
            VALUES (%s, %s, %s)
            """,
            (token, user_id, expires_at),
        )
        conn.commit()
    return token


def get_session_user_id(token: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT user_id FROM sessions
            WHERE token = %s AND expires_at > now()
            """,
            (token,),
        ).fetchone()
    return str(row[0]) if row is not None else None


def delete_session(token: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token = %s", (token,))
        conn.commit()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/data/test_db.py -v`
Expected: PASS (10 tests total) — confirmed passing against real Supabase Postgres.

- [x] **Step 5: Commit**

```bash
git add data/db.py tests/data/test_db.py
git commit -m "feat: add user and session CRUD to data/db.py"
```

---

## Task 5: OAuth token storage (encrypted) ✅ DONE (verified passing against real Supabase Postgres)

**Files:**
- Modify: `data/db.py`
- Test: `tests/data/test_db.py`

**Interfaces:**
- Consumes: `get_connection()` (Task 3), `encrypt`/`decrypt` (Task 2)
- Produces: `save_oauth_token(user_id: str, provider: str, access_token: str, refresh_token: str, expires_at: int) -> None`, `get_oauth_token(user_id: str, provider: str) -> tuple[str, str, int] | None` (returns decrypted `access_token, refresh_token, expires_at`), `delete_oauth_token(user_id: str, provider: str) -> None`.

- [x] **Step 1: Write the failing tests**

```python
# append to tests/data/test_db.py
import base64
import os

from data.db import delete_oauth_token, get_oauth_token, save_oauth_token


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key)


def test_save_then_get_oauth_token_round_trips_decrypted():
    user_id = find_or_create_user("runner@example.com", "google-sub-123")

    save_oauth_token(user_id, "health", "access-abc", "refresh-xyz", 1234567890)
    access_token, refresh_token, expires_at = get_oauth_token(user_id, "health")

    assert access_token == "access-abc"
    assert refresh_token == "refresh-xyz"
    assert expires_at == 1234567890


def test_oauth_token_stored_encrypted_at_rest():
    user_id = find_or_create_user("runner@example.com", "google-sub-123")
    save_oauth_token(user_id, "health", "access-abc", "refresh-xyz", 1234567890)

    with get_connection() as conn:
        row = conn.execute(
            "SELECT access_token FROM oauth_tokens WHERE user_id = %s", (user_id,)
        ).fetchone()

    assert row[0] != "access-abc"


def test_save_oauth_token_upserts_on_conflict():
    user_id = find_or_create_user("runner@example.com", "google-sub-123")
    save_oauth_token(user_id, "health", "access-1", "refresh-1", 100)
    save_oauth_token(user_id, "health", "access-2", "refresh-2", 200)

    access_token, refresh_token, expires_at = get_oauth_token(user_id, "health")

    assert (access_token, refresh_token, expires_at) == ("access-2", "refresh-2", 200)


def test_get_oauth_token_returns_none_when_absent():
    user_id = find_or_create_user("runner@example.com", "google-sub-123")
    assert get_oauth_token(user_id, "health") is None


def test_delete_oauth_token_removes_row():
    user_id = find_or_create_user("runner@example.com", "google-sub-123")
    save_oauth_token(user_id, "health", "access-abc", "refresh-xyz", 1234567890)

    delete_oauth_token(user_id, "health")

    assert get_oauth_token(user_id, "health") is None
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/data/test_db.py -v`
Expected: FAIL — `ImportError: cannot import name 'save_oauth_token'`

- [x] **Step 3: Implement token storage functions**

```python
# append to data/db.py
from backend.encryption import decrypt, encrypt


def save_oauth_token(
    user_id: str, provider: str, access_token: str, refresh_token: str, expires_at: int
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO oauth_tokens
                (user_id, provider, access_token, refresh_token, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, provider) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at
            """,
            (user_id, provider, encrypt(access_token), encrypt(refresh_token), expires_at),
        )
        conn.commit()


def get_oauth_token(user_id: str, provider: str) -> tuple[str, str, int] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT access_token, refresh_token, expires_at
            FROM oauth_tokens WHERE user_id = %s AND provider = %s
            """,
            (user_id, provider),
        ).fetchone()
    if row is None:
        return None
    access_token, refresh_token, expires_at = row
    return decrypt(access_token), decrypt(refresh_token), expires_at


def delete_oauth_token(user_id: str, provider: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM oauth_tokens WHERE user_id = %s AND provider = %s",
            (user_id, provider),
        )
        conn.commit()
```

Note: `ON CONFLICT ... excluded` requires Postgres to treat the VALUES row as `excluded` — this is standard Postgres upsert syntax, unchanged from the SQLite version's intent.

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/data/test_db.py -v`
Expected: PASS (15 tests total) — confirmed passing against real Supabase Postgres.

- [x] **Step 5: Commit**

```bash
git add data/db.py tests/data/test_db.py
git commit -m "feat: add encrypted oauth token storage to data/db.py"
```

---

## Task 6: App login routes (identity-only OAuth) ✅ DONE (verified: 3/3 tests pass. FastAPI app lives in `backend/agent.py`, not `backend/main.py` as the plan template assumed — test file adjusted accordingly; router mounted in `backend/agent.py`)

**Files:**
- Create: `backend/routes/auth.py`
- Modify: `auth/auth.py` (extract reusable pieces; see Step 3)
- Modify: `backend/agent.py` or wherever the FastAPI `app` is constructed — mount the new router (locate via `grep -rn "FastAPI(" backend/`)
- Test: `tests/backend/routes/test_auth.py`

**Interfaces:**
- Consumes: `find_or_create_user`, `create_session`, `delete_session` (Task 4)
- Produces: `router` (FastAPI `APIRouter`) mounted at `/auth`, exposing `GET /auth/login`, `GET /auth/callback`, `POST /auth/logout`.

- [x] **Step 1: Locate the FastAPI app**

Run: `grep -rn "FastAPI(" backend/`

Confirm the app instance location before writing the mount step below; use that file's actual import path.

- [x] **Step 2: Write the failing test**

```python
# tests/backend/routes/test_auth.py
import base64
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from data.db import init_db


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "TOKEN_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    init_db()


@pytest.fixture
def client():
    from backend.main import app  # adjust to the actual app module found in Step 1

    return TestClient(app)


def test_login_redirects_to_google_with_identity_scopes(client):
    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 307
    location = response.headers["location"]
    assert "accounts.google.com" in location
    assert "scope=openid" in location or "openid" in location
    assert "googlehealth" not in location


def test_callback_creates_user_and_sets_session_cookie(client):
    with patch("backend.routes.auth.exchange_code_for_identity_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "email": "runner@example.com",
            "google_sub": "google-sub-123",
        }
        response = client.get(
            "/auth/callback?code=fake-code", follow_redirects=False
        )

    assert response.status_code == 307
    assert "session" in response.cookies


def test_logout_deletes_session_cookie(client):
    with patch("backend.routes.auth.exchange_code_for_identity_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "email": "runner@example.com",
            "google_sub": "google-sub-123",
        }
        login_response = client.get(
            "/auth/callback?code=fake-code", follow_redirects=False
        )
    session_cookie = login_response.cookies["session"]

    logout_response = client.post(
        "/auth/logout", cookies={"session": session_cookie}
    )

    assert logout_response.status_code == 200
```

- [x] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/backend/routes/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.routes.auth'`

- [x] **Step 4: Implement the router**

```python
# backend/routes/auth.py
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, Cookie, HTTPException
from fastapi.responses import RedirectResponse

from data.db import create_session, delete_session, find_or_create_user

router = APIRouter(prefix="/auth")

CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
CALLBACK_URL = os.environ.get(
    "GOOGLE_LOGIN_CALLBACK_URL", "http://localhost:8000/auth/callback"
)
IDENTITY_SCOPE = "openid email profile"
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
SESSION_DURATION = timedelta(days=7)


@router.get("/login")
def login():
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": CALLBACK_URL,
        "response_type": "code",
        "scope": IDENTITY_SCOPE,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        params
    )
    return RedirectResponse(auth_url)


def exchange_code_for_identity_tokens(code: str) -> dict:
    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": CALLBACK_URL,
            "grant_type": "authorization_code",
        },
    )
    token_response.raise_for_status()
    id_token_jwt = token_response.json()["id_token"]

    userinfo_response = requests.get(
        "https://www.googleapis.com/oauth2/v3/tokeninfo",
        params={"id_token": id_token_jwt},
    )
    userinfo_response.raise_for_status()
    payload = userinfo_response.json()

    return {"email": payload["email"], "google_sub": payload["sub"]}


@router.get("/callback")
def callback(code: str):
    identity = exchange_code_for_identity_tokens(code)
    user_id = find_or_create_user(identity["email"], identity["google_sub"])

    expires_at = datetime.now(timezone.utc) + SESSION_DURATION
    session_token = create_session(user_id, expires_at)

    response = RedirectResponse(FRONTEND_URL)
    response.set_cookie(
        "session",
        session_token,
        httponly=True,
        expires=int(SESSION_DURATION.total_seconds()),
    )
    return response


@router.post("/logout")
def logout(session: str | None = Cookie(default=None)):
    if session is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    delete_session(session)
    response = RedirectResponse(FRONTEND_URL, status_code=200)
    response.delete_cookie("session")
    return response
```

Mount the router in the FastAPI app file located in Step 1:

```python
from backend.routes.auth import router as auth_router

app.include_router(auth_router)
```

- [x] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/backend/routes/test_auth.py -v`
Expected: PASS (3 tests) — confirmed passing.

- [x] **Step 6: Commit**

```bash
git add backend/routes/auth.py tests/backend/routes/test_auth.py backend/main.py
git commit -m "feat: add app login OAuth flow (identity-only, session cookie)"
```

---

## Task 7: Health connect routes ✅ DONE (verified: 7/7 tests pass in `tests/backend/routes/test_auth.py` against real Supabase Postgres)

**Files:**
- Modify: `backend/routes/auth.py`
- Test: `tests/backend/routes/test_auth.py`

**Interfaces:**
- Consumes: `save_oauth_token`, `delete_oauth_token` (Task 5), session dependency pattern from Task 6's `Cookie`-based lookup.
- Produces: `GET /auth/health/connect`, `GET /auth/health/callback`, `POST /auth/health/disconnect`.

- [x] **Step 1: Write the failing tests**

```python
# append to tests/backend/routes/test_auth.py
def _login(client) -> str:
    with patch("backend.routes.auth.exchange_code_for_identity_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "email": "runner@example.com",
            "google_sub": "google-sub-123",
        }
        response = client.get("/auth/callback?code=fake-code", follow_redirects=False)
    return response.cookies["session"]


def test_health_connect_requires_session(client):
    response = client.get("/auth/health/connect", follow_redirects=False)
    assert response.status_code == 401


def test_health_connect_redirects_with_health_scope(client):
    session_cookie = _login(client)

    response = client.get(
        "/auth/health/connect",
        cookies={"session": session_cookie},
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert "googlehealth" in response.headers["location"]


def test_health_callback_stores_encrypted_token(client):
    session_cookie = _login(client)

    with patch("backend.routes.auth.exchange_code_for_health_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "access_token": "health-access",
            "refresh_token": "health-refresh",
            "expires_in": 3600,
        }
        response = client.get(
            "/auth/health/callback?code=fake-code",
            cookies={"session": session_cookie},
            follow_redirects=False,
        )

    assert response.status_code == 307


def test_health_disconnect_removes_token(client):
    session_cookie = _login(client)
    with patch("backend.routes.auth.exchange_code_for_health_tokens") as mock_exchange:
        mock_exchange.return_value = {
            "access_token": "health-access",
            "refresh_token": "health-refresh",
            "expires_in": 3600,
        }
        client.get(
            "/auth/health/callback?code=fake-code",
            cookies={"session": session_cookie},
            follow_redirects=False,
        )

    response = client.post(
        "/auth/health/disconnect", cookies={"session": session_cookie}
    )

    assert response.status_code == 200
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/backend/routes/test_auth.py -v`
Expected: FAIL — `AttributeError: module 'backend.routes.auth' has no attribute 'exchange_code_for_health_tokens'`

- [x] **Step 3: Implement Health connect routes**

Append to `backend/routes/auth.py`:

```python
import time

from data.db import delete_oauth_token, get_session_user_id, save_oauth_token

HEALTH_SCOPE = "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly"
HEALTH_CALLBACK_URL = os.environ.get(
    "GOOGLE_HEALTH_CALLBACK_URL", "http://localhost:8000/auth/health/callback"
)


def _require_user_id(session: str | None) -> str:
    if session is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = get_session_user_id(session)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session expired")
    return user_id


@router.get("/health/connect")
def health_connect(session: str | None = Cookie(default=None)):
    _require_user_id(session)

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": HEALTH_CALLBACK_URL,
        "response_type": "code",
        "scope": HEALTH_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        params
    )
    return RedirectResponse(auth_url)


def exchange_code_for_health_tokens(code: str) -> dict:
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": HEALTH_CALLBACK_URL,
            "grant_type": "authorization_code",
        },
    )
    response.raise_for_status()
    return response.json()


@router.get("/health/callback")
def health_callback(code: str, session: str | None = Cookie(default=None)):
    user_id = _require_user_id(session)
    tokens = exchange_code_for_health_tokens(code)
    expires_at = int(time.time()) + tokens["expires_in"]

    save_oauth_token(
        user_id, "health", tokens["access_token"], tokens["refresh_token"], expires_at
    )
    return RedirectResponse(FRONTEND_URL)


@router.post("/health/disconnect")
def health_disconnect(session: str | None = Cookie(default=None)):
    user_id = _require_user_id(session)
    delete_oauth_token(user_id, "health")
    return {"status": "disconnected"}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/backend/routes/test_auth.py -v`
Expected: PASS (7 tests total) — confirmed: 7/7 passed.

- [x] **Step 5: Commit**

```bash
git add backend/routes/auth.py tests/backend/routes/test_auth.py
git commit -m "feat: add Health connect OAuth flow, separate from app login"
```

---

## Task 8: Session dependency and token refresh for /chat

**Files:**
- Create: `backend/dependencies.py`
- Modify: `auth/auth.py` (adapt `get_valid_access_token` to the new per-user, encrypted storage)
- Modify: `backend/routes/chat.py`
- Test: `tests/backend/test_dependencies.py`
- Test: `tests/auth/test_auth.py`

**Interfaces:**
- Consumes: `get_session_user_id` (Task 4), `get_oauth_token`, `save_oauth_token` (Task 5)
- Produces: `require_user(session: str | None) -> str` (FastAPI dependency, raises 401), `get_valid_access_token(user_id: str) -> str` (replaces the email-keyed version in `auth/auth.py`)

- [x] **Step 1: Write the failing test for the dependency**

```python
# tests/backend/test_dependencies.py
import pytest
from fastapi import HTTPException

from backend.dependencies import require_user
from data.db import create_session, find_or_create_user, init_db


@pytest.fixture(autouse=True)
def db():
    init_db()


def test_require_user_returns_user_id_for_valid_session():
    from datetime import datetime, timedelta, timezone

    user_id = find_or_create_user("runner@example.com", "google-sub-123")
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=1))

    assert require_user(token) == user_id


def test_require_user_raises_401_for_missing_session():
    with pytest.raises(HTTPException) as exc_info:
        require_user(None)
    assert exc_info.value.status_code == 401


def test_require_user_raises_401_for_invalid_session():
    with pytest.raises(HTTPException) as exc_info:
        require_user("not-a-real-token")
    assert exc_info.value.status_code == 401
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/test_dependencies.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.dependencies'`

- [x] **Step 3: Implement the dependency**

```python
# backend/dependencies.py
from fastapi import Cookie, HTTPException

from data.db import get_session_user_id


def require_user(session: str | None = Cookie(default=None)) -> str:
    if session is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = get_session_user_id(session)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session expired")
    return user_id
```

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backend/test_dependencies.py -v`
Expected: PASS (3 tests)

- [x] **Step 5: Write the failing test for per-user token refresh**

```python
# tests/auth/test_auth.py
import base64
import os
from unittest.mock import patch

import pytest

from auth.auth import get_valid_access_token
from data.db import find_or_create_user, init_db, save_oauth_token


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv(
        "TOKEN_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    init_db()


def test_returns_stored_token_when_still_valid():
    import time

    user_id = find_or_create_user("runner@example.com", "google-sub-123")
    save_oauth_token(
        user_id, "health", "valid-access", "refresh-1", int(time.time()) + 3600
    )

    assert get_valid_access_token(user_id) == "valid-access"


def test_refreshes_expired_token():
    import time

    user_id = find_or_create_user("runner@example.com", "google-sub-123")
    save_oauth_token(
        user_id, "health", "expired-access", "refresh-1", int(time.time()) - 10
    )

    with patch("auth.auth.refresh_access_token") as mock_refresh:
        mock_refresh.return_value = {
            "access_token": "new-access",
            "expires_in": 3600,
        }
        result = get_valid_access_token(user_id)

    assert result == "new-access"
```

- [x] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/auth/test_auth.py -v`
Expected: FAIL — `TypeError: get_valid_access_token() takes 1 positional argument` (current signature takes `email`, calls CLI `input()` on miss)

- [x] **Step 7: Rewrite `get_valid_access_token` for per-user, encrypted, non-interactive use**

Replace the existing `get_valid_access_token` function and the `data.db` import in `auth/auth.py`:

```python
# auth/auth.py — replace the import and get_valid_access_token function
import time

from data.db import get_oauth_token, save_oauth_token


def get_valid_access_token(user_id: str) -> str:
    token_row = get_oauth_token(user_id, "health")

    if token_row is None:
        raise ValueError(
            f"No Health token for user {user_id}; user must complete "
            "/auth/health/connect first"
        )

    access_token, refresh_token, expires_at = token_row

    if expires_at > time.time():
        return access_token

    response = refresh_access_token(refresh_token)
    new_expires_at = int(time.time()) + response["expires_in"]
    save_oauth_token(
        user_id, "health", response["access_token"], refresh_token, new_expires_at
    )
    return response["access_token"]
```

Remove the now-unused `get_authorization_code`, `exchange_code_for_tokens` CLI-paste flow and the `if __name__ == "__main__"` block from `auth/auth.py` — `backend/routes/auth.py` (Tasks 6-7) now owns code exchange via the web callback routes.

- [x] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/auth/test_auth.py -v`
Expected: PASS (2 tests)

- [x] **Step 9: Wire `/chat` to require a session and forward a minted JWT to the MCP server**

The MCP server authenticates itself now — it does its own bearer-token verification (against a JWKS endpoint it fetches and caches) and its own Postgres lookup (see Task 8a/8b below). `/chat` no longer resolves or passes a Health `access_token`; it only needs to (a) confirm the caller has a valid Strides session, and (b) mint a short-lived signed token the MCP server can independently verify.

Modify `backend/routes/chat.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.agent import app_state
from backend.dependencies import require_user
from backend.jwt_issuer import mint_token
from backend.services.chat_service import process_query

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
async def chat(request: ChatRequest, user_id: str = Depends(require_user)):
    mcp_token = mint_token(user_id)  # short-lived, RS256-signed (Task 8a)

    app_state["messages"].append({"role": "user", "content": request.message})

    reply = await process_query(
        app_state["session"],
        app_state["tools"],
        app_state["messages"],
        mcp_token,  # forwarded as Authorization header inside process_query, not as a tool arg
    )

    return {"reply": reply}
```

`process_query`/`call_tools` in `backend/services/chat_service.py` must set `Authorization: Bearer {mcp_token}` on the MCP client session/transport — not inject it into `block.input`. This avoids putting a live credential into the LLM tool-use loop's visible/loggable surface area; the minted token is single-audience (`strides-mcp`), 5-minute-lived, and grants no minting capability of its own.

- [x] **Step 10: Commit**

```bash
git add backend/dependencies.py backend/routes/chat.py backend/jwt_issuer.py auth/auth.py tests/backend/test_dependencies.py tests/auth/test_auth.py
git commit -m "feat: require session on /chat, forward minted JWT instead of raw Health token"
```

---

## Task 8a: JWT issuer (backend mints short-lived signed tokens)

**Files:**
- Create: `backend/jwt_issuer.py`
- Create: `backend/keys/` (gitignored — holds `private.pem`, `public.pem`)
- Modify: `backend/routes/auth.py` (new `/.well-known/jwks.json` route)
- Test: `tests/backend/test_jwt_issuer.py`

**Interfaces:**
- Produces: `mint_token(user_id: str) -> str` (RS256-signed JWT, 5 min expiry, `sub` claim = user_id), `get_jwks() -> dict` (public key in JWKS format)
- Consumes: nothing from other tasks (standalone crypto module)

**Why asymmetric (RS256) over a shared HMAC secret:** verification capability shouldn't imply minting capability. With RS256, the MCP server (or any future second consumer) only ever holds the public key — it can verify tokens but never forge one. A shared HMAC secret would mean every verifier is also a minter, which doesn't degrade gracefully the moment a second consumer is added. This also matches the MCP Authorization spec's resource-server model, where the resource server independently verifies tokens rather than trusting the caller.

- [x] **Step 1: Add dependency**

```bash
uv add "pyjwt[crypto]"
```

- [x] **Step 2: Write the failing tests**

```python
# tests/backend/test_jwt_issuer.py
import time

import jwt as pyjwt
import pytest

from backend.jwt_issuer import get_jwks, mint_token, PUBLIC_KEY


def test_mint_token_contains_user_id_claim():
    token = mint_token("user-123")
    payload = pyjwt.decode(token, PUBLIC_KEY, algorithms=["RS256"], audience="strides-mcp")
    assert payload["sub"] == "user-123"


def test_mint_token_expires_in_five_minutes():
    token = mint_token("user-123")
    payload = pyjwt.decode(token, PUBLIC_KEY, algorithms=["RS256"], audience="strides-mcp")
    assert 290 <= (payload["exp"] - payload["iat"]) <= 310


def test_mint_token_rejected_after_expiry():
    token = mint_token("user-123")
    with pytest.raises(pyjwt.ExpiredSignatureError):
        pyjwt.decode(
            token, PUBLIC_KEY, algorithms=["RS256"], audience="strides-mcp",
            options={"require": ["exp"]}, leeway=-310,
        )


def test_get_jwks_returns_public_key_in_jwks_format():
    jwks = get_jwks()
    assert "keys" in jwks
    assert jwks["keys"][0]["kty"] == "RSA"
    assert jwks["keys"][0]["kid"] == "strides-1"
```

- [x] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/backend/test_jwt_issuer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.jwt_issuer'`

- [x] **Step 4: Generate the keypair (one-time, not part of the module)**

```bash
mkdir -p backend/keys
openssl genrsa -out backend/keys/private.pem 2048
openssl rsa -in backend/keys/private.pem -pubout -out backend/keys/public.pem
echo "backend/keys/" >> .gitignore
```

- [x] **Step 5: Implement the module**

```python
# backend/jwt_issuer.py
import time
from pathlib import Path

import jwt
from jwt.algorithms import RSAAlgorithm

_KEYS_DIR = Path(__file__).parent / "keys"
PRIVATE_KEY = (_KEYS_DIR / "private.pem").read_text()
PUBLIC_KEY = (_KEYS_DIR / "public.pem").read_text()
KID = "strides-1"
AUDIENCE = "strides-mcp"
TOKEN_TTL_SECONDS = 300  # 5 minutes


def mint_token(user_id: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, PRIVATE_KEY, algorithm="RS256", headers={"kid": KID})


def get_jwks() -> dict:
    jwk = RSAAlgorithm.to_jwk(
        RSAAlgorithm.from_jwk_pem(PUBLIC_KEY) if hasattr(RSAAlgorithm, "from_jwk_pem")
        else jwt.algorithms.RSAAlgorithm(jwt.algorithms.hashes.SHA256()).prepare_key(PUBLIC_KEY),
        as_dict=True,
    )
    jwk["kid"] = KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return {"keys": [jwk]}
```

> Note for implementer: `pyjwt`'s public-key-to-JWK conversion API varies by version — pin `pyjwt[crypto]>=2.8` and verify `get_jwks()` output against `https://www.googleapis.com/oauth2/v3/certs` shape (fields: `kty`, `n`, `e`, `kid`, `use`, `alg`) before relying on it. If `to_jwk` proves unreliable, `python-jose` is an acceptable substitute for this one function.

- [x] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/backend/test_jwt_issuer.py -v`
Expected: PASS (4 tests)

- [x] **Step 7: Add the JWKS route**

```python
# append to backend/routes/auth.py
from backend.jwt_issuer import get_jwks

@router.get("/.well-known/jwks.json")
def jwks():
    return get_jwks()
```

- [x] **Step 8: Commit**

```bash
git add backend/jwt_issuer.py backend/routes/auth.py backend/keys/public.pem .gitignore tests/backend/test_jwt_issuer.py pyproject.toml uv.lock
git commit -m "feat: add RS256 JWT issuer and JWKS endpoint for MCP auth"
```

**Do not commit `backend/keys/private.pem`** — deploy it via secrets manager / env-injected file, not source control.

---

## Task 8b: MCP server verifies JWT via JWKS, resolves its own Health token

**Files:**
- Modify: `mcp_servers/fit_server/server.py`
- Create: `mcp_servers/fit_server/mcp_auth.py`
- Modify: `auth/auth.py` (`get_valid_access_token` uses `SELECT ... FOR UPDATE` row locking — see Step 6a)
- Test: `tests/mcp/test_mcp_auth.py`

**Interfaces:**
- Consumes: `GET /.well-known/jwks.json` (Task 8a, fetched over HTTP), `get_oauth_token` (Task 5, direct Postgres access via `DATABASE_URL`)
- Produces: `verify_bearer_token(token: str) -> str` (returns `user_id`, raises on invalid/expired), middleware wiring in `server.py`

- [x] **Step 1: Add dependency**

```bash
uv add "pyjwt[crypto]" cachetools
```

- [x] **Step 2: Write the failing tests**

```python
# tests/mcp/test_mcp_auth.py
from unittest.mock import patch

import jwt as pyjwt
import pytest

from mcp_servers.fit_server.mcp_auth import verify_bearer_token

PRIVATE_KEY = "<test-only RSA private key PEM, generate via openssl in fixture setup>"
FAKE_JWKS = {"keys": [{"kty": "RSA", "kid": "strides-1", "n": "...", "e": "AQAB", "use": "sig", "alg": "RS256"}]}


def _sign(user_id: str, **overrides) -> str:
    import time
    payload = {"sub": user_id, "aud": "strides-mcp", "iat": int(time.time()), "exp": int(time.time()) + 300}
    payload.update(overrides)
    return pyjwt.encode(payload, PRIVATE_KEY, algorithm="RS256", headers={"kid": "strides-1"})


def test_verify_bearer_token_returns_user_id_for_valid_token():
    with patch("mcp_servers.fit_server.mcp_auth._fetch_jwks", return_value=FAKE_JWKS):
        token = _sign("user-123")
        assert verify_bearer_token(token) == "user-123"


def test_verify_bearer_token_rejects_expired_token():
    with patch("mcp_servers.fit_server.mcp_auth._fetch_jwks", return_value=FAKE_JWKS):
        token = _sign("user-123", exp=0)
        with pytest.raises(Exception):
            verify_bearer_token(token)


def test_verify_bearer_token_rejects_wrong_audience():
    with patch("mcp_servers.fit_server.mcp_auth._fetch_jwks", return_value=FAKE_JWKS):
        token = _sign("user-123", aud="someone-else")
        with pytest.raises(Exception):
            verify_bearer_token(token)
```

> Note for implementer: the fixture needs a real generated RSA keypair (`openssl genrsa`) at test setup so `FAKE_JWKS` actually matches `PRIVATE_KEY` — write a `conftest.py` fixture that generates both together rather than hardcoding a static pair.

- [x] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/mcp/test_mcp_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_servers.fit_server.mcp_auth'`

- [x] **Step 4: Implement JWKS verification with caching**

```python
# mcp_servers/fit_server/mcp_auth.py
import os

import jwt
import requests
from cachetools import TTLCache

AUDIENCE = "strides-mcp"
JWKS_URL = os.environ.get("STRIDES_JWKS_URL", "http://localhost:8000/.well-known/jwks.json")

_jwks_cache: TTLCache = TTLCache(maxsize=1, ttl=300)  # 5 min cache


def _fetch_jwks() -> dict:
    response = requests.get(JWKS_URL, timeout=5)
    response.raise_for_status()
    return response.json()


def _get_signing_key(token: str):
    if "jwks" not in _jwks_cache:
        _jwks_cache["jwks"] = _fetch_jwks()
    jwks = _jwks_cache["jwks"]
    header = jwt.get_unverified_header(token)
    for key in jwks["keys"]:
        if key["kid"] == header["kid"]:
            return jwt.algorithms.RSAAlgorithm.from_jwk(key)
    raise jwt.InvalidTokenError(f"No matching key for kid={header.get('kid')}")


def verify_bearer_token(token: str) -> str:
    """Returns the verified user_id (sub claim), raises jwt exceptions on failure."""
    signing_key = _get_signing_key(token)
    payload = jwt.decode(token, signing_key, algorithms=["RS256"], audience=AUDIENCE)
    return payload["sub"]
```

- [x] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/mcp/test_mcp_auth.py -v`
Expected: PASS (3 tests)

- [x] **Step 6: Wire verification into `server.py`, switch transport to HTTP**

```python
# mcp_servers/fit_server/server.py — additions
from fastmcp import FastMCP, Context
from mcp_servers.fit_server.mcp_auth import verify_bearer_token
from data.db import get_oauth_token
from auth.auth import get_valid_access_token  # moved logic reused here, not in chat.py

mcp = FastMCP("strides")

@mcp.middleware
async def auth_middleware(request, call_next):
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise PermissionError("Missing bearer token")
    token = auth_header.removeprefix("Bearer ")
    try:
        user_id = verify_bearer_token(token)
    except Exception:
        raise PermissionError("Invalid or expired token")
    request.state.user_id = user_id
    return await call_next(request)


@mcp.tool()
def get_recent_runs(days: int, ctx: Context) -> dict:
    """Get the user's recent runs from Google Health."""
    user_id = ctx.request.state.user_id
    try:
        access_token = get_valid_access_token(user_id)  # Task 8's refresh logic, now called here
    except ValueError:
        return {"error": "Google Health not connected. Ask the user to connect it in their dashboard."}
    # ... existing fetch_runs logic using access_token


if __name__ == "__main__":
    mcp.run(transport="streamable-http", port=8001)
```

> Note for implementer: exact middleware/context API depends on the installed FastMCP version — verify `mcp.middleware` and `Context`/`ctx.request` are correct for your pinned version before implementing; check `fastmcp` changelog if names differ.

- [x] **Step 6a: Guard `get_valid_access_token` against concurrent-refresh races**

Both FastAPI and the MCP server can now independently call `get_valid_access_token(user_id)` — e.g. FastAPI refreshing for `/auth/me` at the same moment the MCP server refreshes for a tool call. Google's refresh tokens are single-use/rotating: whichever request reaches Google's `/token` endpoint second gets `invalid_grant` because the refresh token it read has already been rotated out from under it, even though it looked valid when read.

**Implementation note — deviated from the original CAS design below.** The original plan was an optimistic compare-and-swap (`save_oauth_token_if_unchanged`, `WHERE refresh_token = %s`), keyed on comparing the *encrypted* `refresh_token` column against a freshly re-encrypted value. This doesn't work: `encrypt()` is AES-256-GCM with a random nonce per call (see `test_encrypt_is_nondeterministic` in `tests/backend/test_encryption.py`), so encrypting the same plaintext twice never produces equal ciphertext. The `WHERE` clause matched zero rows even absent any real race, `save_oauth_token_if_unchanged` always reported a lost race, and `get_valid_access_token` always fell back to a stale re-read — caught by `tests/auth/test_auth.py::test_refreshes_expired_token` failing (`'expired-access' == 'new-access'`).

Replaced with **pessimistic locking** (`SELECT ... FOR UPDATE`) instead, in `auth/auth.py`:

```python
# auth/auth.py
from backend.encryption import decrypt, encrypt
from data.db import get_connection


def get_valid_access_token(user_id: str) -> str:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT access_token, refresh_token, expires_at
            FROM oauth_tokens WHERE user_id = %s AND provider = %s
            FOR UPDATE
            """,
            (user_id, "health"),
        ).fetchone()

        if row is None:
            raise ValueError(
                f"No Health token for user {user_id}; user must complete "
                "/auth/health/connect first"
            )

        access_token, refresh_token, expires_at = row

        if expires_at > time.time():
            return decrypt(access_token)

        response = refresh_access_token(decrypt(refresh_token))
        new_expires_at = int(time.time()) + response["expires_in"]

        conn.execute(
            """
            UPDATE oauth_tokens SET access_token = %s, expires_at = %s
            WHERE user_id = %s AND provider = %s
            """,
            (encrypt(response["access_token"]), new_expires_at, user_id, "health"),
        )
        conn.commit()
        return response["access_token"]
```

- `FOR UPDATE` locks the row for the transaction's duration. A concurrent caller's `SELECT ... FOR UPDATE` on the same row **blocks** until this transaction commits, rather than racing — no ciphertext comparison needed anywhere.
- Once unblocked, the second caller re-reads the (now already-refreshed) row and re-checks `expires_at > time.time()`, which passes, so it returns the winner's token instead of calling Google a second time.
- `save_oauth_token_if_unchanged` was removed from `data/db.py` entirely (dead code, and subtly broken) rather than left in place.

Note: encryption note from Task 5's open question is resolved here — `encrypt`/`decrypt` stay imported by both processes (`backend/encryption.py` shared), since the MCP server is now a second reader/writer of `oauth_tokens`.

- [x] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/mcp/test_mcp_auth.py tests/data/test_db.py -v`
Expected: PASS (all)

- [x] **Step 8: Commit**

```bash
git add mcp_servers/fit_server/server.py mcp_servers/fit_server/mcp_auth.py data/db.py auth/auth.py tests/mcp/test_mcp_auth.py
git commit -m "feat: MCP server independently verifies JWT via JWKS, resolves own Health token, guards against refresh races"
```

**Trust model change:** the MCP server no longer trusts a backend-supplied token/user_id blindly — it independently verifies a short-lived RS256 JWT against a JWKS endpoint it fetches and caches itself, then does its own Postgres lookup for the user's Google Health refresh token. This matches the MCP Authorization spec's resource-server model.

**Two Postgres connections now exist**: FastAPI (users/sessions/oauth_tokens writes) and the MCP server (oauth_tokens reads/refresh-writes) — both via the same `DATABASE_URL`, no bridging required, no new infra. This is why Step 6a's `SELECT ... FOR UPDATE` guard matters: it's the mechanism that keeps the two connections from corrupting each other's refresh.

**Private key handling**: `backend/keys/private.pem` must never enter source control or logs; production deployment should inject it via secrets manager, not the repo.

**Open follow-up**: JWKS key rotation (multiple `kid`s, overlapping validity) is not covered here — acceptable for current scale, flag as future work if the signing key ever needs rotating without downtime.

---

## Task 9: Remove superseded docs and retired code paths

**Files:**
- Delete: `docs/ARCHITECTURE.md` (superseded by `docs/superpowers/specs/2026-08-01-multi-user-architecture-design.md`) — **already absent by the time this task ran, no action needed**
- Delete: `docs/AUTH_IMPLEMENTATION.md` (superseded by this plan) — **already absent, no action needed**
- Delete: `main.py` — the old single-user CLI entrypoint; imports `from src.auth.auth import get_valid_access_token`, but `src/` was removed in the multi-user pivot, so this file was already broken (`ModuleNotFoundError` on import) and fully superseded by `backend/agent.py`
- Delete: `tests/test_fit_server.py` — tested the old `src.fit_server`/`src.helpers.health_api` modules, also broken on collection (`ModuleNotFoundError`), superseded by `tests/mcp/test_mcp_auth.py`
- Modify: `data/db.py` — confirm no remaining `sqlite3` import or `data/strides.db` reference — **confirmed clean**
- Modify: `.gitignore` — remove `data/strides.db` entry if present — **no such entry found, no action needed**

**Interfaces:** none (cleanup only).

- [x] **Step 1: Verify no remaining references to the retired SQLite file or CLI flow**

Run:
```bash
grep -rn "strides.db\|sqlite3\|get_authorization_code" --include="*.py" .
```
Result: no matches. Separately found `main.py` and `tests/test_fit_server.py` still importing the retired `src.*` package (not `strides.db`/`sqlite3` specifically, but the same "retired CLI flow" this step is checking for) — both already broken, both deleted.

- [x] **Step 2: Remove the superseded planning docs**

`docs/ARCHITECTURE.md` and `docs/AUTH_IMPLEMENTATION.md` were already gone by the time this task ran (removed in an earlier, undocumented cleanup) — nothing to do here.

- [x] **Step 3: Update `.gitignore` if it references `data/strides.db`**

Run: `grep -n "strides.db" .gitignore` — no match, nothing to remove.

- [ ] **Step 4: Commit**

```bash
git add -A main.py tests/test_fit_server.py
git commit -m "chore: remove retired src/-based CLI entrypoint and its test"
```

---

## Self-Review Notes

- **Spec coverage:** app login (Task 6), Health connect (Task 7), opaque session + revocation on logout (Tasks 4, 6), encrypted token storage (Tasks 2, 5), token refresh (Task 8), Supabase Postgres schema (Task 3) — all covered. Frontend, Dockerfiles, `preferences`/`goals`/`messages` tables, and MCP tool signature changes remain explicitly out of scope per the spec's deferred list; Task 8 Step 9 flags the one integration seam (passing `access_token` into MCP tool calls) that this plan touches but doesn't complete, since it depends on MCP server changes outside this plan's scope.
- **Placeholder scan:** no TBD/TODO; the one open item (Step 9 MCP wiring) is explicitly named as a follow-up, not a placeholder.
- **Type consistency:** `user_id` is `str` (stringified UUID) consistently across `data/db.py`, `backend/dependencies.py`, `auth/auth.py`, and `backend/routes/*.py`. `get_oauth_token` / `save_oauth_token` signatures match between Task 5 and their Task 8 callers.
