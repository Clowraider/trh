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
    "titulo_representativo": None,
    "contenido_ia": None,
    "foto_principal": None,
    "fotos_secundarias": [],
    "nota_editor": None,
    "nota_ia": None,
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


def _normalizar_contenido_ia(raw):
    """Return a dict/list for JSONB fields, or the original value."""
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
    return raw


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
    row["contenido_ia"] = _normalizar_contenido_ia(row.get("contenido_ia"))
    row["titulo_representativo"] = row.get("titulo_representativo") or None
    row["nota_editor"] = row.get("nota_editor") or None
    row["nota_ia"] = row.get("nota_ia") or None
    return row


def get_or_create_user_cluster_state(user_id: int, cluster_id: int) -> dict[str, Any]:
    """Return the existing per-user state row or create one with defaults."""
    conn = _connection()
    columns = """
        user_id, cluster_id, estado_publicacion,
        requiere_revision_editorial, url_wp, veces_publicado,
        ultima_publicacion, descartado_en, created_at, updated_at,
        titulo_representativo, contenido_ia, foto_principal,
        fotos_secundarias, nota_editor, nota_ia
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {columns}
                FROM user_cluster_states
                WHERE user_id = %s AND cluster_id = %s
                """,
                (user_id, cluster_id),
            )
            row = cur.fetchone()
            if row:
                return _merge_state(row)

            cur.execute(
                f"""
                INSERT INTO user_cluster_states (user_id, cluster_id)
                VALUES (%s, %s)
                RETURNING {columns}
                """,
                (user_id, cluster_id),
            )
            conn.commit()
            return _merge_state(cur.fetchone())
    finally:
        conn.close()


def update_user_cluster_state(user_id: int, cluster_id: int, **fields) -> None:
    """Update per-user cluster state fields.

    Allowed fields: ``estado_publicacion``, ``url_wp``, ``veces_publicado``,
    ``ultima_publicacion``, ``descartado_en``, ``requiere_revision_editorial``,
    ``titulo_representativo``, ``contenido_ia``, ``foto_principal``,
    ``fotos_secundarias``, ``nota_editor``, ``nota_ia``.
    Unknown fields are ignored.
    """
    allowed = {
        "estado_publicacion",
        "url_wp",
        "veces_publicado",
        "ultima_publicacion",
        "descartado_en",
        "requiere_revision_editorial",
        "titulo_representativo",
        "contenido_ia",
        "foto_principal",
        "fotos_secundarias",
        "nota_editor",
        "nota_ia",
    }
    to_update = {k: v for k, v in fields.items() if k in allowed}
    if not to_update:
        return

    columns = list(to_update.keys())
    set_clause = ", ".join(f"{col} = %s" for col in columns) + ", updated_at = NOW()"

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


def save_user_cluster_content(
    user_id: int,
    cluster_id: int,
    *,
    titulo_representativo: str | None = None,
    contenido_ia: dict[str, Any] | None = None,
    foto_principal: str | None = None,
    fotos_secundarias: list[str] | None = None,
    nota_editor: str | None = None,
    nota_ia: str | None = None,
) -> None:
    """Persist generated editorial content for a specific user and cluster."""
    fields: dict[str, Any] = {}
    if titulo_representativo is not None:
        fields["titulo_representativo"] = titulo_representativo
    if contenido_ia is not None:
        fields["contenido_ia"] = json.dumps(contenido_ia, ensure_ascii=False)
    if foto_principal is not None:
        fields["foto_principal"] = foto_principal
    if fotos_secundarias is not None:
        fields["fotos_secundarias"] = json.dumps(fotos_secundarias, ensure_ascii=False)
    if nota_editor is not None:
        fields["nota_editor"] = nota_editor
    if nota_ia is not None:
        fields["nota_ia"] = nota_ia

    if fields:
        update_user_cluster_state(user_id, cluster_id, **fields)


def get_cluster_news_for_user(cluster_id: int, user_id: int) -> list[dict[str, Any]]:
    """Return news items in the cluster from the user's subscribed sources.

    Results are ordered by ``fecha_publicacion`` DESC, then
    ``fecha_extraccion`` DESC.
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
                    id,
                    fuente,
                    titulo,
                    fecha_publicacion,
                    fecha_extraccion,
                    texto_completo,
                    url_imagen,
                    url_original
                FROM noticias_historico
                WHERE cluster_id = %s
                  AND LOWER(fuente) = ANY(%s)
                ORDER BY fecha_publicacion DESC, fecha_extraccion DESC
                """,
                (cluster_id, subscribed_slugs),
            )
            return cur.fetchall()
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
                    COALESCE(ucs.titulo_representativo, ce.titulo_representativo) AS titulo_representativo,
                    ce.cantidad_noticias,
                    ce.cantidad_fuentes,
                    ce.score,
                    ce.tendencia,
                    ce.primera_noticia,
                    ce.ultima_noticia,
                    ucs.contenido_ia,
                    ucs.foto_principal,
                    ucs.fotos_secundarias,
                    COALESCE(ucs.estado_publicacion, 'pendiente') AS estado_publicacion,
                    COALESCE(ucs.requiere_revision_editorial, FALSE) AS requiere_revision_editorial,
                    ucs.url_wp,
                    COALESCE(ucs.veces_publicado, 0) AS veces_publicado,
                    ucs.ultima_publicacion,
                    ucs.descartado_en,
                    ucs.nota_editor,
                    ucs.nota_ia
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
                         ucs.titulo_representativo, ucs.contenido_ia,
                         ucs.foto_principal, ucs.fotos_secundarias,
                         ucs.estado_publicacion, ucs.requiere_revision_editorial,
                         ucs.url_wp, ucs.veces_publicado, ucs.ultima_publicacion,
                         ucs.descartado_en, ucs.nota_editor, ucs.nota_ia
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
                    COALESCE(ucs.titulo_representativo, ce.titulo_representativo) AS titulo_representativo,
                    ucs.contenido_ia,
                    ce.estado,
                    ucs.foto_principal,
                    ucs.fotos_secundarias,
                    ucs.nota_editor,
                    ucs.nota_ia,
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
