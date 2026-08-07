"""Database CRUD for users and sessions."""

from datetime import datetime
from typing import Any

from pipeline.seleccionar_publicables import get_connection


def _connection():
    return get_connection()


def list_users() -> list[dict[str, Any]]:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, usuario, email, nombre, ciudad, provincia, pais,
                       notas, is_admin, created_at, updated_at, last_login_at
                FROM users
                ORDER BY id
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, usuario, email, password_hash, nombre, ciudad, provincia,
                       pais, notas, is_admin, created_at, updated_at, last_login_at
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def get_user_by_username(usuario: str) -> dict[str, Any] | None:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, usuario, email, password_hash, nombre, ciudad, provincia,
                       pais, notas, is_admin, created_at, updated_at, last_login_at
                FROM users
                WHERE usuario = %s
                """,
                (usuario,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict[str, Any] | None:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, usuario, email, password_hash, nombre, ciudad, provincia,
                       pais, notas, is_admin, created_at, updated_at, last_login_at
                FROM users
                WHERE email = %s
                """,
                (email,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def create_user(
    usuario: str,
    email: str,
    password_hash: str,
    nombre: str,
    ciudad: str | None = None,
    provincia: str | None = None,
    pais: str | None = None,
    notas: str | None = None,
    is_admin: bool = False,
) -> int:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (
                    usuario, email, password_hash, nombre, ciudad, provincia,
                    pais, notas, is_admin
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    usuario,
                    email,
                    password_hash,
                    nombre,
                    ciudad,
                    provincia,
                    pais,
                    notas,
                    is_admin,
                ),
            )
            user_id = cur.fetchone()["id"]
        conn.commit()
        return user_id
    finally:
        conn.close()


def update_user(
    user_id: int,
    email: str | None = None,
    nombre: str | None = None,
    ciudad: str | None = None,
    provincia: str | None = None,
    pais: str | None = None,
    notas: str | None = None,
    is_admin: bool | None = None,
) -> None:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            fields = []
            values = []
            if email is not None:
                fields.append("email = %s")
                values.append(email)
            if nombre is not None:
                fields.append("nombre = %s")
                values.append(nombre)
            if ciudad is not None:
                fields.append("ciudad = %s")
                values.append(ciudad)
            if provincia is not None:
                fields.append("provincia = %s")
                values.append(provincia)
            if pais is not None:
                fields.append("pais = %s")
                values.append(pais)
            if notas is not None:
                fields.append("notas = %s")
                values.append(notas)
            if is_admin is not None:
                fields.append("is_admin = %s")
                values.append(is_admin)
            if not fields:
                return
            values.append(user_id)
            cur.execute(
                f"""
                UPDATE users
                SET {', '.join(fields)}, updated_at = NOW()
                WHERE id = %s
                """,
                tuple(values),
            )
        conn.commit()
    finally:
        conn.close()


def update_user_password(user_id: int, password_hash: str) -> None:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET password_hash = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (password_hash, user_id),
            )
        conn.commit()
    finally:
        conn.close()


def delete_user(user_id: int) -> None:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()


def update_last_login(user_id: int) -> None:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET last_login_at = NOW()
                WHERE id = %s
                """,
                (user_id,),
            )
        conn.commit()
    finally:
        conn.close()


def create_session(
    session_token: str,
    user_id: int,
    expires_at: datetime,
    csrf_token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions (
                    session_token, user_id, expires_at, csrf_token,
                    ip_address, user_agent
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    session_token,
                    user_id,
                    expires_at,
                    csrf_token,
                    ip_address,
                    user_agent,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_session_by_token(session_token: str) -> dict[str, Any] | None:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.session_token, s.user_id, s.expires_at, s.csrf_token,
                       s.ip_address, s.user_agent, s.created_at,
                       u.usuario, u.email, u.nombre, u.is_admin
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.session_token = %s
                """,
                (session_token,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def delete_session(session_token: str) -> None:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM sessions WHERE session_token = %s",
                (session_token,),
            )
        conn.commit()
    finally:
        conn.close()


def delete_user_sessions(user_id: int) -> None:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()
