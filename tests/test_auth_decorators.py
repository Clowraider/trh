import pytest
from flask import Flask, jsonify

from trh.auth.decorators import require_admin, require_auth


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test"
    app.config["AUTH_REQUIRED"] = True

    @app.route("/protected")
    @require_auth
    def protected():
        return "ok"

    @app.route("/admin")
    @require_admin
    def admin_only():
        return "admin ok"

    @app.route("/json-protected")
    @require_auth
    def json_protected():
        return jsonify({"ok": True})

    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_require_auth_redirects_to_login_without_session(client):
    response = client.get("/protected")

    assert response.status_code == 302
    assert "/auth/login" in response.location


def test_require_auth_allows_request_with_valid_session(client, monkeypatch):
    monkeypatch.setattr(
        "trh.auth.decorators.validate_session_token",
        lambda _token: {"user_id": 1, "usuario": "admin", "is_admin": True},
    )

    response = client.get("/protected", headers={"Cookie": "session_token=valid"})

    assert response.status_code == 200
    assert response.data == b"ok"


def test_require_auth_returns_401_for_json_without_session(client):
    response = client.get(
        "/json-protected",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 401
    assert response.json == {"error": "Unauthorized"}


def test_require_admin_blocks_non_admin(client, monkeypatch):
    monkeypatch.setattr(
        "trh.auth.decorators.validate_session_token",
        lambda _token: {"user_id": 1, "usuario": "user", "is_admin": False},
    )

    response = client.get("/admin", headers={"Cookie": "session_token=valid"})

    assert response.status_code == 403


def test_require_admin_allows_admin(client, monkeypatch):
    monkeypatch.setattr(
        "trh.auth.decorators.validate_session_token",
        lambda _token: {"user_id": 1, "usuario": "admin", "is_admin": True},
    )

    response = client.get("/admin", headers={"Cookie": "session_token=valid"})

    assert response.status_code == 200
    assert response.data == b"admin ok"


def test_require_auth_skips_check_when_auth_disabled(app, client):
    app.config["AUTH_REQUIRED"] = False

    response = client.get("/protected")

    assert response.status_code == 200
    assert response.data == b"ok"


def test_require_admin_skips_check_when_auth_disabled(app, client):
    app.config["AUTH_REQUIRED"] = False

    response = client.get("/admin")

    assert response.status_code == 200
    assert response.data == b"admin ok"
