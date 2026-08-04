import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm


@pytest.fixture
def rsa_keypair():
    """Generates a real RSA keypair and a matching JWKS dict, so tests can sign
    with the private key and verify against a JWKS response that actually matches."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk["kid"] = "strides-1"
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"

    return private_pem, {"keys": [jwk]}
