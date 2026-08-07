from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from trh.clusters import repository


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
    with patch("trh.clusters.repository.get_connection", return_value=conn):
        yield


@pytest.fixture
def patch_fotos_manuales():
    with patch("trh.clusters.repository._fotos_manuales", return_value=[]):
        yield


def _execute_calls(cursor):
    """Return a flat list of SQL/params sent to cursor.execute."""
    return [call.args for call in cursor.execute.call_args_list]


def _state_row(**overrides):
    defaults = {
        "user_id": 2,
        "cluster_id": 7,
        "estado_publicacion": "pendiente",
        "requiere_revision_editorial": False,
        "url_wp": None,
        "veces_publicado": 0,
        "ultima_publicacion": None,
        "descartado_en": None,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }
    defaults.update(overrides)
    return defaults


def test_get_or_create_returns_existing_state(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchone.return_value = _state_row(
        estado_publicacion="generado", veces_publicado=1
    )

    result = repository.get_or_create_user_cluster_state(2, 7)

    assert result["estado_publicacion"] == "generado"
    assert result["veces_publicado"] == 1
    calls = _execute_calls(cursor)
    assert any(
        "SELECT" in call[0] and "user_cluster_states" in call[0] for call in calls
    )
    assert not any("INSERT INTO user_cluster_states" in call[0] for call in calls)
    _conn.close.assert_called_once()


def test_get_or_create_inserts_defaults_when_missing(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchone.side_effect = [None, _state_row()]

    result = repository.get_or_create_user_cluster_state(2, 7)

    assert result["estado_publicacion"] == "pendiente"
    assert result["veces_publicado"] == 0
    calls = _execute_calls(cursor)
    assert any("INSERT INTO user_cluster_states" in call[0] for call in calls)
    _conn.commit.assert_called_once()
    _conn.close.assert_called_once()


def test_update_user_cluster_state_inserts_row_when_missing(mock_connection):
    _conn, cursor = mock_connection

    repository.update_user_cluster_state(
        2,
        7,
        estado_publicacion="publicado",
        url_wp="https://wp.test/7",
        veces_publicado=1,
    )

    calls = _execute_calls(cursor)
    update_call = next(
        call for call in calls if "INSERT INTO user_cluster_states" in call[0]
    )
    sql = update_call[0]
    params = update_call[1]
    assert "estado_publicacion = %s" in sql
    assert "url_wp = %s" in sql
    assert "veces_publicado = %s" in sql
    assert params[:2] == (2, 7)
    assert "publicado" in params
    assert "https://wp.test/7" in params
    _conn.commit.assert_called_once()
    _conn.close.assert_called_once()


def test_update_user_cluster_state_ignores_unknown_fields(mock_connection):
    _conn, cursor = mock_connection

    repository.update_user_cluster_state(
        2,
        7,
        estado_publicacion="descartado",
        descartado_en=datetime(2026, 1, 2),
        unknown_field="ignored",
    )

    calls = _execute_calls(cursor)
    update_call = next(
        call for call in calls if "INSERT INTO user_cluster_states" in call[0]
    )
    assert "unknown_field" not in update_call[0]
    assert "descartado_en = %s" in update_call[0]


def test_update_user_cluster_state_noop_for_empty_fields(mock_connection):
    _conn, cursor = mock_connection

    repository.update_user_cluster_state(2, 7)

    _conn.commit.assert_not_called()
    _conn.close.assert_not_called()


def test_list_clusters_for_user_returns_empty_when_no_subscriptions(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchall.return_value = []

    result = repository.list_clusters_for_user(2)

    assert result == []
    calls = _execute_calls(cursor)
    assert any(
        "FROM user_source_subscriptions" in call[0] for call in calls
    )


def test_list_clusters_for_user_filters_by_subscribed_sources(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchall.side_effect = [
        [{"slug": "el-liberal"}, {"slug": "clarin"}],
        [
            {
                "id": 1,
                "titulo_representativo": "A",
                "cantidad_noticias": 2,
                "cantidad_fuentes": 1,
                "score": 10,
                "tendencia": 0,
                "estado_publicacion": "generado",
                "requiere_revision_editorial": False,
                "url_wp": None,
                "veces_publicado": 0,
                "ultima_publicacion": None,
                "descartado_en": None,
            }
        ],
    ]

    result = repository.list_clusters_for_user(2)

    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["estado_publicacion"] == "generado"
    calls = _execute_calls(cursor)
    list_call = calls[-1]
    assert "LOWER(n.fuente) = ANY(%s)" in list_call[0]
    assert list_call[1][1] == ["el-liberal", "clarin"]


def test_list_clusters_for_user_excludes_descartado(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchall.side_effect = [
        [{"slug": "el-liberal"}],
        [],
    ]

    result = repository.list_clusters_for_user(2)

    assert result == []
    calls = _execute_calls(cursor)
    list_call = calls[-1]
    assert "IS DISTINCT FROM 'descartado'" in list_call[0]


def test_list_clusters_for_user_defaults_to_pendiente_when_no_state(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchall.side_effect = [
        [{"slug": "el-liberal"}],
        [
            {
                "id": 1,
                "titulo_representativo": "A",
                "cantidad_noticias": 1,
                "cantidad_fuentes": 1,
                "score": 1,
                "tendencia": 0,
                "estado_publicacion": None,
                "requiere_revision_editorial": None,
                "url_wp": None,
                "veces_publicado": None,
                "ultima_publicacion": None,
                "descartado_en": None,
            }
        ],
    ]

    result = repository.list_clusters_for_user(2)

    assert result[0]["estado_publicacion"] == "pendiente"
    assert result[0]["requiere_revision_editorial"] is False
    assert result[0]["veces_publicado"] == 0


def test_get_user_cluster_by_id_returns_none_when_not_subscribed(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchall.return_value = []

    result = repository.get_user_cluster_by_id(2, 7)

    assert result is None


def test_get_user_cluster_by_id_returns_none_when_cluster_not_visible(mock_connection):
    _conn, cursor = mock_connection
    cursor.fetchall.return_value = [{"slug": "el-liberal"}]
    cursor.fetchone.return_value = None

    result = repository.get_user_cluster_by_id(2, 7)

    assert result is None


def test_get_user_cluster_by_id_returns_cluster_with_state(
    mock_connection, patch_fotos_manuales
):
    _conn, cursor = mock_connection
    cursor.fetchall.return_value = [{"slug": "el-liberal"}]
    cursor.fetchone.return_value = {
        "id": 7,
        "titulo_representativo": "Cluster visible",
        "contenido_ia": None,
        "estado": "nuevo",
        "foto_principal": None,
        "fotos_secundarias": None,
        "nota_editor": None,
        "nota_ia": None,
        "cantidad_noticias": 2,
        "cantidad_fuentes": 1,
        "primera_noticia": None,
        "ultima_noticia": None,
        "score": 5,
        "tendencia": 0,
        "actualizado_en": datetime(2026, 1, 1),
        "estado_publicacion": "publicado",
        "requiere_revision_editorial": False,
        "url_wp": "https://wp.test/7",
        "veces_publicado": 3,
        "ultima_publicacion": datetime(2026, 1, 2),
        "descartado_en": None,
    }

    result = repository.get_user_cluster_by_id(2, 7)

    assert result["id"] == 7
    assert result["estado_publicacion"] == "publicado"
    assert result["url_wp"] == "https://wp.test/7"
    assert result["veces_publicado"] == 3
    assert result["fotos_secundarias"] == []
