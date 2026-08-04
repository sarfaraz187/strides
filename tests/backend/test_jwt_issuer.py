import time

import jwt as pyjwt
import pytest

from backend.jwt_issuer import PUBLIC_KEY, get_jwks, mint_token


def test_mint_token_contains_user_id_claim():
    token = mint_token("user-123")
    payload = pyjwt.decode(
        token, PUBLIC_KEY, algorithms=["RS256"], audience="strides-mcp"
    )
    assert payload["sub"] == "user-123"


def test_mint_token_expires_in_five_minutes():
    token = mint_token("user-123")
    payload = pyjwt.decode(
        token, PUBLIC_KEY, algorithms=["RS256"], audience="strides-mcp"
    )
    assert 290 <= (payload["exp"] - payload["iat"]) <= 310


def test_mint_token_rejected_after_expiry(monkeypatch):
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() - 400)
    token = mint_token("user-123")

    with pytest.raises(pyjwt.ExpiredSignatureError):
        pyjwt.decode(token, PUBLIC_KEY, algorithms=["RS256"], audience="strides-mcp")


def test_get_jwks_returns_public_key_in_jwks_format():
    jwks = get_jwks()
    assert "keys" in jwks
    assert jwks["keys"][0]["kty"] == "RSA"
    assert jwks["keys"][0]["kid"] == "strides-1"
