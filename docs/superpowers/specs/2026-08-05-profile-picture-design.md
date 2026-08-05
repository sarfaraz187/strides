# Profile picture upload — design

## Context

The avatar shown on the profile screen, dashboard header, and sidebar is
currently just initials (`mockUser.initials`) in a colored circle — no
actual picture support exists. This is a separate, independent piece of
work from [[2026-08-05-profile-preferences-design]] (preferences
persistence/language) — different concerns (file storage/upload vs. a
Postgres column on an existing table).

## Storage

- Supabase Storage bucket `avatars`, **private** — public read was the
  original plan, but avatars are personal data tied to a real user
  identity, so access should require the same session auth as everything
  else, not just an unguessable path. Signed URLs (~1hr expiry), generated
  server-side on demand, not stored.
- `users.avatar_path TEXT NULL` column, added via migration — stores the
  bucket-relative object path (`{user_id}.{ext}`), not a URL. A URL would
  either be unsigned (defeats the point of a private bucket) or a signed
  URL that expires and goes stale sitting in the database.

## Backend

- `data/db.py`: `update_avatar_path(user_id: str, path: str | None) -> None`.
- `backend/storage.py`:
  - `upload_avatar(user_id, content, content_type) -> str` — uploads,
    returns the bucket-relative path.
  - `create_signed_url(path: str, expires_in: int = 3600) -> str` — calls
    Supabase's `POST /storage/v1/object/sign/{bucket}/{path}`, returns a
    full signed URL.
  - `delete_avatar(path: str | None) -> None` — deletes by path; no-op for
    `None`.
- New route `POST /profile/avatar` (in `backend/routes/profile.py`, new
  file, or added to `auth.py` if that reads cleaner once implementing):
  - Session-cookie auth, same **dependency** as `/auth/me`.
  - Multipart upload. Server-side validation (never trust client-side
    checks alone): content-type must be `image/jpeg` or `image/png`; size
    must be ≤5MB.
  - If the user already has an `avatar_path`, delete the old file from the
    bucket first.
  - Uploads new file to `avatars/{user_id}.{ext}`, updates
    `users.avatar_path`, returns a freshly signed URL as `avatar_url`.
- `/auth/me`: if `avatar_path` is set, calls `create_signed_url` and
  returns it as `avatar_url`; `null` otherwise. Every `/auth/me` call
  mints a fresh signed URL — the frontend never sees or stores the raw
  path, and the URL naturally rotates instead of going stale.
- The frontend `User` type gains `avatar_url: string | null` — same shape
  as originally planned; the signing happens entirely server-side, so this
  is the only frontend-visible surface of the change.

## Frontend

- `auth-context.tsx`: add `avatar_url` to the `User` type.
- New shared `<Avatar>` component: renders `avatar_url` as an `<img>` when
  present, otherwise falls back to initials derived from `user.name`
  (first letters of first/last word). Replaces the three current
  `mockUser.initials` call sites: `profile-screen.tsx`,
  `dashboard-screen.tsx`, `sidebar.tsx`.
- Profile screen: avatar circle becomes clickable, opening a hidden
  `<input type="file" accept="image/jpeg,image/png">`. Client-side
  pre-check (type/size, reject files >5MB before uploading, to avoid a
  wasted round-trip) runs before the request fires.
- `useMutation` posts to `/profile/avatar`; on success, updates the
  `["auth", "me"]` query cache with the new `avatar_url` so all three
  avatar locations re-render via the shared auth context — no separate
  cache invalidation needed per screen.
- UI states: spinner overlay on the avatar circle while uploading; inline
  error text on rejection (wrong type, too large) or upload failure.

## Testing

- Backend: route tests for content-type/size rejection, successful upload
  updates `users.avatar_url` and deletes the prior file, auth-gating
  (401 without session cookie).
- Frontend: `<Avatar>` fallback-to-initials test; file-picker validation
  test (rejects non-image/oversized files before any network call).

## Out of scope

- Cropping/resizing UI.
- Multiple avatar sizes/thumbnails.
- Any change to `preferences`/language work (tracked separately in
  [[2026-08-05-profile-preferences-design]]).
