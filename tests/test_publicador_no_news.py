import publicador


class RecordingCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.connection.executed.append((sql, params))


class RecordingConnection:
    def __init__(self):
        self.executed = []
        self.commit_count = 0
        self.closed = False

    def cursor(self):
        return RecordingCursor(self)

    def commit(self):
        self.commit_count += 1

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
