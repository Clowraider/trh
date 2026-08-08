from trh.publication import publicador
import pytest
from psycopg2 import errors as psycopg2_errors


class RecordingCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.connection.executed.append((sql, params))

    def fetchone(self):
        results = self.connection.results[len(self.connection.executed) - 1]
        return results[0] if results else None


class FailingCursor(RecordingCursor):
    def execute(self, sql, params=None):
        raise psycopg2_errors.UndefinedColumn("missing column")


class RecordingConnection:
    def __init__(self):
        self.executed = []
        self.commit_count = 0
        self.closed = False

    def cursor(self):
        return RecordingCursor(self)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        raise AssertionError("rollback should not be used for removed schema compatibility")

    def close(self):
        self.closed = True


def test_generar_articulo_para_cluster_restores_pending_when_cluster_has_no_news(monkeypatch):
    initial_conn = RecordingConnection()
    restore_conn = RecordingConnection()
    connections = iter([initial_conn, restore_conn])

    monkeypatch.setattr(publicador, "get_connection", lambda: next(connections))
    monkeypatch.setattr(publicador, "obtener_noticias_cluster", lambda cluster_id: [])

    result = publicador.generar_articulo_para_cluster(17)

    assert result == {
        "ok": False,
        "mensaje": "El cluster no tiene noticias asociadas.",
    }
    assert initial_conn.commit_count == 1
    assert restore_conn.commit_count == 1
    assert "estado_publicacion = 'generando'" in initial_conn.executed[0][0]
    assert "estado_publicacion = 'pendiente'" in restore_conn.executed[0][0]
    assert restore_conn.executed[0][1] == (17,)
    assert initial_conn.closed
    assert restore_conn.closed


def test_generar_articulo_para_cluster_with_no_news_does_not_call_generation_steps(monkeypatch):
    initial_conn = RecordingConnection()
    restore_conn = RecordingConnection()
    connections = iter([initial_conn, restore_conn])

    monkeypatch.setattr(publicador, "get_connection", lambda: next(connections))
    monkeypatch.setattr(publicador, "obtener_noticias_cluster", lambda cluster_id: [])
    monkeypatch.setattr(
        publicador,
        "construir_prompt",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("prompt should not be built")),
    )
    monkeypatch.setattr(
        publicador,
        "llamar_ia",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("IA should not be called")),
    )
    monkeypatch.setattr(
        publicador,
        "guardar_contenido_ia",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("content should not be saved")),
    )

    result = publicador.generar_articulo_para_cluster(99, nota_ia="Sin contexto")

    assert result["mensaje"] == "El cluster no tiene noticias asociadas."
    assert len(initial_conn.executed) == 1
    assert len(restore_conn.executed) == 1


def test_set_requiere_revision_editorial_updates_current_schema(monkeypatch):
    conn = RecordingConnection()

    monkeypatch.setattr(publicador, "get_connection", lambda: conn)

    publicador.set_requiere_revision_editorial(23, True)

    assert conn.commit_count == 1
    assert conn.closed
    assert "SET requiere_revision_editorial = %s" in conn.executed[0][0]
    assert conn.executed[0][1] == (True, 23)


def test_set_requiere_revision_editorial_appends_note_when_provided(monkeypatch):
    conn = RecordingConnection()
    conn.results = [[{"nota_editor": "Nota previa"}]]

    monkeypatch.setattr(publicador, "get_connection", lambda: conn)

    publicador.set_requiere_revision_editorial(23, True, nota_editor="Nueva razón")

    assert conn.commit_count == 1
    assert conn.closed
    assert len(conn.executed) == 2  # SELECT + UPDATE
    assert "SELECT nota_editor" in conn.executed[0][0]
    assert "UPDATE clusters_editoriales" in conn.executed[1][0]
    params = conn.executed[1][1]
    assert params[0] is True
    assert "Nota previa" in params[1]
    assert "Nueva razón" in params[1]
    assert params[2] == 23


def test_set_requiere_revision_editorial_propagates_missing_schema_errors(monkeypatch):
    class FailingConnection(RecordingConnection):
        def cursor(self):
            return FailingCursor(self)

    conn = FailingConnection()
    monkeypatch.setattr(publicador, "get_connection", lambda: conn)

    with pytest.raises(psycopg2_errors.UndefinedColumn):
        publicador.set_requiere_revision_editorial(23, False)

    assert conn.closed


def test_generar_articulo_para_cluster_uses_user_news_filter_when_user_id_provided(monkeypatch):
    initial_conn = RecordingConnection()
    restore_conn = RecordingConnection()
    connections = iter([initial_conn, restore_conn])

    monkeypatch.setattr(publicador, "get_connection", lambda: next(connections))
    monkeypatch.setattr(publicador, "update_user_cluster_state", lambda *args, **kwargs: None)
    calls = []
    monkeypatch.setattr(
        publicador,
        "obtener_noticias_cluster_para_usuario",
        lambda cluster_id, user_id: calls.append((cluster_id, user_id)) or [],
    )

    result = publicador.generar_articulo_para_cluster(17, user_id=5)

    assert result == {
        "ok": False,
        "mensaje": "El cluster no tiene noticias asociadas.",
    }
    assert calls == [(17, 5)]


def test_guardar_contenido_ia_saves_to_user_cluster_states(monkeypatch):
    saved = []
    state_calls = []
    monkeypatch.setattr(
        publicador,
        "save_user_cluster_content",
        lambda *args, **kwargs: saved.append((args, kwargs)),
    )
    monkeypatch.setattr(
        publicador,
        "update_user_cluster_state",
        lambda *args, **kwargs: state_calls.append((args, kwargs)),
    )

    publicador.guardar_contenido_ia(
        7, {"titulo": "T", "resumen": "R", "articulo": "A", "categoria": "C"}, user_id=5
    )

    assert len(saved) == 1
    assert saved[0][0] == (5, 7)
    assert saved[0][1]["titulo_representativo"] == "T"
    assert saved[0][1]["contenido_ia"] == {
        "titulo": "T",
        "resumen": "R",
        "articulo": "A",
        "categoria": "C",
    }
    assert state_calls == [((5, 7), {"estado_publicacion": "generado"})]


def test_set_requiere_revision_editorial_appends_note_per_user(monkeypatch):
    monkeypatch.setattr(
        publicador,
        "get_or_create_user_cluster_state",
        lambda user_id, cluster_id: {"nota_editor": "Nota previa"},
    )
    updates = []
    monkeypatch.setattr(
        publicador,
        "update_user_cluster_state",
        lambda *args, **kwargs: updates.append((args, kwargs)),
    )

    publicador.set_requiere_revision_editorial(
        23, True, nota_editor="Nueva razón", user_id=5
    )

    assert len(updates) == 1
    args, kwargs = updates[0]
    assert args == (5, 23)
    assert kwargs["requiere_revision_editorial"] is True
    assert "Nota previa" in kwargs["nota_editor"]
    assert "Nueva razón" in kwargs["nota_editor"]
