"""Repository for per-user cluster visibility and publication state.

Clusters themselves remain global (``clusters_editoriales``).  This module
handles ``user_cluster_states``: which clusters each user can see based on
their subscribed sources, and the per-user publication lifecycle.
"""

import json
from typing import Any

from pipeline.seleccionar_publicables import get_connection


DEFAULT_STATE = {
    "estado_publicacion": "pendiente",
    "requiere_revision_editorial": False,
    "url_wp": None,
    "veces_publicado": 0,
    "ultima_publicacion": None,
    "descartado_en": None,
}


def _connection():
    return get_connection()


def _normalizar_fotos_secundarias(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _fotos_manuales(cluster_id):
    """Return URLs for manually uploaded temporary photos for a cluster."""
    import os
    from pathlib import Path

    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    path = PROJECT_ROOT / "static" / "uploads" / "tmp" / f"cluster_{cluster_id}"
    if not path.is_dir():
        return []

    allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    fotos = []
    for name in sorted(path.iterdir()):
        if name.suffix.lower() not in allowed:
            continue
        fotos.append(f"/static/uploads/tmp/cluster_{cluster_id}/{name.name}")
    return fotos


def _get_subscribed_source_slugs(cur, user_id: int) -> list[str]:
    cur.execute(
        """
        SELECT ns.slug
        FROM user_source_subscriptions uss
        JOIN news_sources ns ON ns.id = uss.source_id
        WHERE uss.user_id = %s
        """,
        (user_id,),
    )
    return [row["slug"] for row in cur.fetchall()]


def _merge_state(cluster: dict[str, Any]) -> dict[str, Any]:
    """Normalize per-user state fields on a cluster row."""
    row = dict(cluster)
    row["estado_publicacion"] = (row.get("estado_publicacion") or "pendiente").strip() or "pendiente"
    row["requiere_revision_editorial"] = bool(row.get("requiere_revision_editorial"))
    row["veces_publicado"] = int(row.get("veces_publicado") or 0)
    row["fotos_secundarias"] = _normalizar_fotos_secundarias(row.get("fotos_secundarias"))
    return row


def get_or_create_user_cluster_state(user_id: int, cluster_id: int) -> dict[str, Any]:
    """Return the existing per-user state row or create one with defaults."""
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, cluster_id, estado_publicacion,
                       requiere_revision_editorial, url_wp, veces_publicado,
                       ultima_publicacion, descartado_en, created_at, updated_at
                FROM user_cluster_states
                WHERE user_id = %s AND cluster_id = %s
                """,
                (user_id, cluster_id),
            )
            row = cur.fetchone()
            if row:
                return dict(row)

            cur.execute(
                """
                INSERT INTO user_cluster_states (user_id, cluster_id)
                VALUES (%s, %s)
                RETURNING user_id, cluster_id, estado_publicacion,
                          requiere_revision_editorial, url_wp, veces_publicado,
                          ultima_publicacion, descartado_en, created_at, updated_at
                """,
                (user_id, cluster_id),
            )
            conn.commit()
            return dict(cur.fetchone())
    finally:
        conn.close()


def update_user_cluster_state(user_id: int, cluster_id: int, **fields) -> None:
    """Update per-user cluster state fields.

    Allowed fields: ``estado_publicacion``, ``url_wp``, ``veces_publicado``,
    ``ultima_publicacion``, ``descartado_en``, ``requiere_revision_editorial``.
    Unknown fields are ignored.
    """
    allowed = {
        "estado_publicacion",
        "url_wp",
        "veces_publicado",
        "ultima_publicacion",
        "descartado_en",
        "requiere_revision_editorial",
    }
    to_update = {k: v for k, v in fields.items() if k in allowed}
    if not to_update:
        return

    columns = list(to_update.keys()) + ["updated_at"]
    values = list(to_update.values()) + ["NOW()"]
    set_clause = ", ".join(
        f"{col} = %s" if col != "updated_at" else "updated_at = NOW()"
        for col in columns
    )

    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO user_cluster_states (user_id, cluster_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, cluster_id) DO UPDATE SET
                    {set_clause}
                """,
                (user_id, cluster_id, *to_update.values()),
            )
        conn.commit()
    finally:
        conn.close()


