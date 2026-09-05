import os
import secrets
from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from backend.encryption import decrypt, encrypt

pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=5, open=True)


def get_connection() -> psycopg.Connection:
    return pool.connection()


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email TEXT UNIQUE NOT NULL,
                google_sub TEXT UNIQUE NOT NULL,
                name TEXT,
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                weekly_goal_km NUMERIC NOT NULL,
                units TEXT NOT NULL,
                notifications_enabled BOOLEAN NOT NULL,
                language TEXT NOT NULL DEFAULT 'en'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL DEFAULT 'New chat',
                pinned BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_user_id_updated_at "
            "ON conversations (user_id, pinned DESC, updated_at DESC)"
        )

        # One-time destructive migration: `messages`/`conversation_summaries` predate
        # the `conversations` table and have no `conversation_id` to backfill against.
        # Per the multi-chat-threads design doc, existing chat history is discarded
        # rather than migrated, so drop-and-recreate only if the old shape is present.
        old_shape = conn.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'messages' AND column_name = 'user_id'
        """).fetchone()
        if old_shape is not None:
            conn.execute("DROP TABLE IF EXISTS conversation_summaries CASCADE")
            conn.execute("DROP TABLE IF EXISTS messages CASCADE")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_id "
            "ON messages (conversation_id, id DESC)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                conversation_id UUID PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
                summary_text TEXT NOT NULL,
                through_message_id INTEGER NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id SERIAL PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                fact TEXT NOT NULL,
                category TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories (user_id)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                action_href TEXT,
                status TEXT NOT NULL DEFAULT 'unread',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                resolved_at TIMESTAMPTZ
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications (user_id)"
        )
        # Partial unique index, not a plain UNIQUE constraint: a *resolved*
        # notification of a given (user, type) must not block a fresh one
        # from being created later if the same problem recurs.
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_unresolved_dedup
            ON notifications (user_id, type)
            WHERE status != 'resolved'
        """)
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_path TEXT")
        conn.execute("ALTER TABLE users DROP COLUMN IF EXISTS avatar_url")
        conn.execute(
            "ALTER TABLE preferences ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en'"
        )
        conn.execute(
            "ALTER TABLE oauth_tokens ADD COLUMN IF NOT EXISTS calendar_id TEXT"
        )
        conn.execute(
            "ALTER TABLE preferences ADD COLUMN IF NOT EXISTS location_lat DOUBLE PRECISION"
        )
        conn.execute(
            "ALTER TABLE preferences ADD COLUMN IF NOT EXISTS location_lon DOUBLE PRECISION"
        )
        conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS tokens_used INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()


def find_or_create_user(email: str, google_sub: str, name: str) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE google_sub = %s", (google_sub,)
        ).fetchone()
        if row is not None:
            return str(row[0])

        row = conn.execute(
            """
            INSERT INTO users (email, google_sub, name)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (email, google_sub, name),
        ).fetchone()
        conn.commit()
        return str(row[0])


def get_user(user_id: str) -> tuple[str, str, datetime, str | None] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT email, name, created_at, avatar_path FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    email, name, created_at, avatar_path = row
    return email, name, created_at, avatar_path


def update_avatar_path(user_id: str, path: str | None) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE users SET avatar_path = %s WHERE id = %s", (path, user_id))
        conn.commit()


def get_tokens_used(user_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT tokens_used FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    return row[0] if row is not None else 0


def increment_tokens_used(user_id: str, amount: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET tokens_used = tokens_used + %s WHERE id = %s",
            (amount, user_id),
        )
        conn.commit()


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
            (
                user_id,
                provider,
                encrypt(access_token),
                encrypt(refresh_token),
                expires_at,
            ),
        )
        conn.commit()


def save_message(conversation_id: str, role: str, content: str | list) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (conversation_id, role, Json(content)),
        ).fetchone()
        conn.execute(
            "UPDATE conversations SET updated_at = now() WHERE id = %s",
            (conversation_id,),
        )
        conn.commit()
    return row[0]


def get_messages(
    conversation_id: str, before_id: int | None, limit: int
) -> tuple[list[dict], bool]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, created_at FROM messages
            WHERE conversation_id = %s AND (%s::int IS NULL OR id < %s)
                AND jsonb_typeof(content) = 'string'
            ORDER BY id DESC
            LIMIT %s
            """,
            (conversation_id, before_id, before_id, limit + 1),
        ).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    messages = [
        {"id": row[0], "role": row[1], "content": row[2], "created_at": row[3]}
        for row in rows
    ]
    return messages, has_more


