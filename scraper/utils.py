import os
import requests
import hashlib
from config import HEADERS

# carpeta donde se guardan las imagenes
# dentro del contenedor Docker el volumen esta montado en /app
# que corresponde a /root/docker/trh/codigo en el servidor
# las imagenes las guardamos fuera del codigo, en /root/docker/trh/imagenes
CARPETA_IMAGENES = os.getenv("CARPETA_IMAGENES", "/root/docker/trh/imagenes")


def descargar_imagen(url):
    # si no hay url devuelve vacio
    if not url:
        return ""

    try:
        # crea la carpeta si no existe
        os.makedirs(CARPETA_IMAGENES, exist_ok=True)

        # genera un nombre unico basado en la url
        # asi si la misma imagen se pide dos veces no se descarga dos veces
        nombre = hashlib.md5(url.encode()).hexdigest() + "." + url.split(".")[-1].split("?")[0]
        ruta_completa = os.path.join(CARPETA_IMAGENES, nombre)

        # si ya existe no la vuelve a bajar
        if os.path.exists(ruta_completa):
            return nombre

        # descarga la imagen
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