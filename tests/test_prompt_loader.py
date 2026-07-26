import importlib
import json
import logging
import os
import sys

import pytest

from trh.infrastructure import env_loader, prompt_loader


def test_load_prompt_text_returns_file_contents_when_configured(tmp_path):
    prompt_file = tmp_path / "writer.txt"
    prompt_file.write_text("Prompt override\n", encoding="utf-8")

    prompt = prompt_loader.load_prompt_text(
        "TEST_PROMPT_FILE",
        logger=logging.getLogger("tests.prompt_loader"),
        env={"TEST_PROMPT_FILE": str(prompt_file)},
    )

    assert prompt == "Prompt override\n"


def test_load_prompt_text_requires_configured_env_var():
    with pytest.raises(RuntimeError, match="TEST_PROMPT_FILE"):
        prompt_loader.load_prompt_text(
            "TEST_PROMPT_FILE",
            logger=logging.getLogger("tests.prompt_loader"),
            env={},
        )


def test_load_prompt_text_fails_on_read_error():
    with pytest.raises(RuntimeError, match="TEST_PROMPT_FILE") as excinfo:
        prompt_loader.load_prompt_text(
            "TEST_PROMPT_FILE",
            logger=logging.getLogger("tests.prompt_loader"),
            env={"TEST_PROMPT_FILE": "/tmp/does-not-exist.txt"},
        )

    assert "does not exist" in str(excinfo.value)


