import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "strides.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            user_email TEXT PRIMARY KEY,
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_token(user_email, access_token, refresh_token, expires_at):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO tokens (user_email, access_token, refresh_token, expires_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_email) DO UPDATE SET
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            expires_at = excluded.expires_at
    """,
        (user_email, access_token, refresh_token, expires_at),
    )

    conn.commit()
    conn.close()


def get_token(user_email: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT access_token, refresh_token, expires_at FROM tokens WHERE user_email = ?
        """,
        (user_email,),
    )
    result = cursor.fetchone()

    conn.commit()
    conn.close()
    return result
