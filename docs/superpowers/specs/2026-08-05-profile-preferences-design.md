# Profile preferences persistence (incl. language) — design

## Context

The profile screen (`frontend/components/profile-screen.tsx`) currently holds
weekly goal, units, and notifications as local `useState` — nothing is
persisted. A `preferences` table already exists in Postgres
(`weekly_goal_km`, `units`, `notifications_enabled`) but nothing reads or
writes it; no route calls it.

The immediate ask was a language dropdown on the profile page. Since the app
has no schema or backend support for *any* preference yet, this spec wires
persistence for all four profile settings together, including language,
rather than bolting language on as a one-off.

## Data model

Add a `language` column to the existing `preferences` table:

```sql
ALTER TABLE preferences ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en';
```

No CHECK constraint — validated app-side only, consistent with how `units`
is already handled (plain `TEXT`, no DB-level enum).

A user has **no** preferences row until they change something for the first
time (lazy creation via upsert), not created eagerly at signup.

## Backend

### `data/db.py`

- `get_preferences(user_id: str) -> Preferences` — reads the row for
  `user_id`. If no row exists, returns a `Preferences` dataclass populated
  with defaults (`weekly_goal_km=30, units="km", notifications_enabled=True,
  language="en"`) without writing to the DB.
- `upsert_preferences(user_id: str, **fields) -> Preferences` —
  `INSERT ... ON CONFLICT (user_id) DO UPDATE`, updating only the fields
  passed in; omitted fields keep the existing row's value (or the default,
  if no row existed before this call).

### `backend/routes/preferences.py` (new)

- `GET /preferences` — session-cookie auth (same dependency `/auth/me`
  already uses). Returns the `Preferences` object as JSON.
- `PUT /preferences` — body is a partial object, all fields optional:
  `{weekly_goal_km?, units?, notifications_enabled?, language?}`. Calls
  `upsert_preferences` with whatever fields were provided, returns the
  resulting full object.

## Frontend

- `lib/api.ts`: `getPreferences()`, `updatePreferences(partial)`.
- `profile-screen.tsx`:
  - `useQuery(["preferences"])` for initial load. Controls are
    disabled/skeleton until it resolves.
  - One `useMutation` wrapping `updatePreferences`, called:
    - **immediately** for the units toggle, notifications toggle, and
      language change (discrete, single-action controls),
    - **debounced ~500ms** after the last click for the goal stepper
      (+/-), so rapid clicking collapses into a single PUT instead of one
      per click.
  - No optimistic updates — controls reflect the last *server-confirmed*
    value. On mutation failure, show a small inline error state; the
    control does not visually change until the request succeeds. This
    keeps error handling simple for a personal project.
  - Language control: a two-option segmented control matching the existing
    units toggle's visual style (not a `<select>`) — there are only two
    locales (`en`/`de`).
  - On language change: `router.replace` the current pathname with the new
    locale segment substituted in, alongside firing the mutation.
- New i18n keys (`en.json`/`de.json`, `profile` namespace):
  `language`, `english`, `german`.

## Error handling

- `PUT /preferences` failure: inline error indicator near the affected
  control; value stays at last-confirmed state (no optimistic UI to roll
  back).
- `GET /preferences` failure: fall back to the same client-side defaults
  the backend uses, so the UI still renders sensible values.

## Testing

- `data/db.py`: unit tests for `upsert_preferences` — row doesn't exist yet
  (creates with defaults + provided fields), row exists (partial update
  only touches provided fields), `get_preferences` default-fallback when no
  row exists.
- `backend/routes/preferences.py`: route tests for auth-gating (401 without
  session cookie) and GET/PUT round-trip.
- Frontend: test for the goal stepper's debounce behavior (rapid clicks →
  single call after the delay).

## Out of scope

- Locale auto-detection via `middleware.ts`.
- Languages beyond `en`/`de`.
- Any change to the `goals` table or goals UI.