def list_clusters_for_user(user_id: int) -> list[dict[str, Any]]:
    """Return clusters visible to the user joined with their per-user state.

    A cluster is visible when at least one of its news items in
    ``noticias_historico`` has ``fuente`` matching a subscribed source.
    """
    conn = _connection()
    try:
        with conn.cursor() as cur:
            subscribed_slugs = _get_subscribed_source_slugs(cur, user_id)
            if not subscribed_slugs:
                return []

            cur.execute(
                """
                SELECT
                    ce.id,
                    ce.titulo_representativo,
                    ce.cantidad_noticias,
                    ce.cantidad_fuentes,
                    ce.score,
                    ce.tendencia,
                    ce.primera_noticia,
                    ce.ultima_noticia,
                    ce.contenido_ia,
                    ce.foto_principal,
                    ce.fotos_secundarias,
                    COALESCE(ucs.estado_publicacion, 'pendiente') AS estado_publicacion,
                    COALESCE(ucs.requiere_revision_editorial, FALSE) AS requiere_revision_editorial,
                    ucs.url_wp,
                    COALESCE(ucs.veces_publicado, 0) AS veces_publicado,
                    ucs.ultima_publicacion,
                    ucs.descartado_en
                FROM clusters_editoriales ce
                JOIN noticias_historico n ON n.cluster_id = ce.id
                LEFT JOIN user_cluster_states ucs
                    ON ucs.cluster_id = ce.id AND ucs.user_id = %s
                WHERE LOWER(n.fuente) = ANY(%s)
                  AND COALESCE(n.fecha_publicacion, n.fecha_extraccion)
                      >= NOW() - INTERVAL '7 days'
                  AND COALESCE(ucs.estado_publicacion, 'pendiente') IS DISTINCT FROM 'descartado'
                GROUP BY ce.id, ce.titulo_representativo, ce.cantidad_noticias,
                         ce.cantidad_fuentes, ce.score, ce.tendencia,
                         ce.primera_noticia, ce.ultima_noticia,
                         ce.contenido_ia, ce.foto_principal, ce.fotos_secundarias,
                         ucs.estado_publicacion, ucs.requiere_revision_editorial,
                         ucs.url_wp, ucs.veces_publicado, ucs.ultima_publicacion,
                         ucs.descartado_en
                ORDER BY
                    CASE COALESCE(ucs.estado_publicacion, 'pendiente')
                        WHEN 'generado' THEN 1
                        WHEN 'generando' THEN 2
                        WHEN 'pendiente' THEN 3
                        WHEN 'publicado' THEN 4
                        WHEN 'descartado' THEN 5
                        ELSE 6
                    END,
                    ce.score DESC
                LIMIT 200
                """,
                (user_id, subscribed_slugs),
            )
            return [_merge_state(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_user_cluster_by_id(user_id: int, cluster_id: int) -> dict[str, Any] | None:
    """Return a single cluster with per-user state, or None if not visible."""
    conn = _connection()
    try:
        with conn.cursor() as cur:
            subscribed_slugs = _get_subscribed_source_slugs(cur, user_id)
            if not subscribed_slugs:
                return None

            cur.execute(
                """
                SELECT
                    ce.id,
                    ce.titulo_representativo,
                    ce.contenido_ia,
                    ce.estado,
                    ce.foto_principal,
                    ce.fotos_secundarias,
                    ce.nota_editor,
                    ce.nota_ia,
                    ce.cantidad_noticias,
                    ce.cantidad_fuentes,
                    ce.primera_noticia,
                    ce.ultima_noticia,
                    ce.score,
                    ce.tendencia,
                    ce.actualizado_en,
                    COALESCE(ucs.estado_publicacion, 'pendiente') AS estado_publicacion,
                    COALESCE(ucs.requiere_revision_editorial, FALSE) AS requiere_revision_editorial,
                    ucs.url_wp,
                    COALESCE(ucs.veces_publicado, 0) AS veces_publicado,
                    ucs.ultima_publicacion,
                    ucs.descartado_en
                FROM clusters_editoriales ce
                LEFT JOIN user_cluster_states ucs
                    ON ucs.cluster_id = ce.id AND ucs.user_id = %s
                WHERE ce.id = %s
                  AND EXISTS (
                      SELECT 1
                      FROM noticias_historico n
                      JOIN news_sources ns ON LOWER(n.fuente) = ns.slug
                      JOIN user_source_subscriptions uss
                          ON uss.source_id = ns.id AND uss.user_id = %s
                      WHERE n.cluster_id = ce.id
                  )
                """,
                (user_id, cluster_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                return None

            cluster = _merge_state(row)
            cluster["fotos_manuales"] = _fotos_manuales(cluster_id)
            return cluster
    finally:
        conn.close()
