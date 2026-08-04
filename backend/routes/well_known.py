from fastapi import APIRouter

from backend.jwt_issuer import get_jwks

router = APIRouter()


@router.get("/.well-known/jwks.json")
def jwks():
    return get_jwks()
