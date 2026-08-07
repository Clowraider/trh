from unittest.mock import MagicMock, patch

import pytest

from trh.wordpress import repository


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
    with patch("trh.wordpress.repository.get_connection", return_value=conn):
        yield


def test_get_wordpress_config_by_user_executes_select(mock_connection):
    _conn, cursor = mock_connection
    expected = {
        "id": 1,
        "user_id": 42,
        "wp_url": "https://wp.test",
        "wp_username": "admin",
        "wp_app_password": "secret",
    }
    cursor.fetchone.return_value = expected

    result = repository.get_wordpress_config_by_user(42)

    assert result == expected
    cursor.execute.assert_called_once()
    _conn.close.assert_called_once()


def test_create_wordpress_config_inserts_and_returns_id(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchone.return_value = {"id": 5}

    config_id = repository.create_wordpress_config(
        user_id=42,
        wp_url="https://wp.test",
        wp_username="admin",
        wp_app_password="secret",
    )

    assert config_id == 5
    _conn.commit.assert_called_once()
    _conn.close.assert_called_once()


def test_update_wordpress_config_executes_update(mock_connection):
    _conn, cursor = mock_connection

    repository.update_wordpress_config(
        user_id=42,
        wp_url="https://wp.test",
        wp_username="admin",
        wp_app_password="new-secret",
    )

    cursor.execute.assert_called_once()
    _conn.commit.assert_called_once()
    _conn.close.assert_called_once()


def test_upsert_wordpress_config_creates_when_missing(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchone.return_value = None
    cursor.fetchone.side_effect = [None, {"id": 7}]

    repository.upsert_wordpress_config(
        user_id=42,
        wp_url="https://wp.test",
        wp_username="admin",
        wp_app_password="secret",
    )

    assert cursor.execute.call_count == 2
    _conn.commit.assert_called_once()


def test_upsert_wordpress_config_updates_when_exists(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchone.return_value = {"id": 7}

    repository.upsert_wordpress_config(
        user_id=42,
        wp_url="https://wp.test",
        wp_username="admin",
        wp_app_password="secret",
    )

    assert cursor.execute.call_count == 2
    _conn.commit.assert_called_once()
