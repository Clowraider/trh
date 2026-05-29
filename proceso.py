import subprocess

# ----------------------------------------
# Scripts que se ejecutan EN PARALELO
# ----------------------------------------

scripts_paralelos = [
    "crawler/elliberal_crawler.py",
    "crawler/panorama_crawler.py",
    "crawler/nuevodiario_crawler.py",
    "crawler/termasdigital_crawler.py",
    "crawler/sursantiago_crawler.py",
]

# ----------------------------------------
# Scripts que se ejecutan DESPUÉS,
# uno por uno
# ----------------------------------------

scripts_secuenciales = [
    "embedding_archivo.py",
    "cluster_noticias.py",
]

procesos = []

print("Iniciando crawlers en paralelo...\n")

# Lanzar todos juntos
for script in scripts_paralelos:
    print(f"Iniciando {script}...")
    
    p = subprocess.Popen(
        ["python", script]
    )

    procesos.append((script, p))

# Esperar que terminen todos
for script, proceso in procesos:
    proceso.wait()

    if proceso.returncode != 0:
        raise Exception(f"{script} terminó con error.")

    print(f"{script} terminado.")

print("\nTodos los crawlers terminaron.\n")

# ----------------------------------------
# Ejecutar los demás secuencialmente
# ----------------------------------------

for script in scripts_secuenciales:
    print(f"Ejecutando {script}...")

    resultado = subprocess.run(
        ["python", script],
        check=True
    )

    print(f"{script} terminado.\n")

print("Todos los scripts finalizaron.")
