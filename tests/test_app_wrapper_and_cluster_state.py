import importlib
import json
import sys
from datetime import datetime

import pytest


def _write_required_prompt_files(tmp_path, suffix):
    writer_system_prompt = tmp_path / f"article_writer_system_prompt_{suffix}.txt"
    writer_system_prompt.write_text(f"Writer system {suffix}", encoding="utf-8")

    writer_user_prompt = tmp_path / f"article_writer_user_prompt_{suffix}.txt"
    writer_user_prompt.write_text(
        "Fuentes:\n$sources_block\n\nNota:\n$editorial_guidance_block\n\nCategorías: $categories_list",
        encoding="utf-8",
    )

    editor_jefe_prompt = tmp_path / f"editor_jefe_system_prompt_{suffix}.txt"
    editor_jefe_prompt.write_text(f"Editor jefe {suffix}", encoding="utf-8")

    editorial_control_prompt = tmp_path / f"editorial_control_system_prompt_{suffix}.txt"
    editorial_control_prompt.write_text(
        f"Editorial control {suffix}",
        encoding="utf-8",
    )

    editorial_rules = tmp_path / f"editorial_control_rules_{suffix}.json"
    editorial_rules.write_text(
        json.dumps([{"code": f"rule_{suffix}", "instruction": f"Instruction {suffix}"}]),
        encoding="utf-8",
    )

    article_categories = tmp_path / f"article_categories_{suffix}.json"
    article_categories.write_text(
        json.dumps({"categories": ["Salud", "Política"]}),
        encoding="utf-8",
    )

    return {
        "ARTICLE_WRITER_SYSTEM_PROMPT_FILE": str(writer_system_prompt),
        "ARTICLE_WRITER_USER_PROMPT_FILE": str(writer_user_prompt),
        "ARTICLE_CATEGORIES_FILE": str(article_categories),
        "EDITOR_JEFE_SYSTEM_PROMPT_FILE": str(editor_jefe_prompt),
        "EDITORIAL_CONTROL_SYSTEM_PROMPT_FILE": str(editorial_control_prompt),
        "EDITORIAL_CONTROL_RULES_FILE": str(editorial_rules),
    }


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


def test_app_wrapper_reloads_trh_web_app_without_aliasing_sys_modules(monkeypatch, tmp_path):
    first_env = _write_required_prompt_files(tmp_path, "first")
    second_env = _write_required_prompt_files(tmp_path, "second")

    _clear_app_modules()
    for key, value in first_env.items():
        monkeypatch.setenv(key, value)

    first_import = importlib.import_module("app")

    assert first_import.publicador.ARTICLE_WRITER_SYSTEM_PROMPT == "Writer system first"
    assert sys.modules["app"] is sys.modules["trh.web.app"]

    sys.modules.pop("app", None)
    for key, value in second_env.items():
        monkeypatch.setenv(key, value)

    second_import = importlib.import_module("app")

    assert second_import.publicador.ARTICLE_WRITER_SYSTEM_PROMPT == "Writer system second"
    assert second_import is sys.modules["trh.web.app"]


def test_resolve_cluster_publication_state_preserves_generated_content_for_original_cluster(monkeypatch, tmp_path):
    env_vars = _write_required_prompt_files(tmp_path, "cluster")
    _clear_app_modules()
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    web_app = importlib.import_module("trh.web.app")

    state = web_app._resolve_cluster_publication_state(
        {
            "estado_publicacion": "publicado",
            "contenido_ia": {"titulo": "Nota"},
            "foto_principal": "principal.jpg",
            "fotos_secundarias": '["sec1.jpg", "sec2.jpg"]',
        },
        total_noticias=3,
    )

    assert state == {
        "estado_publicacion": "publicado",
        "contenido_ia": {"titulo": "Nota"},
        "foto_principal": "principal.jpg",
        "fotos_secundarias": ["sec1.jpg", "sec2.jpg"],
    }


def test_resolve_cluster_publication_state_resets_generated_content_for_split_target(monkeypatch, tmp_path):
    env_vars = _write_required_prompt_files(tmp_path, "split")
    _clear_app_modules()
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    web_app = importlib.import_module("trh.web.app")

    state = web_app._resolve_cluster_publication_state(
        {
            "estado_publicacion": "generado",
            "contenido_ia": {"titulo": "Viejo"},
            "foto_principal": "principal.jpg",
            "fotos_secundarias": ["sec1.jpg"],
        },
        total_noticias=2,
        reset_generated_content=True,
    )

    assert state == {
        "estado_publicacion": "pendiente",
        "contenido_ia": None,
        "foto_principal": None,
        "fotos_secundarias": [],
    }


def test_split_requires_pending_publication_state_for_generated_and_published_clusters(monkeypatch, tmp_path):
    env_vars = _write_required_prompt_files(tmp_path, "split-state")
    _clear_app_modules()
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    web_app = importlib.import_module("trh.web.app")

    assert web_app._split_requires_pending_publication_state("generando") is True
    assert web_app._split_requires_pending_publication_state("generado") is True
    assert web_app._split_requires_pending_publication_state("publicado") is True


def test_split_allows_pending_publication_state(monkeypatch, tmp_path):
    env_vars = _write_required_prompt_files(tmp_path, "split-pending")
    _clear_app_modules()
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    web_app = importlib.import_module("trh.web.app")

    assert web_app._split_requires_pending_publication_state("pendiente") is False
    assert web_app._split_requires_pending_publication_state(None) is False


@pytest.mark.parametrize(
    ("raw_contenido", "expected_json"),
    [
        ({"titulo": "Nota"}, '{"titulo": "Nota"}'),
        ([{"titulo": "Nota"}], '[{"titulo": "Nota"}]'),
    ],
)
def test_recalcular_cluster_editorial_serializes_python_contenido_ia_before_update(
    monkeypatch,
    tmp_path,
    raw_contenido,
    expected_json,
):
    env_vars = _write_required_prompt_files(tmp_path, "serialize-contenido")
    _clear_app_modules()
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    web_app = importlib.import_module("trh.web.app")

    class Cursor:
        def __init__(self):
            self.statements = []
            self._fetchone_results = iter([
                {
                    "total_noticias": 2,
                    "total_fuentes": 1,
                    "primera": datetime(2026, 3, 7, 9, 0, 0),
                    "ultima": datetime(2026, 3, 7, 11, 0, 0),
                },
                {"titulo": "Cluster recalculado"},
                {
                    "estado_publicacion": "generado",
                    "contenido_ia": raw_contenido,
                    "foto_principal": "principal.jpg",
                    "fotos_secundarias": ["sec1.jpg"],
                },
            ])

        def execute(self, sql, params=None):
            self.statements.append((" ".join(sql.split()), params))

        def fetchone(self):
            return next(self._fetchone_results)

    cur = Cursor()

    web_app.recalcular_cluster_editorial(cur, 7)

    update_sql, update_params = cur.statements[-1]
    assert "UPDATE clusters_editoriales" in update_sql
    assert update_params[8] == expected_json
    assert update_params[10] == '["sec1.jpg"]'
