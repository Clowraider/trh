import editor_jefe_ia as feature


class RecordingCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.connection.executed.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self.connection.rows


class RecordingConnection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed = []
        self.commit_count = 0
        self.closed = False

    def cursor(self, *args, **kwargs):
        assert not args and not kwargs
        return RecordingCursor(self)

    def commit(self):
        self.commit_count += 1

    def close(self):
        self.closed = True


def test_load_saved_recommendations_ensures_storage_and_returns_rows():
    rows = [{
        "cluster_id": 7,
        "title": "Saved",
        "reason": "Reason",
        "estado_publicacion": "generado",
    }]
    conn = RecordingConnection(rows=rows)

    result = feature.load_saved_recommendations(lambda: conn)

    assert result == rows
    assert conn.closed
    assert conn.commit_count == 1
    assert "CREATE TABLE IF NOT EXISTS editor_jefe_ia_recommendations" in conn.executed[0][0]
    assert "CREATE INDEX IF NOT EXISTS idx_editor_jefe_ia_recommendations_recommended_at" in conn.executed[1][0]
    assert "SELECT r.cluster_id, r.title, r.reason, r.editorial_score" in conn.executed[2][0]
    assert "LEFT JOIN clusters_editoriales ce ON ce.id = r.cluster_id" in conn.executed[2][0]
    assert "COALESCE(ce.estado_publicacion, 'pendiente') AS estado_publicacion" in conn.executed[2][0]


def test_save_recommendations_ensures_storage_and_inserts_each_selection():
    conn = RecordingConnection()
    selections = [
        {
            "cluster_id": 7,
            "title": "Uno",
            "reason": "Motivo uno",
            "editorial_score": 80,
            "technical_score": 20,
            "news_count": 3,
            "source_count": 2,
            "newest_at": "2026-03-06T12:00:00+00:00",
        },
        {
            "cluster_id": 8,
            "title": "Dos",
            "reason": "Motivo dos",
            "editorial_score": 70,
            "technical_score": 10,
            "news_count": 4,
            "source_count": 3,
            "newest_at": "2026-03-07T12:00:00+00:00",
        },
    ]

    feature.save_recommendations(lambda: conn, selections)

    assert conn.closed
    assert conn.commit_count == 2
    assert "CREATE TABLE IF NOT EXISTS editor_jefe_ia_recommendations" in conn.executed[0][0]
    assert "CREATE INDEX IF NOT EXISTS idx_editor_jefe_ia_recommendations_recommended_at" in conn.executed[1][0]
    insert_statements = [sql for sql, _ in conn.executed if sql.startswith("INSERT INTO editor_jefe_ia_recommendations")]
    assert len(insert_statements) == 2
    assert conn.executed[2][1][0] == 7
    assert conn.executed[3][1][0] == 8


def test_save_recommendations_skips_empty_input_without_connection():
    called = []

    feature.save_recommendations(lambda: called.append(True), [])

    assert called == []


def test_delete_saved_recommendation_ensures_storage_and_deletes_target_cluster():
    conn = RecordingConnection()

    feature.delete_saved_recommendation(lambda: conn, 7)

    assert conn.closed
    assert conn.commit_count == 2
    assert "CREATE TABLE IF NOT EXISTS editor_jefe_ia_recommendations" in conn.executed[0][0]
    assert "CREATE INDEX IF NOT EXISTS idx_editor_jefe_ia_recommendations_recommended_at" in conn.executed[1][0]
    assert conn.executed[2] == (
        "DELETE FROM editor_jefe_ia_recommendations WHERE cluster_id = %s",
        (7,),
    )
