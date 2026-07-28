import os
import unittest
import unittest.mock
from pathlib import Path
from tempfile import TemporaryDirectory

import proceso


class TestProcesoLockPaths(unittest.TestCase):
    def test_lock_paths_use_project_internal_directory_by_default(self):
        """Los locks deben estar en un directorio interno, no en /tmp."""
        env_backup = os.environ.get("TRH_LOCK_DIR")
        os.environ.pop("TRH_LOCK_DIR", None)
        try:
            import importlib

            importlib.reload(proceso)
            self.assertNotEqual(proceso.LOCK_DIR, Path("/tmp"))
            self.assertTrue(
                str(proceso.LOCK_DIR).endswith(".trh/locks")
                or str(proceso.LOCK_DIR).endswith(".trh\\locks")
            )
        finally:
            if env_backup is None:
                os.environ.pop("TRH_LOCK_DIR", None)
            else:
                os.environ["TRH_LOCK_DIR"] = env_backup
            importlib.reload(proceso)

    def test_lock_paths_respect_trh_lock_dir_env_variable(self):
        """TRH_LOCK_DIR permite sobreescribir la ubicación de los locks."""
        with TemporaryDirectory() as tmp:
            expected = Path(tmp) / "custom_locks"
            env_backup = os.environ.get("TRH_LOCK_DIR")
            os.environ["TRH_LOCK_DIR"] = str(expected)
            try:
                # Recargamos el módulo para que tome la nueva variable de entorno.
                import importlib

                importlib.reload(proceso)
                self.assertEqual(proceso.LOCK_DIR, expected)
                self.assertEqual(proceso.RUN_LOCK_PATH, expected / "trh_proceso_run.lock")
                self.assertEqual(proceso.QUEUE_LOCK_PATH, expected / "trh_proceso_queue.lock")
            finally:
                if env_backup is None:
                    os.environ.pop("TRH_LOCK_DIR", None)
                else:
                    os.environ["TRH_LOCK_DIR"] = env_backup
                importlib.reload(proceso)

    def test_main_creates_lock_directory_and_files(self):
        """main() crea el directorio de locks y los archivos de lock antes de usarlos."""
        with TemporaryDirectory() as tmp:
            lock_dir = Path(tmp) / "locks"
            env_backup = os.environ.get("TRH_LOCK_DIR")
            os.environ["TRH_LOCK_DIR"] = str(lock_dir)
            try:
                import importlib

                importlib.reload(proceso)
                # Evitamos ejecutar el pipeline real; solo importa la lógica de locks.
                with unittest.mock.patch.object(proceso, "ejecutar_pipeline"):
                    proceso.main()
                self.assertTrue(lock_dir.is_dir())
                self.assertTrue((lock_dir / "trh_proceso_run.lock").exists())
                self.assertTrue((lock_dir / "trh_proceso_queue.lock").exists())
            finally:
                if env_backup is None:
                    os.environ.pop("TRH_LOCK_DIR", None)
                else:
                    os.environ["TRH_LOCK_DIR"] = env_backup
                importlib.reload(proceso)


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
