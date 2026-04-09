# estas dos lineas le dicen a python donde encontrar db.py y config.py
# que estan en la carpeta superior (scraper/)
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# feedparser: libreria que lee y entiende archivos RSS
# requests: libreria para hacer pedidos a paginas web (como un navegador)
# datetime: para trabajar con fechas
import feedparser
import requests
from datetime import datetime

# importamos nuestros propios archivos
from db import get_connection   # la funcion que conecta a postgresql
from config import HEADERS      # el user-agent para simular un navegador

# nombre de la fuente que se guardara en la base de datos
FUENTE = "Vision Santiagueña"

# direccion del feed RSS
URL_FEED = "https://visionsantiago.com/feed/"


def parsear_fecha(fecha_texto):
    # el RSS trae la fecha en un formato especial como (2026, 4, 3, 17, 26, 54, ...)
    # datetime() la convierte a un formato que entiende postgresql
    try:
        return datetime(*fecha_texto[:6])  # toma solo los primeros 6 valores: año,mes,dia,hora,min,seg
    except:
        return None  # si falla por cualquier razon, devuelve vacio


def guardar_noticia(titulo, link, fecha):
    # abre una conexion a postgresql
    conn = get_connection()
    cur = conn.cursor()  # el cursor es como el "lapiz" para escribir en la base de datos

    try:
        # intenta insertar la noticia en la tabla noticias
        # ON CONFLICT (link) DO NOTHING significa:
        # si ya existe una noticia con ese link, no hagas nada (evita duplicados)
        cur.execute("""
            INSERT INTO noticias (titulo, link, fuente, fecha_publicacion)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (link) DO NOTHING
        """, (titulo, link, FUENTE, fecha))
        # los %s son los espacios donde van los valores, es mas seguro que poner
        # los valores directamente en el texto del query

        conn.commit()  # confirma los cambios, como un "guardar" en la base de datos

        # cur.rowcount dice cuantas filas se insertaron
        # si es mayor a 0, la noticia era nueva y se guardo
        if cur.rowcount > 0:
            print(f"  guardada: {titulo[:60]}")   # muestra solo los primeros 60 caracteres
        else:
            print(f"  ya existe: {titulo[:60]}")  # ya estaba en la base de datos

    except Exception as e:
        # si algo sale mal, muestra el error
        print(f"  error: {e}")
        conn.rollback()  # cancela los cambios, como un "deshacer"

    finally:
        # finally se ejecuta siempre, haya error o no
        # cerramos el cursor y la conexion para liberar recursos
        cur.close()
        conn.close()


def correr():
    print(f"Leyendo {FUENTE}...")

    # hace el pedido al feed RSS simulando ser un navegador
    respuesta = requests.get(URL_FEED, headers=HEADERS, timeout=10)

    # feedparser convierte el XML del RSS en un objeto python facil de usar
    # feed.entries es la lista de noticias
    feed = feedparser.parse(respuesta.content)

    print(f"Encontradas: {len(feed.entries)} noticias")

    # recorre cada noticia del feed
    for item in feed.entries:
        # .get("title", "") significa: dame el campo title,
        # y si no existe devuelve texto vacio en lugar de dar error
        titulo = item.get("title", "").strip()   # .strip() elimina espacios al inicio y final
        link   = item.get("link", "").strip()
        fecha  = parsear_fecha(item.get("published_parsed"))

        # solo guarda si tiene titulo y link, si falta alguno lo saltea
        if titulo and link:
            guardar_noticia(titulo, link, fecha)

    print("Listo.")


# esto significa: ejecuta la funcion correr() solo si
# corremos este archivo directamente (python vision_santiago.py)
# y no si otro script lo importa
correr()