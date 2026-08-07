import base64
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from data.db import (
    Preferences,
    create_session,
    delete_oauth_token,
    delete_session,
    find_or_create_user,
    get_connection,
    get_oauth_token,
    get_preferences,
    get_session_user_id,
    get_user,
    init_db,
    save_oauth_token,
    update_avatar_path,
    upsert_preferences,
)


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key)


@pytest.fixture(autouse=True)
def clean_schema():
    init_db()
    yield
    with get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS preferences CASCADE")
        conn.execute("DROP TABLE IF EXISTS oauth_tokens CASCADE")
        conn.execute("DROP TABLE IF EXISTS sessions CASCADE")
        conn.execute("DROP TABLE IF EXISTS users CASCADE")
        conn.commit()


def test_init_db_creates_users_table():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users' AND table_schema = 'public'"
        ).fetchall()
    columns = {row[0] for row in result}
    assert columns == {"id", "email", "google_sub", "name", "created_at", "avatar_path"}


def test_init_db_creates_preferences_table():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'preferences' AND table_schema = 'public'"
        ).fetchall()
    columns = {row[0] for row in result}
    assert columns == {
        "user_id",
        "weekly_goal_km",
        "units",
        "notifications_enabled",
        "language",
    }


def test_get_preferences_returns_defaults_when_no_row_exists():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    prefs = get_preferences(user_id)

    assert prefs == Preferences(
        weekly_goal_km=30, units="km", notifications_enabled=True, language="en"
    )


def test_upsert_preferences_creates_row_with_defaults_for_omitted_fields():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    prefs = upsert_preferences(user_id, units="mi")

    assert prefs == Preferences(
        weekly_goal_km=30, units="mi", notifications_enabled=True, language="en"
    )


def test_init_db_creates_sessions_table():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'sessions' AND table_schema = 'public'"
        ).fetchall()
    columns = {row[0] for row in result}
    assert columns == {"token", "user_id", "created_at", "expires_at"}


def test_init_db_creates_oauth_tokens_table():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'oauth_tokens' AND table_schema = 'public'"
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


def test_find_or_create_user_creates_new_user():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    assert user_id is not None


def test_init_db_is_idempotent():
    init_db()
    init_db()  # must not raise


def test_find_or_create_user_returns_same_id_for_existing_sub():
    first_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    second_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    assert first_id == second_id


def test_create_session_then_get_session_user_id_round_trips():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    token = create_session(user_id, expires_at)
    resolved_user_id = get_session_user_id(token)

    assert resolved_user_id == user_id


def test_get_session_user_id_returns_none_for_unknown_token():
    assert get_session_user_id(secrets.token_urlsafe(32)) is None


def test_get_session_user_id_returns_none_for_expired_session():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    token = create_session(user_id, expired_at)

    assert get_session_user_id(token) is None


def test_delete_session_invalidates_token():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    token = create_session(user_id, datetime.now(timezone.utc) + timedelta(days=7))

    delete_session(token)

    assert get_session_user_id(token) is None


def test_save_then_get_oauth_token_round_trips_decrypted():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    save_oauth_token(user_id, "health", "access-abc", "refresh-xyz", 1234567890)
    access_token, refresh_token, expires_at = get_oauth_token(user_id, "health")

    assert access_token == "access-abc"
    assert refresh_token == "refresh-xyz"
    assert expires_at == 1234567890


def test_oauth_token_stored_encrypted_at_rest():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    save_oauth_token(user_id, "health", "access-abc", "refresh-xyz", 1234567890)

    with get_connection() as conn:
        row = conn.execute(
            "SELECT access_token FROM oauth_tokens WHERE user_id = %s", (user_id,)
        ).fetchone()

    assert row[0] != "access-abc"


def test_save_oauth_token_upserts_on_conflict():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    save_oauth_token(user_id, "health", "access-1", "refresh-1", 100)
    save_oauth_token(user_id, "health", "access-2", "refresh-2", 200)

    access_token, refresh_token, expires_at = get_oauth_token(user_id, "health")

    assert (access_token, refresh_token, expires_at) == ("access-2", "refresh-2", 200)


def test_get_oauth_token_returns_none_when_absent():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    assert get_oauth_token(user_id, "health") is None


def test_delete_oauth_token_removes_row():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")
    save_oauth_token(user_id, "health", "access-abc", "refresh-xyz", 1234567890)

    delete_oauth_token(user_id, "health")

    assert get_oauth_token(user_id, "health") is None


def test_find_or_create_user_stores_name():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    email, name, created_at, avatar_path = get_user(user_id)

    assert email == "runner@example.com"
    assert name == "Runner Example"
    assert created_at is not None
    assert avatar_path is None


def test_get_user_returns_none_for_unknown_id():
    assert get_user(str(uuid.uuid4())) is None


def test_update_avatar_path_sets_and_clears_path():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    update_avatar_path(user_id, "user-123.jpg")
    _, _, _, avatar_path = get_user(user_id)
    assert avatar_path == "user-123.jpg"

    update_avatar_path(user_id, None)
    _, _, _, avatar_path_after_clear = get_user(user_id)
    assert avatar_path_after_clear is None


def test_upsert_preferences_then_get_preferences_round_trips():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    upsert_preferences(
        user_id, weekly_goal_km=30, units="km", notifications_enabled=True, language="en"
    )
    prefs = get_preferences(user_id)

    assert prefs == Preferences(
        weekly_goal_km=30, units="km", notifications_enabled=True, language="en"
    )


def test_upsert_preferences_partial_update_only_touches_provided_fields():
    user_id = find_or_create_user("runner@example.com", "google-sub-123", "Runner Example")

    upsert_preferences(
        user_id, weekly_goal_km=30, units="km", notifications_enabled=True, language="en"
    )
    upsert_preferences(user_id, language="de")

    prefs = get_preferences(user_id)

    assert prefs == Preferences(
        weekly_goal_km=30, units="km", notifications_enabled=True, language="de"
    )
