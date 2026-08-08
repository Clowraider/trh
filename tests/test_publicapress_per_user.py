import json
import pytest
from trh.publication import publicapress


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


class RecordingConnection:
    def __init__(self, results=None):
        self.executed = []
        self.results = results or []
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def cursor(self):
        return RecordingCursor(self)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    """Neutralize external dependencies for every test in this module."""
    monkeypatch.setattr(publicapress, "_config_or_raise", lambda user_id: {"site": "test"})
    monkeypatch.setattr(publicapress, "obtener_o_crear_categoria", lambda name, config: 7)
    monkeypatch.setattr(
        publicapress, "subir_imagen_a_wordpress", lambda url, config: (True, 42, url)
    )
    monkeypatch.setattr(
        publicapress, "publicar_en_wordpress",
        lambda titulo, resumen, articulo, config, cat_id, media_id: (True, "https://wp.test/post/1"),
    )
    monkeypatch.setattr(publicapress, "_limpiar_fotos_temporales_cluster", lambda cluster_id: None)
    monkeypatch.setattr(publicapress, "_validar_contenido_publicable", lambda contenido: None)


@pytest.fixture
def fake_user_state(monkeypatch):
    states = {}

    def _get_or_create(user_id, cluster_id):
        return states.setdefault(
            (user_id, cluster_id),
            {
                "user_id": user_id,
                "cluster_id": cluster_id,
                "contenido_ia": None,
                "titulo_representativo": None,
                "foto_principal": None,
                "fotos_secundarias": None,
                "estado_publicacion": "pendiente",
                "url_wp": None,
                "veces_publicado": 0,
                "nota_editor": "",
            },
        )

    def _update(user_id, cluster_id, **kwargs):
        state = _get_or_create(user_id, cluster_id)
        state.update(kwargs)

    monkeypatch.setattr(publicapress, "get_or_create_user_cluster_state", _get_or_create)
    monkeypatch.setattr(publicapress, "update_user_cluster_state", _update)
    return states


def _make_cluster_global(contenido_ia=None, foto_principal=None, fotos_secundarias=None):
    return {
        "id": 1,
        "titulo_representativo": "Global title",
        "contenido_ia": contenido_ia,
        "estado_publicacion": "pendiente",
        "foto_principal": foto_principal,
        "fotos_secundarias": fotos_secundarias,
    }


def test_publicar_cluster_uses_user_state_when_user_id_given(fake_user_state, monkeypatch):
    conn = RecordingConnection(results=[[_make_cluster_global()]])
    monkeypatch.setattr(publicapress, "get_connection", lambda: conn)

    fake_user_state[(5, 1)] = {
        "user_id": 5,
        "cluster_id": 1,
        "contenido_ia": json.dumps(
            {
                "titulo": "User title",
                "resumen": "User summary",
                "articulo": "<p>User article</p>",
                "categoria": "User category",
            }
        ),
        "titulo_representativo": None,
        "foto_principal": "https://user.test/photo.jpg",
        "fotos_secundarias": ["https://user.test/photo2.jpg"],
        "estado_publicacion": "pendiente",
        "url_wp": None,
        "veces_publicado": 0,
        "nota_editor": "",
    }

    result = publicapress.publicar_cluster(1, user_id=5)

    assert result == {"ok": True, "url_wp": "https://wp.test/post/1"}
    state = fake_user_state[(5, 1)]
    assert state["estado_publicacion"] == "publicado"
    assert state["url_wp"] == "https://wp.test/post/1"
    assert state["veces_publicado"] == 1


def test_publicar_cluster_uses_global_cluster_when_no_user_id(monkeypatch):
    conn = RecordingConnection(results=[[
        _make_cluster_global(
            contenido_ia=json.dumps(
                {
                    "titulo": "Global title",
                    "resumen": "Global summary",
                    "articulo": "<p>Global article</p>",
                    "categoria": "Global category",
                }
            ),
            foto_principal="https://global.test/photo.jpg",
            fotos_secundarias='["https://global.test/photo2.jpg"]',
        )
    ]])
    monkeypatch.setattr(publicapress, "get_connection", lambda: conn)

    result = publicapress.publicar_cluster(1, user_id=None)

    assert result == {"ok": True, "url_wp": "https://wp.test/post/1"}
    assert conn.commit_count == 1
    update_sql = next(sql for sql, _ in conn.executed if "UPDATE clusters_editoriales" in sql)
    assert "estado_publicacion = 'publicado'" in update_sql
    assert "veces_publicado = veces_publicado + 1" in update_sql