def get_messages_since(conversation_id: str, after_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content FROM messages
            WHERE conversation_id = %s AND id > %s
            ORDER BY id
            """,
            (conversation_id, after_id),
        ).fetchall()
    return [{"id": row[0], "role": row[1], "content": row[2]} for row in rows]


def get_conversation_summary(conversation_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT summary_text, through_message_id
            FROM conversation_summaries WHERE conversation_id = %s
            """,
            (conversation_id,),
        ).fetchone()
    if row is None:
        return None
    return {"summary_text": row[0], "through_message_id": row[1]}


def upsert_conversation_summary(
    conversation_id: str, summary_text: str, through_message_id: int
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversation_summaries
                (conversation_id, summary_text, through_message_id, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (conversation_id) DO UPDATE SET
                summary_text = excluded.summary_text,
                through_message_id = excluded.through_message_id,
                updated_at = excluded.updated_at
            """,
            (conversation_id, summary_text, through_message_id),
        )
        conn.commit()


class EmptyTitleError(ValueError):
    pass


def create_conversation(user_id: str, title: str) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "INSERT INTO conversations (user_id, title) VALUES (%s, %s) RETURNING id",
            (user_id, title),
        ).fetchone()
        conn.commit()
    return str(row[0])


def get_conversation(conversation_id: str, user_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, title, pinned, created_at, updated_at
            FROM conversations WHERE id = %s AND user_id = %s
            """,
            (conversation_id, user_id),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": str(row[0]),
        "title": row[1],
        "pinned": row[2],
        "created_at": row[3],
        "updated_at": row[4],
    }


def list_conversations(user_id: str, search: str | None = None) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, pinned, created_at, updated_at
            FROM conversations
            WHERE user_id = %s AND (%s::text IS NULL OR title ILIKE '%%' || %s || '%%')
            ORDER BY pinned DESC, updated_at DESC
            """,
            (user_id, search, search),
        ).fetchall()
    return [
        {
            "id": str(row[0]),
            "title": row[1],
            "pinned": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }
        for row in rows
    ]


def rename_conversation(conversation_id: str, user_id: str, title: str) -> None:
    if not title.strip():
        raise EmptyTitleError("title cannot be empty")
    with get_connection() as conn:
        conn.execute(
            "UPDATE conversations SET title = %s WHERE id = %s AND user_id = %s",
            (title, conversation_id, user_id),
        )
        conn.commit()


def set_pinned(conversation_id: str, user_id: str, pinned: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE conversations SET pinned = %s WHERE id = %s AND user_id = %s",
            (pinned, conversation_id, user_id),
        )
        conn.commit()


def delete_conversation(conversation_id: str, user_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM conversations WHERE id = %s AND user_id = %s",
            (conversation_id, user_id),
        )
        conn.commit()


def save_memory(user_id: str, fact: str, category: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO memories (user_id, fact, category) VALUES (%s, %s, %s)",
            (user_id, fact, category),
        )
        conn.commit()


def get_memories(user_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT fact, category FROM memories WHERE user_id = %s ORDER BY id",
            (user_id,),
        ).fetchall()
    return [{"fact": row[0], "category": row[1]} for row in rows]


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


def get_calendar_id(user_id: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT calendar_id FROM oauth_tokens
            WHERE user_id = %s AND provider = 'calendar'
            """,
            (user_id,),
        ).fetchone()
    return row[0] if row is not None else None


