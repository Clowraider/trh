import importlib.util
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

psycopg2_stub = types.ModuleType("psycopg2")
setattr(psycopg2_stub, "connect", lambda **kwargs: None)
sys.modules.setdefault("psycopg2", psycopg2_stub)

psycopg2_extras_stub = types.ModuleType("psycopg2.extras")


def _json_passthrough(value):
    return value


setattr(psycopg2_extras_stub, "Json", _json_passthrough)
sys.modules.setdefault("psycopg2.extras", psycopg2_extras_stub)

dotenv_stub = types.ModuleType("dotenv")
setattr(dotenv_stub, "load_dotenv", lambda *args, **kwargs: None)
sys.modules.setdefault("dotenv", dotenv_stub)


COMMON_PATH = Path(__file__).resolve().parent.parent / "crawler" / "common.py"
spec = importlib.util.spec_from_file_location("crawler_common", COMMON_PATH)
assert spec is not None and spec.loader is not None
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
sys.modules.setdefault("common", common)


class RecordingCursor:
    def __init__(self):
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return None

    def close(self):
        pass


class RecordingConnection:
    def __init__(self):
        self.cursor_instance = RecordingCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def close(self):
        pass


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class TestCrawlerCommon(unittest.TestCase):
    def test_normalize_text_for_storage_strips_tags_and_empty_lines(self):
        raw = "  <p>Hello   <strong>world</strong></p>\n\n<div>Line   two</div><br>  <em>Line three</em>  "

        normalized = common.normalize_text_for_storage(raw)

        self.assertEqual(normalized, "Hello world\nLine two\nLine three")

    def test_normalize_title_for_storage_collapses_whitespace_and_tags(self):
        raw = "  <strong> Breaking   news </strong>\n  today  "

        normalized = common.normalize_title_for_storage(raw)

        self.assertEqual(normalized, "Breaking news today")

    def test_normalize_image_url_for_storage_preserves_query_and_fragment(self):
        raw = "  https://site.com/image.jpg?utm_source=x#fragment  "

        normalized = common.normalize_image_url_for_storage(raw)

        self.assertEqual(normalized, "https://site.com/image.jpg?utm_source=x#fragment")

    def test_normalize_fecha_publicacion_removes_timezone_and_subminute_precision(self):
        fecha = datetime(2026, 5, 29, 12, 30, 45, 123456, tzinfo=timezone.utc)

        normalized = common.normalize_fecha_publicacion(fecha)

        self.assertEqual(normalized, datetime(2026, 5, 29, 12, 30))

    def test_normalize_url_for_storage_removes_query_and_fragment(self):
        url = "https://site.com/nota/123?utm_source=x&fbclid=abc&id=99#fragment"
        normalized = common.normalize_url_for_storage(url)
        self.assertEqual(normalized, "https://site.com/nota/123")

    def test_normalize_url_for_storage_removes_fragment_without_query(self):
        url = "https://site.com/nota/123/#fragment"
        normalized = common.normalize_url_for_storage(url)
        self.assertEqual(normalized, "https://site.com/nota/123")

    def test_build_quality_flags_has_expected_shape(self):
        flags = common.build_quality_flags(
            url="https://site.com/nota/1",
            titulo="Titulo suficientemente largo",
            texto="a" * 350,
            fecha=common.datetime(2026, 5, 29, 12, 30),
            imagen="https://img.com/a.jpg",
        )
        quality = flags["quality"]
        self.assertTrue(quality["titulo_ok"])
        self.assertTrue(quality["texto_ok"])
        self.assertTrue(quality["fecha_ok"])
        self.assertTrue(quality["imagen_ok"])
        self.assertTrue(quality["url_limpia_ok"])

    def test_build_random_headers_uses_shared_user_agents(self):
        with patch.object(common.random, "choice", return_value="selected-agent") as choice_mock:
            headers = common.build_random_headers()

        choice_mock.assert_called_once_with(common.USER_AGENTS)
        self.assertEqual(headers["User-Agent"], "selected-agent")
        self.assertEqual(headers["Accept-Language"], "es-ES,es;q=0.9")

    def test_build_random_headers_allows_accept_language_override(self):
        with patch.object(common.random, "choice", return_value=common.USER_AGENTS[0]):
            headers = common.build_random_headers("es-AR,es;q=0.9")

        self.assertEqual(headers["Accept-Language"], "es-AR,es;q=0.9")

    def test_run_crawler_template_limits_to_100(self):
        source = "Test Source"
        calls = {"processed": 0, "marked": 0}

        def fake_process_page(url, importancia_links, extraer_noticia):
            if not extraer_noticia:
                return True, False
            calls["processed"] += 1
            return True, True

        def fake_pending(_fuente, _max_tanda, faltan):
            # Siempre devolver más que faltan para forzar corte por cupo
            return [(i, f"https://site.com/{i}") for i in range(1, min(30, faltan) + 1)]

        def fake_mark(_url_id, _success):
            calls["marked"] += 1

        with patch.object(common, "_obtener_pendientes_priorizados", side_effect=fake_pending), \
             patch.object(common, "_marcar_url_procesada", side_effect=fake_mark), \
             patch.object(common.time, "sleep", return_value=None), \
             patch.object(common.random, "uniform", return_value=0):
            common.run_crawler_template(
                fuente=source,
                base_url="https://site.com",
                process_page=fake_process_page,
                max_urls_por_tanda=30,
                max_noticias_por_ejecucion=100,
                delay_base=0,
                delay_random_min=0,
                delay_random_max=0,
                logger=DummyLogger(),
            )

        self.assertEqual(calls["processed"], 100)
        self.assertEqual(calls["marked"], 100)

    def test_run_crawler_template_prioritizes_alta_then_baja(self):
        seen = []

        def fake_process_page(url, importancia_links, extraer_noticia):
            if extraer_noticia:
                seen.append(url)
            return True, bool(extraer_noticia)

        counter = {"calls": 0}

        def fake_pending(_fuente, _max_tanda, _faltan):
            # Primera llamada: lote alta (simulado por nombres)
            counter["calls"] += 1
            if counter["calls"] == 1:
                return [(1, "alta-1"), (2, "alta-2")]
            if counter["calls"] == 2:
                return [(3, "baja-1")]
            return []

        with patch.object(common, "_obtener_pendientes_priorizados", side_effect=fake_pending), \
             patch.object(common, "_marcar_url_procesada", return_value=None), \
             patch.object(common.time, "sleep", return_value=None), \
             patch.object(common.random, "uniform", return_value=0):
            common.run_crawler_template(
                fuente="Test",
                base_url="https://site.com",
                process_page=fake_process_page,
                max_urls_por_tanda=30,
                max_noticias_por_ejecucion=10,
                delay_base=0,
                delay_random_min=0,
                delay_random_max=0,
                logger=DummyLogger(),
            )

        self.assertEqual(seen, ["alta-1", "alta-2", "baja-1"])

    def test_guardar_noticia_normalizes_fields_before_insert_for_all_crawlers(self):
        crawler_files = [
            "elliberal_crawler.py",
            "nuevodiario_crawler.py",
            "panorama_crawler.py",
            "sursantiago_crawler.py",
            "termasdigital_crawler.py",
        ]
        expected_text = "First paragraph\nSecond paragraph\n" + " ".join(["extra"] * 80)

        for crawler_file in crawler_files:
            with self.subTest(crawler_file=crawler_file):
                module_path = Path(__file__).resolve().parent.parent / "crawler" / crawler_file
                spec = importlib.util.spec_from_file_location(crawler_file.replace(".py", ""), module_path)
                assert spec is not None and spec.loader is not None
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                connection = RecordingConnection()

                with patch.object(module, "get_connection", return_value=connection), \
                     patch.object(module, "build_quality_flags", return_value={"quality": {}}), \
                     patch.object(module.logger, "info"), \
                     patch.object(module.logger, "warning"):
                    saved = module.guardar_noticia(
                        " https://site.com/article?utm_source=x#fragment ",
                        "  <strong> Breaking   title </strong>  ",
                        datetime(2026, 5, 29, 12, 30, 45, 111111, tzinfo=timezone.utc),
                        "<p> First   paragraph </p>\n\n<p> Second <em> paragraph </em> </p>" + " extra" * 80,
                        " https://site.com/image.jpg?foo=1#frag ",
                    )

                self.assertTrue(saved)
                self.assertTrue(connection.committed)

                insert_query, insert_params = connection.cursor_instance.executed[-1]
                self.assertIn("INSERT INTO noticias_historico", insert_query)
                self.assertEqual(insert_params[3], "https://site.com/article")
                self.assertEqual(insert_params[4], "Breaking title")
                self.assertEqual(insert_params[5], expected_text)
                self.assertEqual(insert_params[6], "https://site.com/image.jpg?foo=1#frag")
                self.assertEqual(insert_params[7], datetime(2026, 5, 29, 12, 30))


if __name__ == "__main__":
    unittest.main()
