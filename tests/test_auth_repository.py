from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from trh.auth import repository


@pytest.fixture
def mock_connection():
    conn = MagicMock()
    cursor_ctx = MagicMock()
    cursor = MagicMock()
    cursor_ctx.__enter__ = MagicMock(return_value=cursor)
    cursor_ctx.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value = cursor_ctx
    return conn, cursor


@pytest.fixture(autouse=True)
def patch_get_connection(mock_connection):
    conn, _cursor = mock_connection
    with patch("trh.auth.repository.get_connection", return_value=conn):
        yield


def test_create_user_inserts_and_returns_id(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchone.return_value = {"id": 42}

    user_id = repository.create_user(
        usuario="jdoe",
        email="jdoe@example.com",
        password_hash="hash",
        nombre="John Doe",
        is_admin=False,
    )

    assert user_id == 42
    _conn.commit.assert_called_once()


def test_get_user_by_username_executes_select(mock_connection):
    _conn, cursor = mock_connection
    expected = {"id": 1, "usuario": "admin"}
    cursor.fetchone.return_value = expected

    result = repository.get_user_by_username("admin")

    assert result == expected
    cursor.execute.assert_called_once()


def test_update_user_password_executes_update(mock_connection):
    _conn, cursor = mock_connection

    repository.update_user_password(1, "new_hash")

    cursor.execute.assert_called_once()
    _conn.commit.assert_called_once()


def test_create_session_inserts_row(mock_connection):
    _conn, cursor = mock_connection
    expires = datetime.utcnow() + timedelta(hours=24)

    repository.create_session(
        session_token="token",
        user_id=1,
        expires_at=expires,
        csrf_token="csrf",
        ip_address="127.0.0.1",
        user_agent="Mozilla/5.0",
    )

    cursor.execute.assert_called_once()
    _conn.commit.assert_called_once()


def test_get_session_by_token_returns_joined_data(mock_connection):
    _conn, cursor = mock_connection
    expected = {
        "session_token": "token",
        "user_id": 1,
        "usuario": "admin",
        "is_admin": True,
    }
    cursor.fetchone.return_value = expected

    result = repository.get_session_by_token("token")

    assert result == expected


def test_delete_session_executes_delete(mock_connection):
    _conn, cursor = mock_connection

    repository.delete_session("token")

    cursor.execute.assert_called_once()
    _conn.commit.assert_called_once()
