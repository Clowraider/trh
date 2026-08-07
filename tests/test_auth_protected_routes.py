import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    from tests.test_app_wrapper_and_cluster_state import _write_required_prompt_files
    env_vars = _write_required_prompt_files(tmp_path, "protected")
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


@pytest.mark.parametrize(
    "path,method",
    [
        ("/", "GET"),
        ("/config", "GET"),
        ("/config", "POST"),
        ("/editor-jefe-ia", "GET"),
        ("/editor-jefe-ia", "POST"),
        ("/reportes/calidad", "GET"),
        ("/keywords-prioridad", "GET"),
        ("/keywords-prioridad/crear", "POST"),
        ("/cluster/1", "GET"),
        ("/generar/1", "POST"),
        ("/preview/1", "GET"),
        ("/guardar-edicion/1", "POST"),
        ("/publicar/1", "POST"),
        ("/noticia/1", "GET"),
    ],
)
def test_existing_routes_redirect_to_login_when_unauthenticated(client, path, method):
    response = client.open(path, method=method)

    assert response.status_code == 302
    assert "/auth/login" in response.location


def test_static_route_is_accessible_without_auth(client):
    # The static folder may not have a favicon; just verify it is not redirected.
    response = client.get("/static/nonexistent.css")

    assert response.status_code in (200, 404)
    assert response.status_code != 302


def test_login_get_is_accessible_without_auth(client):
    response = client.get("/auth/login")

    assert response.status_code == 200
