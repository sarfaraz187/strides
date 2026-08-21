import os

import jwt
import requests
from cachetools import TTLCache
from jwt.algorithms import RSAAlgorithm

AUDIENCE = "strides-mcp"
JWKS_URL = os.environ.get(
    "STRIDES_JWKS_URL", "http://localhost:8000/.well-known/jwks.json"
)

_jwks_cache = TTLCache(maxsize=1, ttl=300)  # Cache for 5 minutes


def _fetch_jwks() -> dict:
    response = requests.get(JWKS_URL)
    response.raise_for_status()
    return response.json()


def _get_signing_key(token: str) -> RSAAlgorithm:
    if "jwks" not in _jwks_cache:
        _jwks_cache["jwks"] = _fetch_jwks()
    jwks = _jwks_cache["jwks"]

    header = jwt.get_unverified_header(token)
    for key in jwks["keys"]:
        if key["kid"] == header["kid"]:
            return jwt.algorithms.RSAAlgorithm.from_jwk(key)

    raise jwt.InvalidTokenError(f"No matching key for kid={header.get('kid')}")


def verify_bearer_token(token: str) -> str:
    signing_key = _get_signing_key(token)
    payload = jwt.decode(token, signing_key, algorithms=["RS256"], audience=AUDIENCE)
    return payload["sub"]
