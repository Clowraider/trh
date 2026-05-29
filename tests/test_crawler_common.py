import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

psycopg2_stub = types.ModuleType("psycopg2")
setattr(psycopg2_stub, "connect", lambda **kwargs: None)
sys.modules.setdefault("psycopg2", psycopg2_stub)

dotenv_stub = types.ModuleType("dotenv")
setattr(dotenv_stub, "load_dotenv", lambda *args, **kwargs: None)
sys.modules.setdefault("dotenv", dotenv_stub)


COMMON_PATH = Path(__file__).resolve().parent.parent / "crawler" / "common.py"
spec = importlib.util.spec_from_file_location("crawler_common", COMMON_PATH)
assert spec is not None and spec.loader is not None
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class TestCrawlerCommon(unittest.TestCase):
    def test_normalize_url_for_storage_removes_tracking(self):
        url = "https://site.com/nota/123?utm_source=x&fbclid=abc&id=99#fragment"
        normalized = common.normalize_url_for_storage(url)
        self.assertEqual(normalized, "https://site.com/nota/123?id=99")

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


if __name__ == "__main__":
    unittest.main()