def save_calendar_id(user_id: str, calendar_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE oauth_tokens SET calendar_id = %s
            WHERE user_id = %s AND provider = 'calendar'
            """,
            (calendar_id, user_id),
        )
        conn.commit()


@dataclass
class Notification:
    id: int
    user_id: str
    type: str
    action_href: str | None
    status: str
    created_at: datetime


def create_notification(
    user_id: str, type_: str, action_href: str | None = None
) -> None:
    # No message text here on purpose: display text is derived from `type`
    # client-side via next-intl (`notifications.types.<type>`), so it's
    # correctly localized instead of being frozen in whatever language the
    # backend happened to write at insert time.
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO notifications (user_id, type, action_href)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, type) WHERE status != 'resolved' DO NOTHING
            """,
            (user_id, type_, action_href),
        )
        conn.commit()


def resolve_notification(user_id: str, type_: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE notifications SET status = 'resolved', resolved_at = now()
            WHERE user_id = %s AND type = %s AND status != 'resolved'
            """,
            (user_id, type_),
        )
        conn.commit()


def list_notifications(user_id: str) -> list[Notification]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, type, action_href, status, created_at
            FROM notifications
            WHERE user_id = %s AND status != 'resolved'
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [
        Notification(
            id=row[0],
            user_id=str(row[1]),
            type=row[2],
            action_href=row[3],
            status=row[4],
            created_at=row[5],
        )
        for row in rows
    ]


def mark_all_read(user_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE notifications SET status = 'read' WHERE user_id = %s AND status = 'unread'",
            (user_id,),
        )
        conn.commit()


@dataclass
class Preferences:
    weekly_goal_km: float
    units: str
    notifications_enabled: bool
    language: str
    location_lat: float | None = None
    location_lon: float | None = None


_DEFAULT_PREFERENCES = Preferences(
    weekly_goal_km=30, units="km", notifications_enabled=True, language="en"
)


def upsert_preferences(
    user_id: str,
    weekly_goal_km: float | None = None,
    units: str | None = None,
    notifications_enabled: bool | None = None,
    language: str | None = None,
    location_lat: float | None = None,
    location_lon: float | None = None,
) -> Preferences:
    current = get_preferences(user_id)
    weekly_goal_km = (
        current.weekly_goal_km if weekly_goal_km is None else weekly_goal_km
    )
    units = current.units if units is None else units
    notifications_enabled = (
        current.notifications_enabled
        if notifications_enabled is None
        else notifications_enabled
    )
    language = current.language if language is None else language
    location_lat = current.location_lat if location_lat is None else location_lat
    location_lon = current.location_lon if location_lon is None else location_lon

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO preferences
                (user_id, weekly_goal_km, units, notifications_enabled, language, location_lat, location_lon)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                weekly_goal_km = excluded.weekly_goal_km,
                units = excluded.units,
                notifications_enabled = excluded.notifications_enabled,
                language = excluded.language,
                location_lat = excluded.location_lat,
                location_lon = excluded.location_lon
            """,
            (
                user_id,
                weekly_goal_km,
                units,
                notifications_enabled,
                language,
                location_lat,
                location_lon,
            ),
        )
        conn.commit()
    return Preferences(
        weekly_goal_km=float(weekly_goal_km),
        units=units,
        notifications_enabled=notifications_enabled,
        language=language,
        location_lat=location_lat,
        location_lon=location_lon,
    )


def get_preferences(user_id: str) -> Preferences:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT weekly_goal_km, units, notifications_enabled, language, location_lat, location_lon
            FROM preferences WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return _DEFAULT_PREFERENCES
    (
        weekly_goal_km,
        units,
        notifications_enabled,
        language,
        location_lat,
        location_lon,
    ) = row
    return Preferences(
        weekly_goal_km=float(weekly_goal_km),
        units=units,
        notifications_enabled=notifications_enabled,
        language=language,
        location_lat=location_lat,
        location_lon=location_lon,
    )
