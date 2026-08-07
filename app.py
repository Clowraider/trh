"""Thin entrypoint that preserves the historic `app` import path."""

from __future__ import annotations

import importlib
import sys

from trh.infrastructure.env_loader import load_project_env


load_project_env()


_RELOAD_DEPENDENCY_MODULES = (
    "trh.publication.publicador",
    "trh.publication.publicapress",
    "trh.publication",
    "trh.editorial.editorial_control",
    "trh.editorial.editor_jefe_ia",
    "trh.editorial",
    "pipeline.seleccionar_publicables",
    "trh.web.auth_routes",
)


def _load_web_app_module():
    cached_module = sys.modules.get("trh.web.app")
    if cached_module is not None:
        for module_name in _RELOAD_DEPENDENCY_MODULES:
            dependency = sys.modules.get(module_name)
            if dependency is not None:
                try:
                    importlib.reload(dependency)
                except Exception:
                    sys.modules.pop(module_name, None)
        return importlib.reload(cached_module)
    return importlib.import_module("trh.web.app")


_web_app_module = _load_web_app_module()


if __name__ == "__main__":
    _web_app_module.main()
else:
    sys.modules[__name__] = _web_app_module
