import time
from unittest.mock import patch

import jwt as pyjwt
import pytest

from mcp_servers.fit_server.mcp_auth import verify_bearer_token


def _sign(private_key: str, user_id: str, **overrides) -> str:
    payload = {
        "sub": user_id,
        "aud": "strides-mcp",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    payload.update(overrides)
    return pyjwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "strides-1"})


def test_verify_bearer_token_returns_user_id_for_valid_token(rsa_keypair):
    private_key, jwks = rsa_keypair
    with patch("mcp_servers.fit_server.mcp_auth._fetch_jwks", return_value=jwks):
        token = _sign(private_key, "user-123")
        assert verify_bearer_token(token) == "user-123"


def test_verify_bearer_token_rejects_expired_token(rsa_keypair):
    private_key, jwks = rsa_keypair
    with patch("mcp_servers.fit_server.mcp_auth._fetch_jwks", return_value=jwks):
        token = _sign(private_key, "user-123", exp=int(time.time()) - 10)
        with pytest.raises(Exception):
            verify_bearer_token(token)


def test_verify_bearer_token_rejects_wrong_audience(rsa_keypair):
    private_key, jwks = rsa_keypair
    with patch("mcp_servers.fit_server.mcp_auth._fetch_jwks", return_value=jwks):
        token = _sign(private_key, "user-123", aud="someone-else")
        with pytest.raises(Exception):
            verify_bearer_token(token)
