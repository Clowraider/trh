import importlib
import os
import sys

import pytest


def _clear_app_modules():
    for module_name in (
        "app",
        "trh.web.app",
        "trh.publication.publicador",
        "trh.publication.publicapress",
        "trh.publication",
        "trh.editorial.editorial_control",
        "trh.editorial.editor_jefe_ia",
        "trh.editorial",
        "pipeline.seleccionar_publicables",
    ):
        sys.modules.pop(module_name, None)


def test_load_secret_key_uses_configured_value(monkeypatch):
    _clear_app_modules()
    monkeypatch.setenv("SECRET_KEY", "configured-secret")
    monkeypatch.setenv("FLASK_ENV", "production")

    web_app = importlib.import_module("trh.web.app")

    assert web_app.app.secret_key == "configured-secret"


def test_load_secret_key_generates_temporary_key_in_development(monkeypatch):
    _clear_app_modules()
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("FLASK_ENV", "development")

    web_app = importlib.import_module("trh.web.app")

    assert isinstance(web_app.app.secret_key, str)
    assert len(web_app.app.secret_key) >= 32


def test_load_secret_key_fails_closed_in_production(monkeypatch):
    _clear_app_modules()
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("FLASK_ENV", "production")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        importlib.import_module("trh.web.app")
