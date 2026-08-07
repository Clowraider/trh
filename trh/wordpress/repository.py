"""Repository for per-user WordPress configuration."""

from typing import Any

from pipeline.seleccionar_publicables import get_connection


def _connection():
    return get_connection()


def get_wordpress_config_by_user(user_id: int) -> dict[str, Any] | None:
    """Return the WordPress config for a user, or None if not configured."""
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, wp_url, wp_username, wp_app_password,
                       created_at, updated_at
                FROM user_wordpress_configs
                WHERE user_id = %s
                """,
                (user_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def create_wordpress_config(
    user_id: int,
    wp_url: str,
    wp_username: str,
    wp_app_password: str,
) -> int:
    """Create a WordPress config for a user and return its id."""
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_wordpress_configs (
                    user_id, wp_url, wp_username, wp_app_password
                ) VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (user_id, wp_url, wp_username, wp_app_password),
            )
            config_id = cur.fetchone()["id"]
        conn.commit()
        return config_id
    finally:
        conn.close()


def update_wordpress_config(
    user_id: int,
    wp_url: str,
    wp_username: str,
    wp_app_password: str,
) -> None:
    """Update an existing WordPress config for a user."""
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_wordpress_configs
                SET wp_url = %s,
                    wp_username = %s,
                    wp_app_password = %s,
                    updated_at = NOW()
                WHERE user_id = %s
                """,
                (wp_url, wp_username, wp_app_password, user_id),
            )
        conn.commit()
    finally:
        conn.close()


def upsert_wordpress_config(
    user_id: int,
    wp_url: str,
    wp_username: str,
    wp_app_password: str,
) -> None:
    """Create or update the WordPress config for a user."""
    existing = get_wordpress_config_by_user(user_id)
    if existing is None:
        create_wordpress_config(user_id, wp_url, wp_username, wp_app_password)
    else:
        update_wordpress_config(user_id, wp_url, wp_username, wp_app_password)
