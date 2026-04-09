# collector.py - corre todos los scrapers de fuentes de una sola vez

import subprocess
import sys
import os

# lista de todos los scripts de fuentes
FUENTES = [
    "scraper/fuentes/vision_santiago.py",
    "scraper/fuentes/rio_hondo_news.py",
    "scraper/fuentes/diario_panorama.py",
]

print("=" * 50)
print("Iniciando recoleccion de noticias...")
print("=" * 50)

for script in FUENTES:
    print(f"\nEjecutando: {script}")
    # subprocess.run ejecuta cada script como si lo corrieras vos a mano
    # sys.executable usa el mismo python que esta corriendo este script
    resultado = subprocess.run([sys.executable, script])
    
    if resultado.returncode != 0:
        # returncode distinto de 0 significa que el script tuvo un error
        print(f"  ADVERTENCIA: {script} termino con errores")

print("\n" + "=" * 50)
print("Recoleccion finalizada.")
print("=" * 50)