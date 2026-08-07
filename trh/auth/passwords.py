"""Password hashing and verification utilities."""

from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password: str) -> str:
    """Hash a plaintext password using scrypt."""
    return generate_password_hash(password, method="scrypt")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored scrypt hash."""
    return check_password_hash(password_hash, password)
