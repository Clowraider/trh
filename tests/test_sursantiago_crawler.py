import importlib.util
import importlib
import sys
import types
import unittest

if "bs4" in sys.modules:
    del sys.modules["bs4"]

BeautifulSoup = importlib.import_module("bs4").BeautifulSoup


psycopg2_stub = types.ModuleType("psycopg2")
setattr(psycopg2_stub, "connect", lambda **kwargs: None)
sys.modules.setdefault("psycopg2", psycopg2_stub)

psycopg2_extras_stub = types.ModuleType("psycopg2.extras")
setattr(psycopg2_extras_stub, "Json", lambda value: value)
sys.modules.setdefault("psycopg2.extras", psycopg2_extras_stub)

dotenv_stub = types.ModuleType("dotenv")
setattr(dotenv_stub, "load_dotenv", lambda *args, **kwargs: None)
sys.modules.setdefault("dotenv", dotenv_stub)

requests_stub = types.ModuleType("requests")
setattr(requests_stub, "Session", object)
sys.modules.setdefault("requests", requests_stub)


def _load_module(module_name, relative_path):
    spec = importlib.util.spec_from_file_location(module_name, relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common = _load_module("crawler_common", "crawler/common.py")
sys.modules.setdefault("common", common)
sursantiago = _load_module("sursantiago_crawler", "crawler/sursantiago_crawler.py")


class TestSurSantiagoCrawler(unittest.TestCase):
    def test_extraer_contenido_sursantiago_preserves_legitimate_paragraphs_before_promo_block(self):
        soup = BeautifulSoup(
            """
            <article>
              <p>Este es el primer párrafo válido con suficiente contexto para pasar el filtro de longitud sin perder información relevante.</p>
              <h2>Subheading important for the article body</h2>
              <p>Te puede interesar conocer cómo impacta la sequía en la producción local sin que eso convierta este párrafo en promoción.</p>
              <p>Más noticias en nuestras redes sociales y en la portada del sitio.</p>
              <p>Este párrafo no debe aparecer porque viene después del bloque promocional.</p>
            </article>
            """,
            "html.parser",
        )

        extracted = sursantiago.extraer_contenido_sursantiago(soup)

        self.assertEqual(
            extracted,
            "\n".join(
                [
                    "Este es el primer párrafo válido con suficiente contexto para pasar el filtro de longitud sin perder información relevante.",
                    "Subheading important for the article body",
                    "Te puede interesar conocer cómo impacta la sequía en la producción local sin que eso convierta este párrafo en promoción.",
                ]
            ),
        )

    def test_extraer_contenido_sursantiago_stops_when_facebook_promo_paragraph_appears(self):
        soup = BeautifulSoup(
            """
            <article>
              <p>Otro párrafo válido con suficiente longitud para formar parte del cuerpo real de la noticia y no ser descartado.</p>
              <p>Facebook Live con más cobertura, videos y transmisiones especiales para seguir la jornada.</p>
              <p>Este contenido posterior tampoco debe aparecer en el resultado final.</p>
            </article>
            """,
            "html.parser",
        )

        extracted = sursantiago.extraer_contenido_sursantiago(soup)

        self.assertEqual(
            extracted,
            "Otro párrafo válido con suficiente longitud para formar parte del cuerpo real de la noticia y no ser descartado.",
        )


if __name__ == "__main__":
    unittest.main()