def test_load_prompt_text_resolves_relative_paths_from_project_root(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    prompt_file = prompt_dir / "writer.txt"
    prompt_file.write_text("Prompt override\n", encoding="utf-8")

    monkeypatch.setattr(prompt_loader, "PROJECT_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path / "prompts")

    prompt = prompt_loader.load_prompt_text(
        "TEST_PROMPT_FILE",
        logger=logging.getLogger("tests.prompt_loader"),
        env={"TEST_PROMPT_FILE": "prompts/writer.txt"},
    )

    assert prompt == "Prompt override\n"


def test_load_json_file_returns_validated_contents_when_configured(tmp_path):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(
        json.dumps([{"code": "neutral_tone", "instruction": "Use neutral tone."}]),
        encoding="utf-8",
    )

    rules = prompt_loader.load_json_file(
        "TEST_RULES_FILE",
        logger=logging.getLogger("tests.prompt_loader"),
        validator=lambda value: value,
        env={"TEST_RULES_FILE": str(rules_file)},
    )

    assert rules == [{"code": "neutral_tone", "instruction": "Use neutral tone."}]


def test_load_json_file_requires_configured_env_var():
    with pytest.raises(RuntimeError, match="TEST_RULES_FILE"):
        prompt_loader.load_json_file(
            "TEST_RULES_FILE",
            logger=logging.getLogger("tests.prompt_loader"),
            validator=lambda value: value,
            env={},
        )


def test_load_json_file_fails_on_invalid_json(tmp_path):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(RuntimeError, match="TEST_RULES_FILE") as excinfo:
        prompt_loader.load_json_file(
            "TEST_RULES_FILE",
            logger=logging.getLogger("tests.prompt_loader"),
            validator=lambda value: value,
            env={"TEST_RULES_FILE": str(rules_file)},
        )

    assert "invalid JSON" in str(excinfo.value)


def test_load_json_file_resolves_relative_paths_from_project_root(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    rules_file = prompt_dir / "rules.json"
    rules_file.write_text(json.dumps({"ok": True}), encoding="utf-8")

    monkeypatch.setattr(prompt_loader, "PROJECT_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path / "prompts")

    rules = prompt_loader.load_json_file(
        "TEST_RULES_FILE",
        logger=logging.getLogger("tests.prompt_loader"),
        validator=lambda value: value,
        env={"TEST_RULES_FILE": "prompts/rules.json"},
    )

    assert rules == {"ok": True}


@pytest.mark.parametrize(
    ("module_name", "env_var", "attribute_name", "override_text"),
    [
        (
            "trh.publication.publicador",
            "ARTICLE_WRITER_SYSTEM_PROMPT_FILE",
            "ARTICLE_WRITER_SYSTEM_PROMPT",
            "Writer system override",
        ),
        (
            "trh.editorial.editor_jefe_ia",
            "EDITOR_JEFE_SYSTEM_PROMPT_FILE",
            "EDITOR_JEFE_SYSTEM_PROMPT",
            "Editor jefe override",
        ),
        (
            "trh.editorial.editorial_control",
            "EDITORIAL_CONTROL_SYSTEM_PROMPT_FILE",
            "EDITORIAL_CONTROL_SYSTEM_PROMPT",
            "Editorial control override",
        ),
    ],
)
def test_modules_load_prompt_override_from_env_file(
    monkeypatch, tmp_path, module_name, env_var, attribute_name, override_text
):
    original_value = os.environ.get(env_var)
    prompt_file = tmp_path / f"{module_name}.txt"
    prompt_file.write_text(override_text, encoding="utf-8")
    monkeypatch.setenv(env_var, str(prompt_file))

    module = importlib.import_module(module_name)
    try:
        reloaded = importlib.reload(module)

        assert getattr(reloaded, attribute_name) == override_text
    finally:
        if original_value is None:
            monkeypatch.delenv(env_var, raising=False)
        else:
            monkeypatch.setenv(env_var, original_value)
        importlib.reload(module)


def test_editorial_control_loads_rules_override_from_env_file(monkeypatch, tmp_path):
    original_value = os.environ.get("EDITORIAL_CONTROL_RULES_FILE")
    rules_file = tmp_path / "editorial_control_rules.json"
    rules_file.write_text(
        json.dumps(
            [
                {
                    "code": "neutral_tone",
                    "instruction": "Mantené un tono neutral y factual.",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EDITORIAL_CONTROL_RULES_FILE", str(rules_file))

    module = importlib.import_module("trh.editorial.editorial_control")
    try:
        reloaded = importlib.reload(module)

        assert reloaded.EDITORIAL_CONTROL_RULES == [
            {
                "code": "neutral_tone",
                "instruction": "Mantené un tono neutral y factual.",
            }
        ]
    finally:
        if original_value is None:
            monkeypatch.delenv("EDITORIAL_CONTROL_RULES_FILE", raising=False)
        else:
            monkeypatch.setenv("EDITORIAL_CONTROL_RULES_FILE", original_value)
        importlib.reload(module)


def test_editorial_control_fails_when_rules_file_is_invalid(monkeypatch, tmp_path):
    original_value = os.environ.get("EDITORIAL_CONTROL_RULES_FILE")
    rules_file = tmp_path / "editorial_control_rules.json"
    rules_file.write_text(
        json.dumps([{"code": "", "instruction": "Missing code"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("EDITORIAL_CONTROL_RULES_FILE", str(rules_file))

    module = importlib.import_module("trh.editorial.editorial_control")
    try:
        with pytest.raises(RuntimeError, match="EDITORIAL_CONTROL_RULES_FILE") as excinfo:
            importlib.reload(module)

        assert "invalid value" in str(excinfo.value)
    finally:
        if original_value is None:
            monkeypatch.delenv("EDITORIAL_CONTROL_RULES_FILE", raising=False)
        else:
            monkeypatch.setenv("EDITORIAL_CONTROL_RULES_FILE", original_value)
        importlib.reload(module)


def test_publicador_uses_user_prompt_template_override(monkeypatch, tmp_path):
    original_value = os.environ.get("ARTICLE_WRITER_USER_PROMPT_FILE")
    prompt_file = tmp_path / "article_writer_user_prompt.txt"
    prompt_file.write_text(
        "Fuentes:\n$sources_block\n\nNota:\n$editorial_guidance_block",
        encoding="utf-8",
    )
    monkeypatch.setenv("ARTICLE_WRITER_USER_PROMPT_FILE", str(prompt_file))

    publicador = importlib.import_module("trh.publication.publicador")
    try:
        reloaded = importlib.reload(publicador)

        prompt = reloaded.construir_prompt(
            [
                {
                    "fuente": "Fuente Test",
                    "titulo": "Título Test",
                    "fecha_publicacion": None,
                    "texto_completo": "Texto base",
                }
            ],
            nota_ia="Seguí esta guía.",
        )

        assert "Fuentes:" in prompt
        assert "FUENTE 1: Fuente Test" in prompt
        assert "CONTENIDO: Texto base..." in prompt
        assert "Seguí esta guía." in prompt
    finally:
        if original_value is None:
            monkeypatch.delenv("ARTICLE_WRITER_USER_PROMPT_FILE", raising=False)
        else:
            monkeypatch.setenv("ARTICLE_WRITER_USER_PROMPT_FILE", original_value)
        importlib.reload(publicador)


@pytest.mark.parametrize(
    ("template_text", "missing_placeholder"),
    [
        ("Fuentes:\n$editorial_guidance_block", "sources_block"),
        ("Fuentes:\n$sources_block", "editorial_guidance_block"),
    ],
)
def test_publicador_fails_when_user_prompt_template_misses_required_placeholders(
    monkeypatch, tmp_path, template_text, missing_placeholder
):
    original_value = os.environ.get("ARTICLE_WRITER_USER_PROMPT_FILE")
    prompt_file = tmp_path / "article_writer_user_prompt.txt"
    prompt_file.write_text(template_text, encoding="utf-8")
    monkeypatch.setenv("ARTICLE_WRITER_USER_PROMPT_FILE", str(prompt_file))

    publicador = importlib.import_module("trh.publication.publicador")
    try:
        with pytest.raises(RuntimeError, match=missing_placeholder):
            importlib.reload(publicador)
    finally:
        if original_value is None:
            monkeypatch.delenv("ARTICLE_WRITER_USER_PROMPT_FILE", raising=False)
        else:
            monkeypatch.setenv("ARTICLE_WRITER_USER_PROMPT_FILE", original_value)
        importlib.reload(publicador)


def test_module_import_fails_when_required_prompt_env_var_is_missing(monkeypatch):
    original_value = os.environ.get("EDITOR_JEFE_SYSTEM_PROMPT_FILE")
    monkeypatch.delenv("EDITOR_JEFE_SYSTEM_PROMPT_FILE", raising=False)

    module = importlib.import_module("trh.editorial.editor_jefe_ia")
    try:
        with pytest.raises(RuntimeError, match="EDITOR_JEFE_SYSTEM_PROMPT_FILE"):
            importlib.reload(module)
    finally:
        if original_value is None:
            monkeypatch.delenv("EDITOR_JEFE_SYSTEM_PROMPT_FILE", raising=False)
        else:
            monkeypatch.setenv("EDITOR_JEFE_SYSTEM_PROMPT_FILE", original_value)
        importlib.reload(module)


def test_app_import_loads_required_prompt_env_from_dotenv_before_module_imports(
    monkeypatch, tmp_path
):
    writer_system_prompt = tmp_path / "article_writer_system_prompt.txt"
    writer_system_prompt.write_text("Writer system override", encoding="utf-8")
    writer_user_prompt = tmp_path / "article_writer_user_prompt.txt"
    writer_user_prompt.write_text(
        "Fuentes:\n$sources_block\n\nNota:\n$editorial_guidance_block",
        encoding="utf-8",
    )
    editor_jefe_prompt = tmp_path / "editor_jefe_system_prompt.txt"
    editor_jefe_prompt.write_text("Editor jefe override", encoding="utf-8")
    editorial_control_prompt = tmp_path / "editorial_control_system_prompt.txt"
    editorial_control_prompt.write_text(
        "Editorial control override", encoding="utf-8"
    )
    editorial_rules = tmp_path / "editorial_control_rules.json"
    editorial_rules.write_text(
        json.dumps(
            [{"code": "neutral_tone", "instruction": "Use neutral tone."}]
        ),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                f"ARTICLE_WRITER_SYSTEM_PROMPT_FILE={writer_system_prompt}",
                f"ARTICLE_WRITER_USER_PROMPT_FILE={writer_user_prompt}",
                f"EDITOR_JEFE_SYSTEM_PROMPT_FILE={editor_jefe_prompt}",
                f"EDITORIAL_CONTROL_SYSTEM_PROMPT_FILE={editorial_control_prompt}",
                f"EDITORIAL_CONTROL_RULES_FILE={editorial_rules}",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(env_loader, "DEFAULT_ENV_PATH", tmp_path / ".env")
    for env_var in (
        "ARTICLE_WRITER_SYSTEM_PROMPT_FILE",
        "ARTICLE_WRITER_USER_PROMPT_FILE",
        "EDITOR_JEFE_SYSTEM_PROMPT_FILE",
        "EDITORIAL_CONTROL_SYSTEM_PROMPT_FILE",
        "EDITORIAL_CONTROL_RULES_FILE",
    ):
        monkeypatch.delenv(env_var, raising=False)

    original_modules = {}
    for module_name in (
        "app",
        "trh.publication.publicador",
        "trh.publication.publicapress",
        "trh.publication",
        "trh.editorial.editorial_control",
        "trh.editorial.editor_jefe_ia",
        "trh.editorial",
        "pipeline.seleccionar_publicables",
    ):
        original_modules[module_name] = sys.modules.pop(module_name, None)

    try:
        panel = importlib.import_module("app")

        assert panel.publicador.ARTICLE_WRITER_SYSTEM_PROMPT == "Writer system override"
        assert (
            panel.publicador.ARTICLE_WRITER_USER_PROMPT_TEMPLATE
            == "Fuentes:\n$sources_block\n\nNota:\n$editorial_guidance_block"
        )
        assert sys.modules["trh.editorial.editor_jefe_ia"].EDITOR_JEFE_SYSTEM_PROMPT == (
            "Editor jefe override"
        )
        assert sys.modules["trh.editorial.editorial_control"].EDITORIAL_CONTROL_SYSTEM_PROMPT == (
            "Editorial control override"
        )
        assert sys.modules["trh.editorial.editorial_control"].EDITORIAL_CONTROL_RULES == [
            {"code": "neutral_tone", "instruction": "Use neutral tone."}
        ]
    finally:
        for module_name in (
            "app",
            "trh.publication.publicador",
            "trh.publication.publicapress",
            "trh.publication",
            "trh.editorial.editorial_control",
            "trh.editorial.editor_jefe_ia",
            "trh.editorial",
            "pipeline.seleccionar_publicables",
        ):
            sys.modules.pop(module_name, None)
        for module_name, module in original_modules.items():
            if module is not None:
                sys.modules[module_name] = module
