import importlib.util
import inspect
import re
import sys
import types
import unittest
from contextlib import contextmanager
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch


PLANTILLA_PATH = Path(__file__).resolve().parents[1] / "crawler" / "sites" / "plantilla_crawler.py"
COMMON_PATH = Path(__file__).resolve().parents[1] / "crawler" / "common.py"


# Stubs para las dependencias externas, igual que en test_crawler_common.py.
psycopg2_stub = types.ModuleType("psycopg2")
setattr(psycopg2_stub, "connect", lambda **kwargs: None)

psycopg2_extras_stub = types.ModuleType("psycopg2.extras")
setattr(psycopg2_extras_stub, "Json", lambda value: value)

dotenv_stub = types.ModuleType("dotenv")
setattr(dotenv_stub, "load_dotenv", lambda *args, **kwargs: None)

requests_stub = types.ModuleType("requests")
setattr(requests_stub, "Session", object)

# bs4: stub mínimo que soporta lo que html_a_texto() necesita.
bs4_stub = types.ModuleType("bs4")


class _StubElement:
    def __init__(self, tag, text="", children=None):
        self.tag = tag
        self._text = text
        self.children = children or []
        self.decomposed = False

    def decompose(self):
        self.decomposed = True

    def replace_with(self, text):
        self._text = text
        self.children = []

    def find_all(self, tag):
        result = []
        if self.tag == tag:
            result.append(self)
        for child in self.children:
            result.extend(child.find_all(tag))
        return result

    def get_text(self, separator="", strip=False):
        if self.decomposed:
            return ""
        pieces = []
        if self._text:
            pieces.append(self._text)
        for child in self.children:
            if not child.decomposed:
                pieces.append(child.get_text(separator, strip))
        text = separator.join(pieces)
        if strip:
            text = text.strip()
        return text


class _BeautifulSoupStub:
    def __init__(self, html_content, parser=None):
        self._root = self._parse(html_content)

    def _parse(self, html_content):
        # Parser mínimo: solo reconoce <p>, <br> y las etiquetas que html_a_texto
        # elimina. No es robusto, pero alcanza para el test.
        tags = ["script", "style", "iframe", "button", "aside", "nav", "p", "br"]
        pattern = re.compile(r"<\s*(/?)\s*([a-zA-Z0-9]+)\b[^>]*>", re.IGNORECASE)
        root = _StubElement("root", "")
        current = root
        stack = [root]
        last_end = 0

        for match in pattern.finditer(html_content):
            text_before = html_content[last_end:match.start()]
            if text_before:
                current.children.append(_StubElement("text", text_before))

            is_closing = match.group(1) == "/"
            tag = match.group(2).lower()

            if is_closing:
                if stack and stack[-1].tag == tag:
                    stack.pop()
                    current = stack[-1] if stack else root
            elif tag in tags:
                new_elem = _StubElement(tag)
                current.children.append(new_elem)
                if tag not in ("br",):
                    stack.append(current)
                    current = new_elem
            else:
                # etiqueta desconocida: solo texto
                current.children.append(_StubElement("text", ""))

            last_end = match.end()

        text_after = html_content[last_end:]
        if text_after:
            current.children.append(_StubElement("text", text_after))

        return root

    def find_all(self, tag):
        return self._root.find_all(tag)

    def get_text(self, separator="", strip=False):
        return self._root.get_text(separator, strip)


setattr(bs4_stub, "BeautifulSoup", _BeautifulSoupStub)

lxml_stub = types.ModuleType("lxml")
lhtml_stub = types.ModuleType("lxml.html")
setattr(lxml_stub, "html", lhtml_stub)
setattr(lhtml_stub, "HtmlElement", type("HtmlElement", (), {}))
setattr(lhtml_stub, "fromstring", lambda html: None)
setattr(lhtml_stub, "tostring", lambda *args, **kwargs: "")


@contextmanager
def _patched_imports(*, include_common=False):
    common = sys.modules.get("common")
    patched_modules = {
        "psycopg2": psycopg2_stub,
        "psycopg2.extras": psycopg2_extras_stub,
        "dotenv": dotenv_stub,
        "requests": requests_stub,
        "bs4": bs4_stub,
        "lxml": lxml_stub,
        "lxml.html": lhtml_stub,
    }
    if include_common:
        patched_modules["common"] = common
    with patch.dict(sys.modules, patched_modules):
        yield


