import pytest

from trh.infrastructure.ai_response_parser import extract_json_object


def test_extract_clean_json_object():
    assert extract_json_object('{"selections":[]}') == {"selections": []}


def test_extract_json_from_markdown_fence_with_label():
    raw = '```json\n{"titulo":"Hola","resumen":"Mundo"}\n```'
    assert extract_json_object(raw) == {"titulo": "Hola", "resumen": "Mundo"}


def test_extract_json_from_markdown_fence_without_label():
    raw = '```\n{"selections":[{"cluster_id":1,"reason":"ok"}]}\n```'
    assert extract_json_object(raw) == {"selections": [{"cluster_id": 1, "reason": "ok"}]}


def test_extract_json_with_preamble_and_postamble():
    raw = 'Claro, aquí tienes:\n{"titulo":"A","resumen":"B","articulo":"C"}\nEspero que sirva.'
    assert extract_json_object(raw) == {
        "titulo": "A", "resumen": "B", "articulo": "C"
    }


def test_extract_respects_strings_and_escapes():
    raw = '{"articulo":"texto con { y \\" comillas"}'
    assert extract_json_object(raw) == {"articulo": 'texto con { y " comillas'}


def test_extract_fails_when_no_json_object():
    with pytest.raises(ValueError):
        extract_json_object("no es json")


def test_extract_fails_for_non_string():
    with pytest.raises(ValueError):
        extract_json_object(None)
