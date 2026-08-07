from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


def _patch_auth(monkeypatch, user=None, password_valid=True):
    monkeypatch.setattr(
        "trh.web.auth_routes.get_user_by_username",
        lambda _usuario: user,
    )
    monkeypatch.setattr(
        "trh.web.auth_routes.verify_password",
        lambda _password, _hash: password_valid,
    )
    monkeypatch.setattr(
        "trh.web.auth_routes.update_last_login",
        lambda _user_id: None,
    )


def _create_session_patch(monkeypatch, token="session-token", csrf="csrf-token"):
    expires = datetime.utcnow() + timedelta(hours=24)
    monkeypatch.setattr(
        "trh.web.auth_routes.create_session_for_user",
        lambda **kwargs: (token, csrf, expires),
    )


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Required prompt files so trh.web.app can import cleanly
    from tests.test_app_wrapper_and_cluster_state import _write_required_prompt_files
    env_vars = _write_required_prompt_files(tmp_path, "login")
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    import importlib
    import sys

    for module_name in (
        "app",
        "trh.web.app",
        "trh.web.auth_routes",
        "trh.publication.publicador",
        "trh.publication.publicapress",
        "trh.publication",
        "pipeline.seleccionar_publicables",
    ):
        sys.modules.pop(module_name, None)

    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("AUTH_REQUIRED", "True")
    monkeypatch.setenv("WTF_CSRF_ENABLED", "False")

    web_app = importlib.import_module("trh.web.app")
    test_client = web_app.app.test_client()

    # Clean up after the test so existing tests that import the app.py wrapper
    # do not trigger its reload logic and end up with mismatched module objects.
    def _cleanup_modules():
        for module_name in ("app", "trh.web.app", "trh.web.auth_routes"):
            sys.modules.pop(module_name, None)

    yield test_client
    _cleanup_modules()


def test_login_page_renders_form(client):
    response = client.get("/auth/login")

    assert response.status_code == 200
    assert b"Iniciar sesi" in response.data
    assert b'csrf_token' in response.data


def test_login_success_redirects_and_sets_cookie(client, monkeypatch):
    _patch_auth(
        monkeypatch,
        user={
            "id": 1,
            "usuario": "admin",
            "password_hash": "hash",
            "nombre": "Admin",
            "is_admin": True,
        },
    )
    _create_session_patch(monkeypatch)
    csrf_token = _extract_csrf_token(client.get("/auth/login").data)

    response = client.post(
        "/auth/login",
        data={"usuario": "admin", "password": "admin", "csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.location == "/"
    assert "session_token" in response.headers.getlist("Set-Cookie")[0]


def test_login_failure_shows_error_without_session(client, monkeypatch):
    _patch_auth(monkeypatch, user=None)
    csrf_token = _extract_csrf_token(client.get("/auth/login").data)

    response = client.post(
        "/auth/login",
        data={"usuario": "admin", "password": "wrong", "csrf_token": csrf_token},
    )

    assert response.status_code == 401
    assert b"incorrectos" in response.data
    assert "session_token" not in response.headers.get("Set-Cookie", "")


def test_login_requires_csrf_token(client, monkeypatch):
    _patch_auth(
        monkeypatch,
        user={
            "id": 1,
            "usuario": "admin",
            "password_hash": "hash",
            "nombre": "Admin",
            "is_admin": True,
        },
    )

    response = client.post(
        "/auth/login",
        data={"usuario": "admin", "password": "admin"},
    )

    assert response.status_code == 403
    assert b"CSRF" in response.data or response.json == {"error": "Token CSRF inválido o faltante."}


def test_login_validates_csrf_token_from_session(client, monkeypatch):
    _patch_auth(
        monkeypatch,
        user={
            "id": 1,
            "usuario": "admin",
            "password_hash": "hash",
            "nombre": "Admin",
            "is_admin": True,
        },
    )
    _create_session_patch(monkeypatch)

    get_response = client.get("/auth/login")
    csrf_token = _extract_csrf_token(get_response.data)

    response = client.post(
        "/auth/login",
        data={"usuario": "admin", "password": "admin", "csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 302


def _extract_csrf_token(html):
    import re
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html.decode())
    assert match, "CSRF token not found in form"
    return match.group(1)


def test_login_rate_limits_by_username(client, monkeypatch):
    _patch_auth(monkeypatch, user=None)

    for attempt in range(5):
        csrf_token = _extract_csrf_token(client.get("/auth/login").data)
        response = client.post(
            "/auth/login",
            data={"usuario": "brute", "password": "wrong", "csrf_token": csrf_token},
        )
        assert response.status_code in (401, 403)

    csrf_token = _extract_csrf_token(client.get("/auth/login").data)
    response = client.post(
        "/auth/login",
        data={"usuario": "brute", "password": "wrong", "csrf_token": csrf_token},
    )

    assert response.status_code == 429


def test_logout_deletes_session_and_cookie(client, monkeypatch):
    _patch_auth(
        monkeypatch,
        user={
            "id": 1,
            "usuario": "admin",
            "password_hash": "hash",
            "nombre": "Admin",
            "is_admin": True,
        },
    )
    _create_session_patch(monkeypatch)

    # log in
    get_response = client.get("/auth/login")
    csrf_token = _extract_csrf_token(get_response.data)
    login_response = client.post(
        "/auth/login",
        data={"usuario": "admin", "password": "admin", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert login_response.status_code == 302

    deleted_tokens = []
    monkeypatch.setattr(
        "trh.web.auth_routes.delete_session",
        lambda token: deleted_tokens.append(token),
    )

    # Provide a valid server-side session for logout auth and CSRF checks
    monkeypatch.setattr(
        "trh.auth.sessions.repo_get_session_by_token",
        lambda _token: {
            "session_token": "session-token",
            "expires_at": datetime.utcnow() + timedelta(hours=1),
            "csrf_token": "csrf-token",
            "usuario": "admin",
            "is_admin": True,
        },
    )

    response = client.post(
        "/auth/logout",
        data={"csrf_token": "csrf-token"},
    )

    assert response.status_code == 302
    assert "/auth/login" in response.location
    assert len(deleted_tokens) == 1
