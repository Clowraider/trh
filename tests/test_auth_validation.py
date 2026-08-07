import pytest

from trh.auth.validation import (
    validate_email,
    validate_nombre,
    validate_notas,
    validate_password,
    validate_usuario,
)


@pytest.mark.parametrize(
    "usuario,expected_error",
    [
        ("", "El usuario es obligatorio."),
        ("ab", "El usuario debe tener entre 3 y 50 caracteres."),
        ("a" * 51, "El usuario debe tener entre 3 y 50 caracteres."),
        ("user-name", "El usuario solo puede contener letras, números y guiones bajos."),
        ("user name", "El usuario solo puede contener letras, números y guiones bajos."),
    ],
)
def test_validate_usuario_rejects_invalid_values(usuario, expected_error):
    assert validate_usuario(usuario) == expected_error


def test_validate_usuario_accepts_valid_value():
    assert validate_usuario("valid_user_123") is None


@pytest.mark.parametrize(
    "email,expected_error",
    [
        ("", "El email es obligatorio."),
        ("not-an-email", "El email no tiene un formato válido."),
        ("missing@tld", "El email no tiene un formato válido."),
        ("spaces in@email.com", "El email no tiene un formato válido."),
    ],
)
def test_validate_email_rejects_invalid_values(email, expected_error):
    assert validate_email(email) == expected_error


def test_validate_email_accepts_valid_value():
    assert validate_email("user@example.com") is None


@pytest.mark.parametrize(
    "password,expected_error",
    [
        ("", "La contraseña es obligatoria."),
        ("short", "La contraseña debe tener al menos 8 caracteres."),
    ],
)
def test_validate_password_rejects_invalid_values(password, expected_error):
    assert validate_password(password) == expected_error


def test_validate_password_accepts_valid_value():
    assert validate_password("long Enough 1") is None


@pytest.mark.parametrize(
    "nombre,expected_error",
    [
        ("", "El nombre es obligatorio."),
        ("a" * 101, "El nombre no puede superar los 100 caracteres."),
    ],
)
def test_validate_nombre_rejects_invalid_values(nombre, expected_error):
    assert validate_nombre(nombre) == expected_error


def test_validate_nombre_accepts_valid_value():
    assert validate_nombre("Ana García") is None


def test_validate_notas_rejects_too_long_value():
    assert validate_notas("a" * 2001) == "Las notas no pueden superar los 2000 caracteres."


@pytest.mark.parametrize("notas", [None, "", "a" * 2000])
def test_validate_notas_accepts_valid_values(notas):
    assert validate_notas(notas) is None
