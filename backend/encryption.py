import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_SIZE = 12


def _load_key() -> bytes:
    encoded_key = os.environ["TOKEN_ENCRYPTION_KEY"]
    return base64.urlsafe_b64decode(encoded_key)


def encrypt(plaintext: str) -> str:
    key = _load_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_SIZE)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    key = _load_key()
    aesgcm = AESGCM(key)
    raw = base64.urlsafe_b64decode(ciphertext)
    nonce, encrypted = raw[:NONCE_SIZE], raw[NONCE_SIZE:]
    plaintext = aesgcm.decrypt(nonce, encrypted, None)
    return plaintext.decode("utf-8")
