import os

import requests

_EXTENSION_BY_CONTENT_TYPE = {"image/jpeg": "jpg", "image/png": "png"}


def _bucket_object_url(path: str) -> str:
    base_url = os.environ["SUPABASE_URL"]
    return f"{base_url}/storage/v1/object/avatars/{path}"


def _bucket_public_url(path: str) -> str:
    base_url = os.environ["SUPABASE_URL"]
    return f"{base_url}/storage/v1/object/public/avatars/{path}"


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
    return _bucket_public_url(path)


def delete_avatar(url: str | None) -> None:
    if url is None:
        return
    path = url.rsplit("/avatars/", maxsplit=1)[-1]
    response = requests.delete(
        _bucket_object_url(path), headers=_auth_headers(), timeout=10
    )
    response.raise_for_status()