def _load_module(module_name, module_path, *, include_common=False):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with _patched_imports(include_common=include_common):
        spec.loader.exec_module(module)
    return module


class _StubConnection:
    """Connection que falla si se usa, para detectar accesos a DB en modo test."""

    def cursor(self):
        raise AssertionError("No debe llamarse a la base de datos en modo test")

    def commit(self):
        raise AssertionError("No debe llamarse a la base de datos en modo test")

    def close(self):
        pass


class TestPlantillaCrawler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.common = _load_module("crawler_common", COMMON_PATH)
        sys.modules.setdefault("common", cls.common)
        cls.plantilla = _load_module("plantilla_crawler", PLANTILLA_PATH, include_common=True)

    def test_module_has_required_public_interface(self):
        """El crawler plantilla expone todo lo que run_crawler_template necesita."""
        required = {
            "BASE_URL",
            "FUENTE",
            "TEST_URL",
            "TEST_MODE",
            "MAX_URLS_POR_TANDA",
            "MAX_NOTICIAS_POR_EJECUCION",
            "DELAY",
            "procesar_pagina",
            "guardar_noticia",
            "main",
        }
        for name in required:
            self.assertTrue(
                hasattr(self.plantilla, name),
                f"Falta atributo/función requerido: {name}",
            )

    def test_procesar_pagina_signature_compatible_with_template(self):
        """La firma de procesar_pagina debe coincidir con lo que espera run_crawler_template."""
        signature = inspect.signature(self.plantilla.procesar_pagina)
        self.assertIn("extraer_links", signature.parameters)
        self.assertTrue(signature.parameters["extraer_links"].default)
        self.assertIn("extraer_noticia", signature.parameters)
        self.assertIn("importancia_links", signature.parameters)

    def test_guardar_noticia_in_test_mode_does_not_touch_db(self):
        """En TEST_MODE=True guardar_noticia debe imprimir y no usar la DB."""
        original_test_mode = self.plantilla.TEST_MODE
        try:
            self.plantilla.TEST_MODE = True

            captured = StringIO()
            with (
                patch.object(self.plantilla, "get_connection", return_value=_StubConnection()),
                patch("sys.stdout", new=captured),
            ):
                result = self.plantilla.guardar_noticia(
                    url="https://www.lanacion.com.ar/politica/noticia-de-prueba/",
                    titulo="Título de prueba para el crawler plantilla",
                    fecha_pub=datetime(2026, 7, 27, 14, 30),
                    texto="Este es el cuerpo de la noticia. " * 50,
                    imagen="https://www.lanacion.com.ar/img.jpg",
                )

            self.assertTrue(result)
            output = captured.getvalue()
            self.assertIn("MODO TEST", output)
            self.assertIn("Título de prueba", output)
            self.assertIn("https://www.lanacion.com.ar/politica/noticia-de-prueba", output)
        finally:
            self.plantilla.TEST_MODE = original_test_mode

    def test_guardar_noticia_rejects_short_text(self):
        """Sin texto suficiente no debe considerarse una noticia válida."""
        result = self.plantilla.guardar_noticia(
            url="https://www.lanacion.com.ar/politica/noticia-corta/",
            titulo="Título corto",
            fecha_pub=None,
            texto="Texto muy corto.",
            imagen=None,
        )
        self.assertFalse(result)

    def test_html_a_texto_converts_html_to_plaintext(self):
        """La utilidad de limpieza de HTML debe preservar párrafos y quitar tags."""
        html = "<p>Primer párrafo.</p><br><p>Segundo párrafo.</p>"
        texto = self.plantilla.html_a_texto(html)
        self.assertIn("Primer párrafo.", texto)
        self.assertIn("Segundo párrafo.", texto)
        self.assertNotIn("<p>", texto)

    def test_generar_hash_contenido_is_deterministic(self):
        """El hash debe ser estable para detectar duplicados."""
        h1 = self.plantilla.generar_hash_contenido("Título", "Texto de la noticia")
        h2 = self.plantilla.generar_hash_contenido("Título", "Texto de la noticia")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_clean_url_removes_fragments_and_trailing_slash(self):
        """clean_url quita fragmentos y barra final; las queries las deja para save_url."""
        url = self.plantilla.clean_url(
            "https://www.lanacion.com.ar/politica/noticia/?utm_source=x#comentarios"
        )
        self.assertEqual(url, "https://www.lanacion.com.ar/politica/noticia/?utm_source=x")


if __name__ == "__main__":
    unittest.main()
