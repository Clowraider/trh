from datetime import datetime, timezone
import sys
import types

import pytest

try:
    import psycopg2.extras  # noqa: F401
except ModuleNotFoundError:
    extras_stub = types.ModuleType("psycopg2.extras")
    extras_stub.RealDictCursor = type("RealDictCursor", (), {})
    sys.modules["psycopg2.extras"] = extras_stub

from editor_jefe_ia import build_editorial_context
from pipeline import seleccionar_publicables as scoring


class MappingRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            raise AssertionError("runtime rows must not be tuple-indexed")
        return super().__getitem__(key)


class QueryCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        statement = " ".join(sql.split())
        assert statement.upper().startswith(("SELECT", "WITH"))
        self.connection.queries.append((statement, params))

    def fetchall(self):
        return self.connection.results[len(self.connection.queries) - 1]


class ReadOnlyConnection:
    def __init__(self, *results):
        self.results = results
        self.queries = []
        self.closed = False

    def cursor(self, *args, **kwargs):
        assert not args and not kwargs, "must preserve the factory's RealDictCursor default"
        return QueryCursor(self)

    def commit(self):
        raise AssertionError("the context builder must never commit")

    def close(self):
        self.closed = True


@pytest.fixture
def score_inputs(monkeypatch):
    recent = {
        10: {"noticias_2h": 1, "noticias_6h": 2, "noticias_24h": 3},
        20: {"noticias_2h": 0, "noticias_6h": 1, "noticias_24h": 1},
    }
    score_keywords = {
        10: [{"tipo": "tema", "valor_normalizado": "economia"}],
        20: [],
    }
    priorities = [{"keyword": "economia", "tipo": "tema", "puntos": 7}]
    calls = []

    def loader(value):
        def load(conn):
            calls.append(conn)
            return value
        return load

    monkeypatch.setattr("editor_jefe_ia.obtener_recientes_por_cluster", loader(recent))
    monkeypatch.setattr("editor_jefe_ia.obtener_keywords_por_cluster", loader(score_keywords))
    monkeypatch.setattr("editor_jefe_ia.obtener_prioridades", loader(priorities))
    frozen = datetime(2026, 3, 7, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(scoring, "_ahora_utc", lambda: frozen)
    return recent, score_keywords, priorities, calls


def cluster(cluster_id, newest_at, **overrides):
    row = MappingRow(
        cluster_id=cluster_id,
        titulo_representativo=f"Cluster {cluster_id}",
        cantidad_noticias=4,
        cantidad_fuentes=2,
        technical_score=31.5,
        tendencia=1,
        primera_noticia=datetime(2026, 3, 7, 9, tzinfo=timezone.utc),
        ultima_noticia=datetime(2026, 3, 7, 11, tzinfo=timezone.utc),
        ultima_publicacion=None,
        newest_at=newest_at,
    )
    row.update(overrides)
    return row


def news(item_id, cluster_id, effective_at, **overrides):
    row = MappingRow(
        id=item_id,
        cluster_id=cluster_id,
        titulo=f"News {item_id}",
        fuente="Source",
        texto_completo="Body",
        effective_at=effective_at,
    )
    row.update(overrides)
    return row


def test_eligibility_score_connection_and_ranked_news_are_read_only(score_inputs):
    recent, score_keywords, priorities, loader_connections = score_inputs
    t_new = datetime(2026, 3, 7, 11, tzinfo=timezone.utc)
    t_old = datetime(2026, 3, 7, 10, tzinfo=timezone.utc)
    eligible = [cluster(10, t_old), cluster(20, t_new)]
    ranked_news = [
        news(4, 10, t_new), news(3, 10, t_old),
        news(2, 10, datetime(2026, 3, 7, 9, tzinfo=timezone.utc)),
        news(1, 10, datetime(2026, 3, 7, 8, tzinfo=timezone.utc)),
        news(5, 20, t_new),
    ]
    conn = ReadOnlyConnection(eligible, ranked_news)
    factory_calls = []

    def factory():
        factory_calls.append(True)
        return conn

    keywords = {10: ["economia"], 20: ["mundo"]}
    result = build_editorial_context(factory, lambda used_conn, ids: keywords)

    assert factory_calls == [True]
    assert loader_connections == [conn, conn, conn]
    assert conn.closed
    assert [item["cluster_id"] for item in result] == [20, 10]
    assert result[0]["keywords"] == ["mundo"]
    assert result[1]["keywords"] == ["economia"]
    expected = scoring.calcular_score_editorial(
        {"id": 10, **eligible[0]}, recent[10], score_keywords[10], priorities
    )["score_final"]
    assert result[1]["editorial_score"] == expected
    assert [item["title"] for item in result[1]["recent_news"]] == ["News 4", "News 3", "News 2"]

    eligibility_sql, eligibility_params = conn.queries[0]
    assert "COALESCE(ce.estado_publicacion, 'pendiente') = 'pendiente'" in eligibility_sql
    assert "COALESCE(n.fecha_publicacion, n.fecha_extraccion)" in eligibility_sql
    assert "NOW() - INTERVAL '3 days'" in eligibility_sql
    assert "ORDER BY newest_at DESC, ce.id DESC" in eligibility_sql
    assert "LIMIT" not in eligibility_sql.upper()
    assert eligibility_params is None

    news_sql, news_params = conn.queries[1]
    assert "n.cluster_id = ANY(%s)" in news_sql
    assert "PARTITION BY n.cluster_id" in news_sql
    assert "effective_at DESC, n.id DESC" in news_sql
    assert "rn <= 3" in news_sql
    assert "ORDER BY cluster_id, effective_at DESC, id DESC" in news_sql
    assert news_params == ([20, 10],)
    assert len(conn.queries) == 2


def test_context_normalizes_and_bounds_cluster_keywords_and_news(score_inputs):
    t = datetime(2026, 3, 7, 11, 30, tzinfo=timezone.utc)
    eligible = [cluster(
        10, t, titulo_representativo="  A\n" + "é" * 400,
        technical_score=None,
    )]
    ranked_news = [news(
        1, 10, t, titulo=None, fuente="  S\n" + "x" * 150,
        texto_completo="  α\n\t" + "β" * 700,
    )]
    conn = ReadOnlyConnection(eligible, ranked_news)
    raw_keywords = [" z ", "", "a", "a ", "b" * 130, "y", "x", "w", "v", "u"]

    result = build_editorial_context(lambda: conn, lambda _conn, _ids: {10: raw_keywords})
    candidate = result[0]

    assert candidate["title"] == ("A " + "é" * 400)[:300]
    assert candidate["technical_score"] == 0.0
    assert candidate["keywords"] == sorted({k.strip()[:120] for k in raw_keywords if k.strip()})[:8]
    item = candidate["recent_news"][0]
    assert item["title"] == ""
    assert item["source"] == ("S " + "x" * 150)[:100]
    assert item["excerpt"] == ("α " + "β" * 700)[:600]
    assert item["effective_at"] == t.isoformat()


def test_null_cluster_title_falls_back_and_invalid_timestamp_fails_closed(score_inputs):
    valid_time = datetime(2026, 3, 7, 11, tzinfo=timezone.utc)
    conn = ReadOnlyConnection(
        [cluster(10, valid_time, titulo_representativo=None)],
        [news(1, 10, None, texto_completo=None)],
    )

    with pytest.raises(ValueError, match="effective timestamp"):
        build_editorial_context(lambda: conn, lambda _conn, _ids: {10: []})
    assert conn.closed

    clean_conn = ReadOnlyConnection(
        [cluster(10, valid_time, titulo_representativo=None)],
        [news(1, 10, valid_time, texto_completo=None)],
    )
    candidate = build_editorial_context(lambda: clean_conn, lambda _conn, _ids: {10: []})[0]
    assert candidate["title"] == "(Sin título)"
    assert candidate["recent_news"][0]["excerpt"] == ""
