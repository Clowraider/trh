import re
from datetime import timedelta
from unittest.mock import patch

import pytest

from trh.auth.time_utils import utc_now


@pytest.fixture
def client(monkeypatch, tmp_path):
    from tests.test_app_wrapper_and_cluster_state import _write_required_prompt_files
    env_vars = _write_required_prompt_files(tmp_path, "config")
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    import importlib
    import sys

    for module_name in (
        "app",
        "trh.web.app",
        "trh.web.auth_routes",
        "trh.web.admin_routes",
        "trh.web.config_routes",
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


@pytest.fixture
def sample_sources():
    return [
        {"id": 1, "slug": "el-liberal", "name": "El Liberal"},
        {"id": 2, "slug": "clarin", "name": "Clarín"},
        {"id": 3, "slug": "lanacion", "name": "La Nación"},
    ]


def _login_as_user(client, monkeypatch, user_id=2, is_admin=False):
    monkeypatch.setattr(
        "trh.auth.sessions.repo_get_session_by_token",
        lambda _token: {
            "session_token": "session-token",
            "expires_at": utc_now() + timedelta(hours=1),
            "csrf_token": "csrf-token",
            "user_id": user_id,
            "usuario": "jdoe",
            "email": "jdoe@example.com",
            "nombre": "John Doe",
            "is_admin": is_admin,
        },
    )
    client.set_cookie("session_token", "session-token")


def test_config_requires_login(client):
    response = client.get("/config")

    assert response.status_code == 302
    assert "/auth/login" in response.location


def test_config_get_renders_form_for_authenticated_user(client, monkeypatch, sample_sources):
    _login_as_user(client, monkeypatch)

    with (
        patch(
            "trh.web.config_routes.get_wordpress_config_by_user",
            return_value={
                "id": 1,
                "user_id": 2,
                "wp_url": "https://wp.test",
                "wp_username": "admin",
                "wp_app_password": "secret",
            },
        ),
        patch(
            "trh.web.config_routes.list_active_sources",
            return_value=sample_sources,
        ),
        patch(
            "trh.web.config_routes.get_subscribed_source_ids",
            return_value={1, 3},
        ),
    ):
        response = client.get("/config")

    assert response.status_code == 200
    assert b"WordPress" in response.data
    assert b"https://wp.test" in response.data
    assert b"admin" in response.data
    assert b"El Liberal" in response.data
    assert "La Nación".encode() in response.data

    html = response.data.decode()
    assert re.search(r'id="source_1"[^>]*checked', html)
    assert re.search(r'id="source_3"[^>]*checked', html)
    assert 'id="source_2"' in html
    assert not re.search(r'id="source_2"[^>]*checked', html)


def test_config_post_saves_valid_config_and_subscriptions(
    client, monkeypatch, sample_sources
):
    _login_as_user(client, monkeypatch)

    with (
        patch(
            "trh.web.config_routes.get_wordpress_config_by_user",
            return_value=None,
        ),
        patch(
            "trh.web.config_routes.list_active_sources",
            return_value=sample_sources,
        ),
        patch(
            "trh.web.config_routes.get_subscribed_source_ids",
            return_value=set(),
        ),
        patch(
            "trh.web.config_routes.validate_wordpress_credentials",
            return_value=(True, "OK"),
        ) as mock_validate,
        patch(
            "trh.web.config_routes.upsert_wordpress_config",
            return_value=None,
        ) as mock_upsert,
        patch(
            "trh.web.config_routes.subscribe_user_to_sources",
            return_value=None,
        ) as mock_subscribe,
    ):
        response = client.post(
            "/config",
            data={
                "csrf_token": "csrf-token",
                "wp_url": "https://wp.test/",
                "wp_username": "admin",
                "wp_app_password": "app-password",
                "wp_app_password_confirm": "app-password",
                "source_ids": ["1", "3"],
            },
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert "/config" in response.location
    mock_validate.assert_called_once_with(
        "https://wp.test/", "admin", "app-password"
    )
    mock_subscribe.assert_called_once_with(2, [1, 3])
    mock_upsert.assert_called_once_with(
        user_id=2,
        wp_url="https://wp.test/",
        wp_username="admin",
        wp_app_password="app-password",
    )


def test_config_post_rejects_mismatched_passwords(client, monkeypatch, sample_sources):
    _login_as_user(client, monkeypatch)

    with (
        patch(
            "trh.web.config_routes.get_wordpress_config_by_user",
            return_value=None,
        ),
        patch(
            "trh.web.config_routes.list_active_sources",
            return_value=sample_sources,
        ),
        patch(
            "trh.web.config_routes.get_subscribed_source_ids",
            return_value=set(),
        ),
        patch(
            "trh.web.config_routes.validate_wordpress_credentials",
        ) as mock_validate,
    ):
        response = client.post(
            "/config",
            data={
                "csrf_token": "csrf-token",
                "wp_url": "https://wp.test/",
                "wp_username": "admin",
                "wp_app_password": "app-password",
                "wp_app_password_confirm": "other-password",
                "source_ids": ["1"],
            },
        )

    assert response.status_code == 400
    assert b"no coinciden" in response.data
    mock_validate.assert_not_called()


def test_config_post_rejects_wordpress_validation_failure(
    client, monkeypatch, sample_sources
):
    _login_as_user(client, monkeypatch)

    with (
        patch(
            "trh.web.config_routes.get_wordpress_config_by_user",
            return_value=None,
        ),
        patch(
            "trh.web.config_routes.list_active_sources",
            return_value=sample_sources,
        ),
        patch(
            "trh.web.config_routes.get_subscribed_source_ids",
            return_value=set(),
        ),
        patch(
            "trh.web.config_routes.validate_wordpress_credentials",
            return_value=(False, "No se pudo conectar con WordPress. Verificá..."),
        ) as mock_validate,
    ):
        response = client.post(
            "/config",
            data={
                "csrf_token": "csrf-token",
                "wp_url": "https://wp.test/",
                "wp_username": "admin",
                "wp_app_password": "app-password",
                "wp_app_password_confirm": "app-password",
                "source_ids": ["2"],
            },
        )

    assert response.status_code == 400
    assert b"No se pudo conectar con WordPress" in response.data
    mock_validate.assert_called_once()


def test_config_post_rejects_invalid_source_ids(client, monkeypatch, sample_sources):
    _login_as_user(client, monkeypatch)

    with (
        patch(
            "trh.web.config_routes.get_wordpress_config_by_user",
            return_value=None,
        ),
        patch(
            "trh.web.config_routes.list_active_sources",
            return_value=sample_sources,
        ),
        patch(
            "trh.web.config_routes.get_subscribed_source_ids",
            return_value=set(),
        ),
        patch(
            "trh.web.config_routes.validate_wordpress_credentials",
            return_value=(True, "OK"),
        ),
        patch(
            "trh.web.config_routes.subscribe_user_to_sources",
            side_effect=ValueError("Los siguientes IDs de fuente no existen: [99]"),
        ) as mock_subscribe,
    ):
        response = client.post(
            "/config",
            data={
                "csrf_token": "csrf-token",
                "wp_url": "https://wp.test/",
                "wp_username": "admin",
                "wp_app_password": "app-password",
                "wp_app_password_confirm": "app-password",
                "source_ids": ["99"],
            },
        )

    assert response.status_code == 400
    assert b"IDs de fuente no existen" in response.data
    mock_subscribe.assert_called_once_with(2, [99])
