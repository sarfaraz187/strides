from unittest.mock import Mock, patch

import pytest

from backend.storage import delete_avatar, upload_avatar


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")


def test_upload_avatar_puts_object_and_returns_public_url():
    with patch("backend.storage.requests.put") as mock_put:
        mock_put.return_value = Mock(status_code=200, raise_for_status=Mock())

        url = upload_avatar("user-123", b"fake-image-bytes", "image/jpeg")

    mock_put.assert_called_once()
    call_args = mock_put.call_args
    assert call_args.args[0] == (
        "https://project-ref.supabase.co/storage/v1/object/avatars/user-123.jpg"
    )
    assert call_args.kwargs["headers"]["Authorization"] == "Bearer service-role-key"
    assert call_args.kwargs["headers"]["Content-Type"] == "image/jpeg"
    assert call_args.kwargs["data"] == b"fake-image-bytes"
    assert url == (
        "https://project-ref.supabase.co/storage/v1/object/public/avatars/user-123.jpg"
    )


def test_delete_avatar_removes_object_by_url():
    with patch("backend.storage.requests.delete") as mock_delete:
        mock_delete.return_value = Mock(status_code=200, raise_for_status=Mock())

        delete_avatar(
            "https://project-ref.supabase.co/storage/v1/object/public/avatars/user-123.jpg"
        )

    mock_delete.assert_called_once_with(
        "https://project-ref.supabase.co/storage/v1/object/avatars/user-123.jpg",
        headers={"Authorization": "Bearer service-role-key"},
        timeout=10,
    )


def test_delete_avatar_noop_for_none():
    with patch("backend.storage.requests.delete") as mock_delete:
        delete_avatar(None)

    mock_delete.assert_not_called()
