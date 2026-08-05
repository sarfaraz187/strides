import os

import requests

_EXTENSION_BY_CONTENT_TYPE = {"image/jpeg": "jpg", "image/png": "png"}


def _bucket_object_url(path: str) -> str:
    base_url = os.environ["SUPABASE_URL"]
    return f"{base_url}/storage/v1/object/avatars/{path}"


def _bucket_sign_url(path: str) -> str:
    base_url = os.environ["SUPABASE_URL"]
    return f"{base_url}/storage/v1/object/sign/avatars/{path}"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ['SUPABASE_SERVICE_ROLE_KEY']}"}


def upload_avatar(user_id: str, content: bytes, content_type: str) -> str:
    extension = _EXTENSION_BY_CONTENT_TYPE[content_type]
    path = f"{user_id}.{extension}"

    response = requests.put(
        _bucket_object_url(path),
        headers={**_auth_headers(), "Content-Type": content_type, "x-upsert": "true"},
        data=content,
        timeout=10,
    )
    response.raise_for_status()
    return path


def create_signed_url(path: str, expires_in: int = 3600) -> str:
    response = requests.post(
        _bucket_sign_url(path),
        headers=_auth_headers(),
        json={"expiresIn": expires_in},
        timeout=10,
    )
    response.raise_for_status()
    signed_url = response.json()["signedURL"]
    base_url = os.environ["SUPABASE_URL"]
    return f"{base_url}/storage/v1{signed_url}"


def delete_avatar(path: str | None) -> None:
    if path is None:
        return
    response = requests.delete(
        _bucket_object_url(path), headers=_auth_headers(), timeout=10
    )
    response.raise_for_status()
