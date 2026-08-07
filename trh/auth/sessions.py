"""Server-side session management.

Tokens are generated with secrets.token_urlsafe and stored verbatim in the
sessions table. The cookie holds the raw token; the database is the source of
truth for validity and expiration.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import Request, Response

from trh.auth.repository import (
    create_session as repo_create_session,
    delete_session as repo_delete_session,
    get_session_by_token as repo_get_session_by_token,
)
from trh.auth.time_utils import utc_now


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def create_session_for_user(
    user_id: int,
    lifetime_hours: int = 24,
    request_obj: Request | None = None,
) -> tuple[str, str, datetime]:
    """Create a session and return (session_token, csrf_token, expires_at)."""
    session_token = _generate_token()
    csrf_token = _generate_token()
    expires_at = utc_now() + timedelta(hours=lifetime_hours)

    ip_address = None
    user_agent = None
    if request_obj is not None:
        ip_address = request_obj.remote_addr or None
        if request_obj.user_agent is not None:
            user_agent = request_obj.user_agent.string[:255] or None

    repo_create_session(
        session_token=session_token,
        user_id=user_id,
        expires_at=expires_at,
        csrf_token=csrf_token,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return session_token, csrf_token, expires_at


def validate_session_token(session_token: str | None) -> dict[str, Any] | None:
    """Return session+user data if token is valid and not expired."""
    if not session_token:
        return None
    session = repo_get_session_by_token(session_token)
    if session is None:
        return None
    expires_at = session.get("expires_at")
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < utc_now():
            repo_delete_session(session_token)
            return None
    return dict(session)


def delete_session(session_token: str | None) -> None:
    """Delete a session by token."""
    if session_token:
        repo_delete_session(session_token)


def set_session_cookie(
    response: Response,
    session_token: str,
    expires_at: datetime,
    secure: bool = True,
) -> None:
    """Attach the session cookie to a response."""
    response.set_cookie(
        "session_token",
        session_token,
        expires=expires_at,
        httponly=True,
        secure=secure,
        samesite="Lax",
        path="/",
    )
