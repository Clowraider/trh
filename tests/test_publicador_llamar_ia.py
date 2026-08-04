import json

import pytest

from trh.publication import publicador


def _response(content, status_code=200):
    class Response:
        def __init__(self, content, status_code):
            self._content = content
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise publicador.requests.HTTPError("error")

        def json(self):
            return {"choices": [{"message": {"content": self._content}}]}

    return Response(content, status_code)


def test_llamar_ia_json_accepts_clean_json(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]["model"]))
        return _response('{"titulo":"A","resumen":"B","articulo":"C","categoria":"X"}')

    monkeypatch.setattr(publicador.requests, "post", post)
    result = publicador.llamar_ia_json("prompt", "system")

    assert result["titulo"] == "A"
    assert calls[0][0] == f"{publicador.OPENAI_BASE_URL}/chat/completions"


def test_llamar_ia_json_extracts_json_from_markdown_fence(monkeypatch):
    def post(url, **kwargs):
        return _response('```json\n{"titulo":"A","resumen":"B","articulo":"C","categoria":"X"}\n```')

    monkeypatch.setattr(publicador.requests, "post", post)
    result = publicador.llamar_ia_json("prompt", "system")
    assert result["titulo"] == "A"


def test_llamar_ia_json_extracts_json_with_preamble(monkeypatch):
    def post(url, **kwargs):
        return _response('Aquí va:\n{"titulo":"A","resumen":"B","articulo":"C","categoria":"X"}\nFin.')

    monkeypatch.setattr(publicador.requests, "post", post)
    result = publicador.llamar_ia_json("prompt", "system")
    assert result["titulo"] == "A"


def test_llamar_ia_json_raises_on_malformed_response(monkeypatch, caplog):
    def post(url, **kwargs):
        return _response("no es json")

    monkeypatch.setattr(publicador.requests, "post", post)
    with caplog.at_level("WARNING", logger=publicador.__name__):
        with pytest.raises(Exception, match="El proveedor de IA falló"):
            publicador.llamar_ia_json("prompt", "system")

    assert "La IA no devolvió JSON válido" in caplog.text
    assert "no es json" in caplog.text


def test_llamar_ia_json_detects_truncated_json_response(monkeypatch, caplog):
    def post(url, **kwargs):
        return _response('{"titulo":"A","resumen":"B","articulo":"C"')

    monkeypatch.setattr(publicador.requests, "post", post)
    with caplog.at_level("WARNING", logger=publicador.__name__):
        with pytest.raises(Exception, match="El proveedor de IA falló"):
            publicador.llamar_ia_json("prompt", "system")

    assert "La respuesta de la IA parece estar truncada" in caplog.text


def test_llamar_ia_json_uses_configured_max_tokens(monkeypatch):
    sent_max_tokens = []

    def post(url, **kwargs):
        sent_max_tokens.append(kwargs["json"]["max_tokens"])
        return _response('{"titulo":"A","resumen":"B","articulo":"C","categoria":"X"}')

    monkeypatch.setattr(publicador.requests, "post", post)
    publicador.llamar_ia_json("prompt", "system")
    assert sent_max_tokens[0] == publicador.ARTICLE_WRITER_MAX_TOKENS
    assert sent_max_tokens[0] >= 4000
