# extractor_collector.py - corre todos los extractores de una sola vez

import subprocess
import sys
import os

# lista de todos los extractores
EXTRACTORES = [
    "scraper/fuentes/extractor_vision_santiago.py",
    "scraper/fuentes/extractor_rio_hondo_news.py",
    "scraper/fuentes/extractor_diario_panorama.py",
]

print("=" * 50)
print("Iniciando extraccion de contenido...")
print("=" * 50)

for script in EXTRACTORES:
    print(f"\nEjecutando: {script}")
    resultado = subprocess.run([sys.executable, script])

    if resultado.returncode != 0:
        print(f"  ADVERTENCIA: {script} termino con errores")

print("\n" + "=" * 50)
print("Extraccion finalizada.")
print("=" * 50)