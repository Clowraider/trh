"""CSRF token generation and validation.

Authenticated requests use the csrf_token stored in the server-side session.
The login form uses a token stored in the signed Flask session because there is
no server-side session yet.
"""

import secrets

from flask import request, session as flask_session

from trh.auth.sessions import validate_session_token


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def get_expected_csrf_token() -> str | None:
    """Return the CSRF token expected for the current request."""
    session_token = request.cookies.get("session_token")
    db_session = validate_session_token(session_token)
    if db_session is not None:
        return db_session.get("csrf_token")
    return flask_session.get("csrf_token")


def validate_csrf_request() -> tuple[str, int] | None:
    """Validate the CSRF token for the current request.

    Returns an (error_message, status_code) tuple on failure, otherwise None.
    """
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    expected = get_expected_csrf_token()
    if not expected or token != expected:
        return "Token CSRF inválido o faltante.", 403
    return None
