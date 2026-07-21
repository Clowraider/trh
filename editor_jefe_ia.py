"""Read-only context assembly for the Editor Jefe IA recommendation flow."""

from pipeline.seleccionar_publicables import (
    calcular_score_editorial,
    obtener_keywords_por_cluster,
    obtener_prioridades,
    obtener_recientes_por_cluster,
)


_ELIGIBLE_CLUSTERS_SQL = """
SELECT
    ce.id AS cluster_id,
    ce.titulo_representativo,
    ce.cantidad_noticias,
    ce.cantidad_fuentes,
    ce.score AS technical_score,
    ce.tendencia,
    ce.primera_noticia,
    ce.ultima_noticia,
    ce.ultima_publicacion,
    MAX(COALESCE(n.fecha_publicacion, n.fecha_extraccion)) AS newest_at
FROM clusters_editoriales ce
JOIN noticias_historico n ON n.cluster_id = ce.id
WHERE COALESCE(ce.estado_publicacion, 'pendiente') = 'pendiente'
  AND COALESCE(n.fecha_publicacion, n.fecha_extraccion)
      >= NOW() - INTERVAL '3 days'
GROUP BY ce.id, ce.titulo_representativo, ce.cantidad_noticias,
         ce.cantidad_fuentes, ce.score, ce.tendencia,
         ce.primera_noticia, ce.ultima_noticia, ce.ultima_publicacion
ORDER BY newest_at DESC, ce.id DESC
"""

_RECENT_NEWS_SQL = """
WITH qualifying AS (
    SELECT
        n.id,
        n.cluster_id,
        n.titulo,
        n.fuente,
        n.texto_completo,
        COALESCE(n.fecha_publicacion, n.fecha_extraccion) AS effective_at
    FROM noticias_historico n
    WHERE n.cluster_id = ANY(%s)
      AND COALESCE(n.fecha_publicacion, n.fecha_extraccion)
          >= NOW() - INTERVAL '3 days'
), ranked AS (
    SELECT n.*, ROW_NUMBER() OVER (
        PARTITION BY n.cluster_id
        ORDER BY n.effective_at DESC, n.id DESC
    ) AS rn
    FROM qualifying n
)
SELECT id, cluster_id, titulo, fuente, texto_completo, effective_at
FROM ranked
WHERE rn <= 3
ORDER BY cluster_id, effective_at DESC, id DESC
"""


def _normalized_text(value, limit, fallback=""):
    normalized = " ".join(str(value).split()) if value is not None else ""
    return (normalized or fallback)[:limit]


def _normalized_keywords(values):
    bounded = {
        normalized[:120]
        for value in values
        if (normalized := _normalized_text(value, 120))
    }
    return sorted(bounded)[:8]


def _serialize_timestamp(value, label):
    if value is None:
        raise ValueError(f"Missing {label} timestamp")
    return value.isoformat()


def _load_eligible_clusters(conn):
    with conn.cursor() as cursor:
        cursor.execute(_ELIGIBLE_CLUSTERS_SQL)
        return cursor.fetchall()


def _load_recent_news(conn, cluster_ids):
    with conn.cursor() as cursor:
        cursor.execute(_RECENT_NEWS_SQL, (cluster_ids,))
        return cursor.fetchall()


def build_editorial_context(connection_factory, panel_keywords_loader):
    """Return deterministic, bounded candidate mappings using read-only queries."""
    conn = connection_factory()
    try:
        clusters = _load_eligible_clusters(conn)
        if not clusters:
            return []
        clusters.sort(
            key=lambda row: (row["newest_at"], row["cluster_id"]), reverse=True
        )

        recent_counts = obtener_recientes_por_cluster(conn)
        score_keywords = obtener_keywords_por_cluster(conn)
        priorities = obtener_prioridades(conn)
        cluster_ids = [row["cluster_id"] for row in clusters]
        panel_keywords = panel_keywords_loader(conn, cluster_ids)
        news_rows = _load_recent_news(conn, cluster_ids)

        news_by_cluster = {}
        for row in news_rows:
            items = news_by_cluster.setdefault(row["cluster_id"], [])
            if len(items) >= 3:
                continue
            items.append({
                "title": _normalized_text(row.get("titulo"), 300),
                "source": _normalized_text(row.get("fuente"), 100),
                "effective_at": _serialize_timestamp(
                    row.get("effective_at"), "news effective"
                ),
                "excerpt": _normalized_text(row.get("texto_completo"), 600),
            })

        candidates = []
        for row in clusters:
            cluster_id = row["cluster_id"]
            score_cluster = {"id": cluster_id, **row}
            score = calcular_score_editorial(
                score_cluster,
                recent_counts.get(cluster_id, {
                    "noticias_2h": 0,
                    "noticias_6h": 0,
                    "noticias_24h": 0,
                }),
                score_keywords.get(cluster_id, []),
                priorities,
            )
            candidates.append({
                "cluster_id": cluster_id,
                "title": _normalized_text(
                    row.get("titulo_representativo"), 300, "(Sin título)"
                ),
                "technical_score": (
                    0.0 if row.get("technical_score") is None
                    else row["technical_score"]
                ),
                "editorial_score": score["score_final"],
                "news_count": row["cantidad_noticias"],
                "source_count": row["cantidad_fuentes"],
                "newest_at": _serialize_timestamp(row.get("newest_at"), "cluster newest"),
                "keywords": _normalized_keywords(panel_keywords.get(cluster_id, [])),
                "recent_news": news_by_cluster.get(cluster_id, []),
            })

        return candidates
    finally:
        conn.close()
