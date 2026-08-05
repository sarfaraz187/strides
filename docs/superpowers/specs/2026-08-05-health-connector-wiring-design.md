# Wire the connectors screen to the real Health-connect backend

Decided 2026-08-05. Scope: replace the mocked "Connect"/"Disconnect" behavior in
`frontend/components/connectors-screen.tsx` with the real Google Health OAuth flow that
already exists on the backend (`backend/routes/auth.py`'s `/auth/health/connect`,
`/auth/health/callback`, `/auth/health/disconnect`), and drop the unrelated mocked
Google Calendar entry.

## Why

Login (identity) and Health-connect (data access) are two separate OAuth consents by
design — see `docs/superpowers/specs/2026-08-01-multi-user-architecture-design.md`. Login
already works end-to-end. Health-connect's backend routes were built in the auth-layer
plan (Task 7) but the frontend never calls them — `ConnectorsScreen` fakes the whole
interaction with local `useState` and a `setTimeout`. A freshly-registered user today can
log in and reach the chat screen, but the agent has no Health token to fetch data with
unless one was seeded manually during earlier testing. This closes that gap.

## Out of scope

- Google Calendar connector — no backend exists for it at all; the card is mock-only and
  gets removed, not wired to anything.
- `preferences`/`goals` tables — unrelated, not touched here.
- Dashboard mock data (`get_weekly_stats`/`get_recent_runs` wiring) — separate task.

## Backend change

### `/auth/me` gains a `health_connected` field

`backend/routes/auth.py`'s `me()` currently returns `{ email, name, created_at }`. Add a
DB lookup via `data/db.py`'s existing `get_oauth_token(user_id, "health")` — token found
→ `health_connected: true`, else `false`. This is the only way the frontend can know
connection status without inventing a second endpoint; `/auth/me` is already fetched on
every app load via `AuthProvider`.

```
GET /auth/me → { email, name, created_at, health_connected }
```

### `/auth/health/callback` error handling

Currently `exchange_code_for_health_tokens` is unguarded — a user denying consent, or any
exchange failure, 500s with no user-facing signal. Wrap it: on failure, redirect to
`FRONTEND_URL` with an error query param (e.g. `?health_connect_error=1`) instead of
raising, so the frontend can render a toast/inline error instead of a blank crash page.

No changes needed to `/auth/health/connect` or `/auth/health/disconnect` — both are
already correct for this flow.

## Frontend changes

### Connect: plain redirect, not a fetch call

This is a full OAuth consent screen — it can't be an `async` button handler. The
"Connect" button becomes a real link to
`${NEXT_PUBLIC_API_URL}/auth/health/connect` (or `window.location.href =` that URL).
Google redirects to the backend's `/auth/health/callback`, which saves the token and
redirects back to `FRONTEND_URL`. On landing back, the existing React Query
`/auth/me` fetch (already wired through `AuthProvider`) needs to be invalidated/refetched
so `health_connected` reflects the new state — no new polling mechanism required, just
make sure the query re-runs on mount/focus or is explicitly invalidated after the
redirect completes.

### Disconnect: real POST

`POST ${NEXT_PUBLIC_API_URL}/auth/health/disconnect` with `credentials: "include"` (the
session cookie carries auth, same pattern the rest of the API client already uses).
On success, invalidate the `/auth/me` query.

### Status model collapses to two states

Drop `"pending"` for the Health connector — there's no real intermediate state to
represent; the "connecting" moment is the browser navigating away to Google and back, not
something this app's state machine can observe. `ConnectorStatus` becomes effectively
`"connected" | "disconnected"`, derived straight from `useAuth()`'s `health_connected`,
not local component state.

### Remove mock data for this screen

- Delete `mockConnectors`, `Connector`, `ConnectorStatus` from `frontend/lib/mock-data.ts`
  (or narrow them to just what's still needed if other screens import from the same
  file — check before deleting the whole block).
- `ConnectorsScreen` renders a single row for Google Health, sourced from
  `useAuth()`, not `useState<Connector[]>`.
- Google Calendar card removed entirely — no backend, not being stubbed as
  "coming soon" per your call.

## Error handling

- Consent denied / exchange failure (backend redirects with `?health_connect_error=1`):
  frontend shows an inline error state on the connectors screen instead of silently
  doing nothing.
- Disconnect request fails (network/500): keep showing "connected" (don't optimistically
  flip to disconnected) and surface an error — the account may still be connected
  server-side.
- Not logged in: `_require_user_id` already 401s on both connect and disconnect
  server-side; frontend shouldn't be able to reach this screen unauthenticated anyway
  (existing `AuthProvider` redirect covers this).

## Testing

Given this is a learning project focused on understanding the flow, tests are optional
here — flag to the user whether they want:
- A backend test for `/auth/me` returning `health_connected` correctly (token present vs.
  absent vs. expired-but-present).
- A backend test for the `/auth/health/callback` error-redirect path.
- Frontend: likely not worth testing the OAuth redirect itself (it leaves the app), but
  the derived status rendering (`connected`/`disconnected` from `useAuth()`) is a cheap
  unit test if `ConnectorsScreen` is refactored to take status as a prop.

## Open question for implementer

`get_oauth_token` — confirm whether it returns `None`/falsy for both "never connected"
and "row deleted after disconnect," so `health_connected` doesn't need to distinguish
those two cases (it shouldn't need to).
