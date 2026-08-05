import os
import secrets
from dataclasses import dataclass
from datetime import date, datetime

import psycopg

from backend.encryption import decrypt, encrypt


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
            CREATE TABLE IF NOT EXISTS goals (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                description TEXT NOT NULL,
                target_value NUMERIC,
                deadline DATE,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """)
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_path TEXT")
        conn.execute("ALTER TABLE users DROP COLUMN IF EXISTS avatar_url")
        conn.execute(
            "ALTER TABLE preferences ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en'"
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
        conn.execute(
            "UPDATE users SET avatar_path = %s WHERE id = %s", (path, user_id)
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


@dataclass
class Preferences:
    weekly_goal_km: float
    units: str
    notifications_enabled: bool
    language: str


_DEFAULT_PREFERENCES = Preferences(
    weekly_goal_km=30, units="km", notifications_enabled=True, language="en"
)


def upsert_preferences(
    user_id: str,
    weekly_goal_km: float | None = None,
    units: str | None = None,
    notifications_enabled: bool | None = None,
    language: str | None = None,
) -> Preferences:
    current = get_preferences(user_id)
    weekly_goal_km = current.weekly_goal_km if weekly_goal_km is None else weekly_goal_km
    units = current.units if units is None else units
    notifications_enabled = (
        current.notifications_enabled if notifications_enabled is None else notifications_enabled
    )
    language = current.language if language is None else language

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO preferences (user_id, weekly_goal_km, units, notifications_enabled, language)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                weekly_goal_km = excluded.weekly_goal_km,
                units = excluded.units,
                notifications_enabled = excluded.notifications_enabled,
                language = excluded.language
            """,
            (user_id, weekly_goal_km, units, notifications_enabled, language),
        )
        conn.commit()
    return Preferences(
        weekly_goal_km=float(weekly_goal_km),
        units=units,
        notifications_enabled=notifications_enabled,
        language=language,
    )


def get_preferences(user_id: str) -> Preferences:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT weekly_goal_km, units, notifications_enabled, language
            FROM preferences WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return _DEFAULT_PREFERENCES
    weekly_goal_km, units, notifications_enabled, language = row
    return Preferences(
        weekly_goal_km=float(weekly_goal_km),
        units=units,
        notifications_enabled=notifications_enabled,
        language=language,
    )


@dataclass
class Goal:
    id: str
    description: str
    target_value: float | None
    deadline: date | None
    created_at: datetime


def create_goal(
    user_id: str, description: str, target_value: float | None, deadline: date | None
) -> str:
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO goals (user_id, description, target_value, deadline)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, description, target_value, deadline),
        ).fetchone()
        conn.commit()
        return str(row[0])


def list_goals(user_id: str) -> list[Goal]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, description, target_value, deadline, created_at
            FROM goals WHERE user_id = %s ORDER BY created_at
            """,
            (user_id,),
        ).fetchall()
    return [
        Goal(
            id=str(goal_id),
            description=description,
            target_value=float(target_value) if target_value is not None else None,
            deadline=deadline,
            created_at=created_at,
        )
        for goal_id, description, target_value, deadline, created_at in rows
    ]
