import time
from pathlib import Path

import jwt
from jwt.algorithms import RSAAlgorithm

_KEYS_DIR = Path(__file__).parent / "keys"
PRIVATE_KEY = (_KEYS_DIR / "private.pem").read_text()
PUBLIC_KEY = (_KEYS_DIR / "public.pem").read_text()
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
