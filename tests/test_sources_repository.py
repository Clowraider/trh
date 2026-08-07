from unittest.mock import MagicMock, patch

import pytest

from trh.sources import repository


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
    with patch("trh.sources.repository.get_connection", return_value=conn):
        yield


def _execute_calls(cursor):
    """Return a flat list of SQL/params sent to cursor.execute."""
    return [call.args for call in cursor.execute.call_args_list]


def test_sync_news_sources_inserts_new_sources(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchall.return_value = [
        {"fuente": "El Liberal"},
        {"fuente": "  Clarín  "},
    ]

    repository.sync_news_sources()

    calls = _execute_calls(cursor)
    assert any(
        "to_regclass" in call[0] for call in calls
    )
    assert any(
        "INSERT INTO news_sources" in call[0] and call[1] == ("el liberal", "El Liberal")
        for call in calls
    )
    assert any(
        "INSERT INTO news_sources" in call[0] and call[1] == ("clarín", "Clarín")
        for call in calls
    )
    _conn.commit.assert_called_once()
    _conn.close.assert_called_once()


def test_sync_news_sources_skips_empty_or_null_names(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchall.return_value = [
        {"fuente": ""},
        {"fuente": "   "},
        {"fuente": "La Nación"},
    ]

    repository.sync_news_sources()

    calls = _execute_calls(cursor)
    insert_calls = [call for call in calls if "INSERT INTO news_sources" in call[0]]
    assert len(insert_calls) == 1
    assert insert_calls[0][1] == ("la nación", "La Nación")


def test_sync_news_sources_no_op_when_table_missing(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchone.return_value = {"table_name": None}

    repository.sync_news_sources()

    calls = _execute_calls(cursor)
    assert any("to_regclass" in call[0] for call in calls)
    assert not any("SELECT DISTINCT fuente" in call[0] for call in calls)
    _conn.commit.assert_not_called()
    _conn.close.assert_called_once()


def test_list_active_sources_returns_ordered_rows(mock_connection):
    _conn, cursor = mock_connection
    expected = [
        {"id": 1, "slug": "el-liberal", "name": "El Liberal"},
        {"id": 2, "slug": "clarin", "name": "Clarín"},
    ]
    cursor.fetchall.return_value = expected

    result = repository.list_active_sources()

    assert result == expected
    cursor.execute.assert_called_once()
    _conn.close.assert_called_once()


def test_get_subscribed_source_ids_returns_set(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchall.return_value = [
        {"source_id": 3},
        {"source_id": 7},
    ]

    result = repository.get_subscribed_source_ids(42)

    assert result == {3, 7}
    cursor.execute.assert_called_once()
    _conn.close.assert_called_once()


def test_subscribe_user_to_sources_replaces_subscriptions(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchall.return_value = [
        {"id": 1},
        {"id": 2},
    ]

    repository.subscribe_user_to_sources(42, [1, 2])

    calls = _execute_calls(cursor)
    assert any("DELETE FROM user_source_subscriptions" in call[0] for call in calls)
    insert_calls = [
        call for call in calls if "INSERT INTO user_source_subscriptions" in call[0]
    ]
    assert len(insert_calls) == 2
    _conn.commit.assert_called_once()
    _conn.close.assert_called_once()


def test_subscribe_user_to_sources_deduplicates_source_ids(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchall.return_value = [{"id": 5}]

    repository.subscribe_user_to_sources(42, [5, "5", 5])

    insert_calls = [
        call
        for call in _execute_calls(cursor)
        if "INSERT INTO user_source_subscriptions" in call[0]
    ]
    assert len(insert_calls) == 1
    assert insert_calls[0][1] == (42, 5)


def test_subscribe_user_to_sources_accepts_empty_list(mock_connection):
    _conn, cursor = mock_connection

    repository.subscribe_user_to_sources(42, [])

    calls = _execute_calls(cursor)
    assert any("DELETE FROM user_source_subscriptions" in call[0] for call in calls)
    assert not any(
        "INSERT INTO user_source_subscriptions" in call[0] for call in calls
    )
    _conn.commit.assert_called_once()


def test_subscribe_user_to_sources_rejects_unknown_source_ids(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchall.return_value = [{"id": 1}]

    with pytest.raises(ValueError, match="IDs de fuente no existen"):
        repository.subscribe_user_to_sources(42, [1, 99])

    _conn.commit.assert_not_called()
    _conn.close.assert_called_once()
