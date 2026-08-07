"""Input validation helpers for users and auth forms."""

import re


MAX_USUARIO_LENGTH = 50
MIN_USUARIO_LENGTH = 3
MAX_NOMBRE_LENGTH = 100
MAX_NOTAS_LENGTH = 2000

_USUARIO_RE = re.compile(r"^[a-zA-Z0-9_]+$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_usuario(usuario: str) -> str | None:
    """Return an error message if usuario is invalid, otherwise None."""
    if not usuario:
        return "El usuario es obligatorio."
    if len(usuario) < MIN_USUARIO_LENGTH or len(usuario) > MAX_USUARIO_LENGTH:
        return f"El usuario debe tener entre {MIN_USUARIO_LENGTH} y {MAX_USUARIO_LENGTH} caracteres."
    if not _USUARIO_RE.match(usuario):
        return "El usuario solo puede contener letras, números y guiones bajos."
    return None


def validate_email(email: str) -> str | None:
    """Return an error message if email is invalid, otherwise None."""
    if not email:
        return "El email es obligatorio."
    if len(email) > 255 or not _EMAIL_RE.match(email):
        return "El email no tiene un formato válido."
    return None


def validate_password(password: str) -> str | None:
    """Return an error message if password is invalid, otherwise None."""
    if not password:
        return "La contraseña es obligatoria."
    if len(password) < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    return None


def validate_nombre(nombre: str) -> str | None:
    """Return an error message if nombre is invalid, otherwise None."""
    if not nombre:
        return "El nombre es obligatorio."
    if len(nombre) > MAX_NOMBRE_LENGTH:
        return f"El nombre no puede superar los {MAX_NOMBRE_LENGTH} caracteres."
    return None


def validate_notas(notas: str | None) -> str | None:
    """Return an error message if notas exceed the limit, otherwise None."""
    if notas and len(notas) > MAX_NOTAS_LENGTH:
        return f"Las notas no pueden superar los {MAX_NOTAS_LENGTH} caracteres."
    return None
