import os
import requests
import re
from unicodedata import normalize
from config import HEADERS

CARPETA_IMAGENES = os.getenv("CARPETA_IMAGENES", "/root/docker/trh/imagenes")

MAPA_ACENTOS = {
    'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
    'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u',
    'ä': 'a', 'ë': 'e', 'ï': 'i', 'ö': 'o', 'ü': 'u',
    'Á': 'a', 'É': 'e', 'Í': 'i', 'Ó': 'o', 'Ú': 'u',
    'À': 'a', 'È': 'e', 'Ì': 'i', 'Ò': 'o', 'Ù': 'u',
    'Ä': 'a', 'Ë': 'e', 'Ï': 'i', 'Ö': 'o', 'Ü': 'u',
    'ñ': 'n', 'Ñ': 'n'
}

def _limpiar_titulo(titulo):
    texto = titulo.strip()
    for accented, plain in MAPA_ACENTOS.items():
        texto = texto.replace(accented, plain)
    texto = re.sub(r'[^a-z0-9\s-]', '', texto.lower())
    texto = re.sub(r'[\s]+', '-', texto)
    return texto[:40]


def descargar_imagen(url, titulo):
    if not url:
        return ""

    try:
        os.makedirs(CARPETA_IMAGENES, exist_ok=True)

        nombre_base = _limpiar_titulo(titulo)
        ext = url.split(".")[-1].split("?")[0]
        if ext.lower() not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            ext = "jpg"
        nombre = f"{nombre_base}.{ext}"
        ruta_completa = os.path.join(CARPETA_IMAGENES, nombre)

        if os.path.exists(ruta_completa):
            return nombre

        respuesta = requests.get(url, headers=HEADERS, timeout=10)
        if respuesta.status_code == 200:
            with open(ruta_completa, "wb") as f:
                f.write(respuesta.content)
            print(f"  imagen guardada: {nombre}")
            return nombre
        else:
            print(f"  error descargando imagen: HTTP {respuesta.status_code}")
            return ""

    except Exception as e:
        print(f"  error descargando imagen: {e}")
        return ""