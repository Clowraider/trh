import pytest

from trh.auth.passwords import hash_password, verify_password


def test_hash_password_produces_scrypt_hash():
    hashed = hash_password("correct horse battery staple")

    assert hashed.startswith("scrypt:")
    assert hashed != "correct horse battery staple"


def test_verify_password_accepts_correct_password():
    hashed = hash_password("my-secret-password")

    assert verify_password("my-secret-password", hashed) is True


@pytest.mark.parametrize("password", ["", "wrong", "my-secret-password "] )
def test_verify_password_rejects_incorrect_password(password):
    hashed = hash_password("my-secret-password")

    assert verify_password(password, hashed) is False
