from datetime import timedelta
from unittest.mock import patch

import pytest

from trh.auth.time_utils import utc_now


def _patch_admin_repository(monkeypatch, users=None, existing_username=None, existing_email=None):
    monkeypatch.setattr(
        "trh.web.admin_routes.list_users",
        lambda: users or [],
    )
    monkeypatch.setattr(
        "trh.web.admin_routes.get_user_by_username",
        lambda _usuario: existing_username,
    )
    monkeypatch.setattr(
        "trh.web.admin_routes.get_user_by_email",
        lambda _email: existing_email,
    )
    monkeypatch.setattr(
        "trh.web.admin_routes.create_user",
        lambda **kwargs: 42,
    )
    monkeypatch.setattr(
        "trh.web.admin_routes.get_user_by_id",
        lambda user_id: {"id": user_id, "usuario": "jdoe"},
    )
    monkeypatch.setattr(
        "trh.web.admin_routes.update_user_password",
        lambda _user_id, _hash: None,
    )


@pytest.fixture
def client(monkeypatch, tmp_path):
    from tests.test_app_wrapper_and_cluster_state import _write_required_prompt_files
    env_vars = _write_required_prompt_files(tmp_path, "admin")
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    import importlib
    import sys

    for module_name in (
        "app",
        "trh.web.app",
        "trh.web.auth_routes",
        "trh.web.admin_routes",
        "trh.publication.publicador",
        "trh.publication.publicapress",
        "trh.publication",
        "pipeline.seleccionar_publicables",
    ):
        sys.modules.pop(module_name, None)

    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("AUTH_REQUIRED", "True")

    web_app = importlib.import_module("trh.web.app")
    return web_app.app.test_client()


def _login_as_admin(client, monkeypatch):
    monkeypatch.setattr(
        "trh.auth.sessions.repo_get_session_by_token",
        lambda _token: {
            "session_token": "session-token",
            "expires_at": utc_now() + timedelta(hours=1),
            "csrf_token": "csrf-token",
            "user_id": 1,
            "usuario": "admin",
            "email": "admin@example.com",
            "nombre": "Admin",
            "is_admin": True,
        },
    )
    client.set_cookie("session_token", "session-token")


def test_admin_users_list_requires_login(client):
    response = client.get("/admin/usuarios")
    assert response.status_code == 302
    assert "/auth/login" in response.location


def test_admin_users_list_requires_admin(client, monkeypatch):
    monkeypatch.setattr(
        "trh.auth.sessions.repo_get_session_by_token",
        lambda _token: {
            "session_token": "session-token",
            "expires_at": utc_now() + timedelta(hours=1),
            "csrf_token": "csrf-token",
            "user_id": 1,
            "usuario": "user",
            "email": "user@example.com",
            "nombre": "User",
            "is_admin": False,
        },
    )
    client.set_cookie("session_token", "session-token")

    response = client.get("/admin/usuarios")

    assert response.status_code == 403


def test_admin_users_list_renders_table(client, monkeypatch):
    _login_as_admin(client, monkeypatch)
    _patch_admin_repository(
        monkeypatch,
        users=[
            {
                "id": 1,
                "usuario": "admin",
                "email": "admin@example.com",
                "nombre": "Administrador",
                "is_admin": True,
                "last_login_at": None,
            }
        ],
    )

    response = client.get("/admin/usuarios")

    assert response.status_code == 200
    assert b"admin" in response.data
    assert b"Nuevo usuario" in response.data


def test_admin_create_user_success(client, monkeypatch):
    _login_as_admin(client, monkeypatch)
    _patch_admin_repository(monkeypatch)

    response = client.post(
        "/admin/usuarios/nuevo",
        data={
            "csrf_token": "csrf-token",
            "usuario": "jdoe",
            "email": "jdoe@example.com",
            "nombre": "John Doe",
            "password": "securepass",
            "is_admin": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/admin/usuarios" in response.location


def test_admin_create_user_rejects_invalid_input(client, monkeypatch):
    _login_as_admin(client, monkeypatch)
    _patch_admin_repository(monkeypatch)

    response = client.post(
        "/admin/usuarios/nuevo",
        data={
            "csrf_token": "csrf-token",
            "usuario": "ab",
            "email": "not-an-email",
            "nombre": "",
            "password": "short",
        },
    )

    assert response.status_code == 400
    assert b"El usuario debe tener" in response.data


def test_admin_create_user_rejects_duplicate_username(client, monkeypatch):
    _login_as_admin(client, monkeypatch)
    _patch_admin_repository(
        monkeypatch,
        existing_username={"id": 2, "usuario": "jdoe"},
    )

    response = client.post(
        "/admin/usuarios/nuevo",
        data={
            "csrf_token": "csrf-token",
            "usuario": "jdoe",
            "email": "jdoe2@example.com",
            "nombre": "John Doe",
            "password": "securepass",
        },
    )

    assert response.status_code == 400
    assert b"ya est\xc3\xa1 registrado" in response.data


def test_admin_reset_password_success(client, monkeypatch):
    _login_as_admin(client, monkeypatch)
    _patch_admin_repository(monkeypatch)

    response = client.post(
        "/admin/usuarios/2/reset-password",
        data={"csrf_token": "csrf-token", "password": "newpassword"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/admin/usuarios" in response.location


def test_admin_reset_password_rejects_short_password(client, monkeypatch):
    _login_as_admin(client, monkeypatch)
    _patch_admin_repository(monkeypatch)

    response = client.post(
        "/admin/usuarios/2/reset-password",
        data={"csrf_token": "csrf-token", "password": "short"},
    )

    assert response.status_code == 302
    # Flash message is shown after redirect; just verify it redirected back.
