import importlib
import json
import logging

import pytest

import prompt_loader


def test_load_prompt_text_returns_file_contents_when_configured(tmp_path):
    prompt_file = tmp_path / "writer.txt"
    prompt_file.write_text("Prompt override\n", encoding="utf-8")

    prompt = prompt_loader.load_prompt_text(
        "TEST_PROMPT_FILE",
        "fallback prompt",
        logger=logging.getLogger("tests.prompt_loader"),
        env={"TEST_PROMPT_FILE": str(prompt_file)},
    )

    assert prompt == "Prompt override\n"


def test_load_prompt_text_logs_warning_and_uses_fallback_on_read_failure(caplog):
    with caplog.at_level(logging.WARNING):
        prompt = prompt_loader.load_prompt_text(
            "TEST_PROMPT_FILE",
            "fallback prompt",
            logger=logging.getLogger("tests.prompt_loader"),
            env={"TEST_PROMPT_FILE": "/tmp/does-not-exist.txt"},
        )

    assert prompt == "fallback prompt"
    assert "Failed to load prompt file" in caplog.text
    assert "TEST_PROMPT_FILE" in caplog.text


def test_load_json_file_returns_validated_contents_when_configured(tmp_path):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(
        json.dumps([{"code": "neutral_tone", "instruction": "Use neutral tone."}]),
        encoding="utf-8",
    )

    rules = prompt_loader.load_json_file(
        "TEST_RULES_FILE",
        [{"code": "fallback", "instruction": "Fallback."}],
        logger=logging.getLogger("tests.prompt_loader"),
        validator=lambda value: value,
        env={"TEST_RULES_FILE": str(rules_file)},
    )

    assert rules == [{"code": "neutral_tone", "instruction": "Use neutral tone."}]


def test_load_json_file_logs_warning_and_uses_fallback_on_invalid_content(
    tmp_path, caplog
):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text("{invalid json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        rules = prompt_loader.load_json_file(
            "TEST_RULES_FILE",
            [{"code": "fallback", "instruction": "Fallback."}],
            logger=logging.getLogger("tests.prompt_loader"),
            validator=lambda value: value,
            env={"TEST_RULES_FILE": str(rules_file)},
        )

    assert rules == [{"code": "fallback", "instruction": "Fallback."}]
    assert "Failed to load JSON file" in caplog.text
    assert "TEST_RULES_FILE" in caplog.text


@pytest.mark.parametrize(
    ("module_name", "env_var", "attribute_name", "override_text"),
    [
        (
            "publicador",
            "ARTICLE_WRITER_SYSTEM_PROMPT_FILE",
            "ARTICLE_WRITER_SYSTEM_PROMPT",
            "Writer system override",
        ),
        (
            "editor_jefe_ia",
            "EDITOR_JEFE_SYSTEM_PROMPT_FILE",
            "EDITOR_JEFE_SYSTEM_PROMPT",
            "Editor jefe override",
        ),
        (
            "editorial_control",
            "EDITORIAL_CONTROL_SYSTEM_PROMPT_FILE",
            "EDITORIAL_CONTROL_SYSTEM_PROMPT",
            "Editorial control override",
        ),
    ],
)
def test_modules_load_prompt_override_from_env_file(
    monkeypatch, tmp_path, module_name, env_var, attribute_name, override_text
):
    prompt_file = tmp_path / f"{module_name}.txt"
    prompt_file.write_text(override_text, encoding="utf-8")
    monkeypatch.setenv(env_var, str(prompt_file))

    module = importlib.import_module(module_name)
    reloaded = importlib.reload(module)

    assert getattr(reloaded, attribute_name) == override_text

    monkeypatch.delenv(env_var, raising=False)
    importlib.reload(reloaded)


def test_editorial_control_loads_rules_override_from_env_file(monkeypatch, tmp_path):
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

    module = importlib.import_module("editorial_control")
    reloaded = importlib.reload(module)

    assert reloaded.EDITORIAL_CONTROL_RULES == [
        {
            "code": "neutral_tone",
            "instruction": "Mantené un tono neutral y factual.",
        }
    ]

    monkeypatch.delenv("EDITORIAL_CONTROL_RULES_FILE", raising=False)
    importlib.reload(reloaded)


def test_editorial_control_uses_fallback_rules_when_rules_file_is_invalid(
    monkeypatch, tmp_path, caplog
):
    rules_file = tmp_path / "editorial_control_rules.json"
    rules_file.write_text(
        json.dumps([{"code": "", "instruction": "Missing code"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("EDITORIAL_CONTROL_RULES_FILE", str(rules_file))

    module = importlib.import_module("editorial_control")
    with caplog.at_level(logging.WARNING):
        reloaded = importlib.reload(module)

    assert reloaded.EDITORIAL_CONTROL_RULES == reloaded.DEFAULT_EDITORIAL_CONTROL_RULES
    assert "Failed to load JSON file" in caplog.text
    assert "EDITORIAL_CONTROL_RULES_FILE" in caplog.text

    monkeypatch.delenv("EDITORIAL_CONTROL_RULES_FILE", raising=False)
    importlib.reload(reloaded)


def test_publicador_uses_user_prompt_template_override(monkeypatch, tmp_path):
    prompt_file = tmp_path / "article_writer_user_prompt.txt"
    prompt_file.write_text(
        "Fuentes:\n$sources_block\n\nNota:\n$editorial_guidance_block",
        encoding="utf-8",
    )
    monkeypatch.setenv("ARTICLE_WRITER_USER_PROMPT_FILE", str(prompt_file))

    publicador = importlib.import_module("publicador")
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

    monkeypatch.delenv("ARTICLE_WRITER_USER_PROMPT_FILE", raising=False)
    importlib.reload(reloaded)
