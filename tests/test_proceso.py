import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import proceso


class TestProcesoDiscovery(unittest.TestCase):
    def test_discovers_crawler_scripts_sorted_and_excludes_template(self):
        """Descubre *_crawler.py, ordena alfabéticamente y excluye la plantilla."""
        scripts = proceso.discover_crawler_scripts()

        # La plantilla nunca debe aparecer como crawler ejecutable.
        self.assertNotIn("crawler/sites/plantilla_crawler.py", scripts)

        # Los paths deben ser relativos a la raíz del proyecto y estar ordenados.
        self.assertEqual(scripts, sorted(scripts))
        for script in scripts:
            self.assertTrue(script.startswith("crawler/sites/"))
            self.assertTrue(script.endswith("_crawler.py"))

    def test_discovers_only_crawler_suffix_in_custom_directory(self):
        """En un directorio temporal solo descubre archivos *_crawler.py."""
        with TemporaryDirectory() as tmp:
            sites_dir = Path(tmp) / "sites"
            sites_dir.mkdir()

            (sites_dir / "foo_crawler.py").write_text("# foo")
            (sites_dir / "bar_crawler.py").write_text("# bar")
            (sites_dir / "plantilla_crawler.py").write_text("# plantilla")
            (sites_dir / "not_a_crawler_helper.py").write_text("# ignored")
            (sites_dir / "helper.py").write_text("# ignored")

            # Pasamos sites_dir como base_dir para que relative_to() devuelva solo el nombre.
            scripts = proceso.discover_crawler_scripts(sites_dir=sites_dir, base_dir=sites_dir)

        self.assertEqual(scripts, ["bar_crawler.py", "foo_crawler.py"])

    def test_returns_empty_list_when_directory_is_empty(self):
        """No falla si no hay crawlers: simplemente devuelve lista vacía."""
        with TemporaryDirectory() as tmp:
            scripts = proceso.discover_crawler_scripts(sites_dir=Path(tmp))
        self.assertEqual(scripts, [])


if __name__ == "__main__":
    unittest.main()
