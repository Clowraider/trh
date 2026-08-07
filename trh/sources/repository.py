"""Repository for news sources and per-user source subscriptions."""

from typing import Any

from pipeline.seleccionar_publicables import get_connection


def _connection():
    return get_connection()


def _news_sources_table_exists(cur) -> bool:
    cur.execute("SELECT to_regclass('public.news_sources') AS table_name")
    row = cur.fetchone()
    return row is not None and row.get("table_name") is not None


def sync_news_sources() -> None:
    """Idempotently create or update news_sources rows from noticias_historico.

    New distinct ``fuente`` values become active sources. Existing slugs keep
    their ``name`` and ``updated_at`` refreshed so the canonical display name
    stays in sync with the crawler data.
    """
    conn = _connection()
    try:
        with conn.cursor() as cur:
            if not _news_sources_table_exists(cur):
                return

            cur.execute(
                """
                SELECT DISTINCT fuente
                FROM noticias_historico
                WHERE fuente IS NOT NULL
                """
            )
            rows = cur.fetchall()

            for row in rows:
                name = (row.get("fuente") or "").strip()
                if not name:
                    continue
                slug = name.lower()
                cur.execute(
                    """
                    INSERT INTO news_sources (slug, name)
                    VALUES (%s, %s)
                    ON CONFLICT (slug) DO UPDATE SET
                        name = EXCLUDED.name,
                        updated_at = NOW()
                    """,
                    (slug, name),
                )
        conn.commit()
    finally:
        conn.close()


def list_active_sources() -> list[dict[str, Any]]:
    """Return all active news sources ordered by name."""
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, slug, name
                FROM news_sources
                WHERE is_active = TRUE
                ORDER BY name ASC
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


def get_subscribed_source_ids(user_id: int) -> set[int]:
    """Return the set of source_ids the user is subscribed to."""
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_id
                FROM user_source_subscriptions
                WHERE user_id = %s
                """,
                (user_id,),
            )
            return {row["source_id"] for row in cur.fetchall()}
    finally:
        conn.close()


def subscribe_user_to_sources(user_id: int, source_ids: list[int]) -> None:
    """Replace all subscriptions for the user with the given source IDs.

    Raises:
        ValueError: if any source_id does not exist in news_sources.
    """
    normalized = sorted({int(source_id) for source_id in source_ids})

    conn = _connection()
    try:
        with conn.cursor() as cur:
            if normalized:
                placeholders = ", ".join("%s" for _ in normalized)
                cur.execute(
                    f"""
                    SELECT id
                    FROM news_sources
                    WHERE id IN ({placeholders})
                    """,
                    tuple(normalized),
                )
                valid_ids = {row["id"] for row in cur.fetchall()}
                invalid = set(normalized) - valid_ids
                if invalid:
                    raise ValueError(
                        f"Los siguientes IDs de fuente no existen: {sorted(invalid)}"
                    )

            cur.execute(
                """
                DELETE FROM user_source_subscriptions
                WHERE user_id = %s
                """,
                (user_id,),
            )

            for source_id in normalized:
                cur.execute(
                    """
                    INSERT INTO user_source_subscriptions (user_id, source_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id, source_id) DO NOTHING
                    """,
                    (user_id, source_id),
                )
        conn.commit()
    finally:
        conn.close()