def test_publicar_cluster_blocks_when_user_already_published(fake_user_state, monkeypatch):
    conn = RecordingConnection(results=[[_make_cluster_global()]])
    monkeypatch.setattr(publicapress, "get_connection", lambda: conn)
    fake_user_state[(5, 1)] = {
        "user_id": 5,
        "cluster_id": 1,
        "estado_publicacion": "publicado",
        "contenido_ia": json.dumps(
            {"titulo": "T", "resumen": "R", "articulo": "<p>A</p>", "categoria": "C"}
        ),
        "titulo_representativo": None,
        "foto_principal": None,
        "fotos_secundarias": None,
        "url_wp": "https://wp.test/post/old",
        "veces_publicado": 1,
        "nota_editor": "",
    }

    result = publicapress.publicar_cluster(1, user_id=5)

    assert result == {"ok": False, "mensaje": "Este cluster ya fue publicado."}


def test_load_publishable_content_returns_user_data(monkeypatch, fake_user_state):
    conn = RecordingConnection(results=[[_make_cluster_global(
        contenido_ia=json.dumps({"titulo": "Global"}),
        foto_principal="https://global.test/photo.jpg",
        fotos_secundarias='["https://global.test/photo2.jpg"]',
    )]])
    monkeypatch.setattr(publicapress, "get_connection", lambda: conn)
    fake_user_state[(5, 1)] = {
        "user_id": 5,
        "cluster_id": 1,
        "contenido_ia": json.dumps({"titulo": "User"}),
        "titulo_representativo": None,
        "foto_principal": "https://user.test/photo.jpg",
        "fotos_secundarias": ["https://user.test/photo2.jpg", "https://user.test/photo3.jpg"],
        "estado_publicacion": "pendiente",
        "url_wp": None,
        "veces_publicado": 0,
        "nota_editor": "",
    }

    content = publicapress._load_publishable_content(1, user_id=5)

    assert json.loads(content["contenido_ia"])["titulo"] == "User"
    assert content["foto_principal"] == "https://user.test/photo.jpg"
    assert content["fotos_secundarias"] == [
        "https://user.test/photo2.jpg",
        "https://user.test/photo3.jpg",
    ]


def test_guardar_error_publicacion_appends_to_user_state(fake_user_state, monkeypatch):
    conn = RecordingConnection()
    monkeypatch.setattr(publicapress, "get_connection", lambda: conn)
    fake_user_state[(5, 1)] = {
        "user_id": 5,
        "cluster_id": 1,
        "nota_editor": "previous note",
        "contenido_ia": None,
        "titulo_representativo": None,
        "foto_principal": None,
        "fotos_secundarias": None,
        "estado_publicacion": "pendiente",
        "url_wp": None,
        "veces_publicado": 0,
    }

    publicapress._guardar_error_publicacion(conn, 1, "something failed", user_id=5)

    assert "something failed" in fake_user_state[(5, 1)]["nota_editor"]
    assert "previous note" in fake_user_state[(5, 1)]["nota_editor"]


def test_publicar_cluster_saves_error_to_user_state_on_publish_failure(fake_user_state, monkeypatch):
    conn = RecordingConnection(results=[[_make_cluster_global()]])
    monkeypatch.setattr(publicapress, "get_connection", lambda: conn)
    monkeypatch.setattr(
        publicapress, "publicar_en_wordpress",
        lambda *args, **kwargs: (False, None),
    )
    fake_user_state[(5, 1)] = {
        "user_id": 5,
        "cluster_id": 1,
        "contenido_ia": json.dumps(
            {"titulo": "T", "resumen": "R", "articulo": "<p>A</p>", "categoria": "C"}
        ),
        "titulo_representativo": None,
        "foto_principal": None,
        "fotos_secundarias": None,
        "estado_publicacion": "pendiente",
        "url_wp": None,
        "veces_publicado": 0,
        "nota_editor": "",
    }

    result = publicapress.publicar_cluster(1, user_id=5)

    assert result == {"ok": False, "mensaje": "Falló la publicación en WordPress. Revisar logs."}
    assert "Error publicación WP" in fake_user_state[(5, 1)]["nota_editor"]
