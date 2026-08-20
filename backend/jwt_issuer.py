import base64
import os
import time
from pathlib import Path

import jwt
from jwt.algorithms import RSAAlgorithm

_KEYS_DIR = Path(__file__).parent / "keys"


def _load_key(env_var: str, filename: str) -> str:
    if encoded := os.environ.get(env_var):
        return base64.b64decode(encoded).decode()
    return (_KEYS_DIR / filename).read_text()


PRIVATE_KEY = _load_key("PRIVATE_KEY_B64", "private.pem")
PUBLIC_KEY = _load_key("PUBLIC_KEY_B64", "public.pem")
KID = "strides-1"
AUDIENCE = "strides-mcp"
TOKEN_TTL_SECONDS = 300


def mint_token(user_id: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }

    return jwt.encode(payload, PRIVATE_KEY, algorithm="RS256", headers={"kid": KID})


def get_jwks() -> dict:
    algorithm = RSAAlgorithm(RSAAlgorithm.SHA256)
    key_obj = algorithm.prepare_key(PUBLIC_KEY)
    jwk = RSAAlgorithm.to_jwk(key_obj, as_dict=True)
    jwk["kid"] = KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return {"keys": [jwk]}
