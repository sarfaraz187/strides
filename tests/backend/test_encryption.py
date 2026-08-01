import base64
import os

import pytest

from backend.encryption import decrypt, encrypt


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key)


def test_encrypt_then_decrypt_returns_original():
    plaintext = "ya29.example_token"
    ciphertext = encrypt(plaintext)

    assert ciphertext != plaintext
    assert decrypt(ciphertext) == plaintext


def test_encrypt_is_nondeterministic():
    plaintext = "ya29.example_token"
    ciphertext = encrypt(plaintext)

    ciphertext_twice = encrypt(plaintext)

    assert ciphertext_twice != ciphertext


def test_decrypt_rejects_tampered_ciphertext():
    ciphertext = encrypt("secret-value")
    tampered = ciphertext[:-4] + ("AAAA" if ciphertext[-4:] != "AAAA" else "BBBB")

    with pytest.raises(Exception):
        decrypt(tampered)
