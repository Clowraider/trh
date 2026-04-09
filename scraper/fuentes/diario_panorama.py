import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import feedparser
import requests
from datetime import datetime
from db import get_connection
from config import HEADERS

FUENTE = "Diario Panorama"
URL_FEED = "https://diariopanorama.com/rss"

def parsear_fecha(fecha_texto):
    try:
        return datetime(*fecha_texto[:6])
    except:
        return None

def guardar_noticia(titulo, link, fecha):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO noticias (titulo, link, fuente, fecha_publicacion)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (link) DO NOTHING
        """, (titulo, link, FUENTE, fecha))
        conn.commit()
        if cur.rowcount > 0:
            print(f"  guardada: {titulo[:60]}")
        else:
            print(f"  ya existe: {titulo[:60]}")
    except Exception as e:
        print(f"  error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def correr():
    print(f"Leyendo {FUENTE}...")
    respuesta = requests.get(URL_FEED, headers=HEADERS, timeout=10)
    feed = feedparser.parse(respuesta.content)
    print(f"Encontradas: {len(feed.entries)} noticias")
    for item in feed.entries:
        titulo = item.get("title", "").strip()
        link   = item.get("link", "").strip()
        fecha  = parsear_fecha(item.get("published_parsed"))
        if titulo and link:
            guardar_noticia(titulo, link, fecha)
    print("Listo.")

correr()