import fcntl
import subprocess
import sys
from pathlib import Path

# ----------------------------------------
# Scripts que se ejecutan EN PARALELO
# ----------------------------------------

def discover_crawler_scripts(sites_dir=None, base_dir=None):
    """Descubre los scripts de crawler dentro de crawler/sites/."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent
    if sites_dir is None:
        sites_dir = base_dir / "crawler" / "sites"
    # El plantilla es un ejemplo documentado; no debe ejecutarse como crawler real.
    excluded = {"plantilla_crawler.py"}
    return sorted(
        str(path.relative_to(base_dir))
        for path in sites_dir.glob("*_crawler.py")
        if path.name not in excluded
    )


scripts_paralelos = discover_crawler_scripts()

# ----------------------------------------
# Scripts que se ejecutan DESPUÉS,
# uno por uno
# ----------------------------------------

scripts_secuenciales = [
    "pipeline/embedding_archivo.py",
    "pipeline/cluster_noticias.py",
    "pipeline/extraer_keywords_ner.py",
]

LOCK_DIR = Path("/tmp")
RUN_LOCK_PATH = LOCK_DIR / "trh_proceso_run.lock"
QUEUE_LOCK_PATH = LOCK_DIR / "trh_proceso_queue.lock"


def ejecutar_pipeline():
    procesos = []
    python_cmd = sys.executable

    print("Iniciando crawlers en paralelo...\n")

    for script in scripts_paralelos:
        print(f"Iniciando {script}...")
        p = subprocess.Popen([python_cmd, script])
        procesos.append((script, p))

    for script, proceso in procesos:
        proceso.wait()
        if proceso.returncode != 0:
            raise Exception(f"{script} terminó con error.")
        print(f"{script} terminado.")

    print("\nTodos los crawlers terminaron.\n")

    for script in scripts_secuenciales:
        print(f"Ejecutando {script}...")
        subprocess.run([python_cmd, script], check=True)
        print(f"{script} terminado.\n")

    print("Todos los scripts finalizaron.")


def main():
    RUN_LOCK_PATH.touch(exist_ok=True)
    QUEUE_LOCK_PATH.touch(exist_ok=True)

    with open(RUN_LOCK_PATH, "r") as run_lock:
        try:
            # Intento ejecutar ya
            fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print("Lock principal adquirido. Ejecutando pipeline ahora.")
            ejecutar_pipeline()
            return
        except BlockingIOError:
            print("Ya hay una ejecución corriendo. Intentando entrar en cola (máx 1)...")

        with open(QUEUE_LOCK_PATH, "r") as queue_lock:
            try:
                # Reserva el único lugar de cola
                fcntl.flock(queue_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("Cola llena (ya hay 1 ejecución esperando). Se cancela esta corrida.")
                return

            print("Lugar de cola reservado. Esperando a que termine la ejecución actual...")

            # Espera bloqueante al lock principal
            fcntl.flock(run_lock, fcntl.LOCK_EX)

            # Ya pasó de cola a ejecución; libero lugar de cola
            fcntl.flock(queue_lock, fcntl.LOCK_UN)

            print("Turno adquirido. Ejecutando pipeline...")
            ejecutar_pipeline()


if __name__ == "__main__":
    main()
