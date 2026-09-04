from unittest.mock import Mock, patch

import pytest

from backend.storage import create_signed_url, delete_avatar, upload_avatar


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("SUPABASE_STORAGE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_STORAGE_SERVICE_ROLE_KEY", "service-role-key")


def test_upload_avatar_puts_object_and_returns_bucket_relative_path():
    with patch("backend.storage.requests.put") as mock_put:
        mock_put.return_value = Mock(status_code=200, raise_for_status=Mock())

        path = upload_avatar("user-123", b"fake-image-bytes", "image/jpeg")

    mock_put.assert_called_once()
    call_args = mock_put.call_args
    assert call_args.args[0] == (
        "https://project-ref.supabase.co/storage/v1/object/avatars/user-123.jpg"
    )
    assert call_args.kwargs["headers"]["Authorization"] == "Bearer service-role-key"
    assert call_args.kwargs["headers"]["apikey"] == "service-role-key"
    assert call_args.kwargs["headers"]["Content-Type"] == "image/jpeg"
    assert call_args.kwargs["data"] == b"fake-image-bytes"
    assert path == "user-123.jpg"


def test_create_signed_url_requests_signature_and_builds_full_url():
    with patch("backend.storage.requests.post") as mock_post:
        mock_post.return_value = Mock(
            status_code=200,
            raise_for_status=Mock(),
            json=Mock(
                return_value={
                    "signedURL": "/object/sign/avatars/user-123.jpg?token=abc"
                }
            ),
        )

        url = create_signed_url("user-123.jpg", expires_in=3600)

    mock_post.assert_called_once_with(
        "https://project-ref.supabase.co/storage/v1/object/sign/avatars/user-123.jpg",
        headers={"Authorization": "Bearer service-role-key", "apikey": "service-role-key"},
        json={"expiresIn": 3600},
        timeout=10,
    )
    assert url == (
        "https://project-ref.supabase.co/storage/v1/object/sign/avatars/user-123.jpg?token=abc"
    )


def test_delete_avatar_removes_object_by_path():
    with patch("backend.storage.requests.delete") as mock_delete:
        mock_delete.return_value = Mock(status_code=200, raise_for_status=Mock())

        delete_avatar("user-123.jpg")

    mock_delete.assert_called_once_with(
        "https://project-ref.supabase.co/storage/v1/object/avatars/user-123.jpg",
        headers={"Authorization": "Bearer service-role-key", "apikey": "service-role-key"},
        timeout=10,
    )


def test_delete_avatar_noop_for_none():
    with patch("backend.storage.requests.delete") as mock_delete:
        delete_avatar(None)

    mock_delete.assert_not_called()
