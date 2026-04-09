import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import time
from bs4 import BeautifulSoup
from db import get_connection
from config import HEADERS
from utils import descargar_imagen

FUENTE = "Vision Santiagueña"
PAUSA_SEGUNDOS = 3


def obtener_links_pendientes():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, link, titulo FROM noticias
        WHERE fuente = %s
        AND estado = 'aprobado'
        AND id NOT IN (SELECT noticia_id FROM contenido)
    """, (FUENTE,))
    filas = cur.fetchall()
    cur.close()
    conn.close()
    return filas


def extraer_contenido(html):
    soup = BeautifulSoup(html, "html.parser")

    resumen = ""
    meta_desc = soup.find("meta", {"property": "og:description"})
    if meta_desc:
        resumen = meta_desc.get("content", "").strip()

    imagen_url = ""
    meta_img = soup.find("meta", {"property": "og:image"})
    if meta_img:
        imagen_url = meta_img.get("content", "").strip()

    texto = ""
    div_contenido = soup.find("div", class_="entry-content")
    if div_contenido:
        for tag in div_contenido.find_all("div", class_="fb-comments"):
            tag.decompose()
        for tag in div_contenido.find_all("h3"):
            tag.decompose()
        parrafos = []
        for p in div_contenido.find_all("p"):
            texto_parrafo = p.get_text(separator=" ").strip()
            texto_parrafo = " ".join(texto_parrafo.split())
            if texto_parrafo:
                parrafos.append(texto_parrafo)
        texto = "\n\n".join(parrafos)

    categorias = []
    for tag in soup.find_all("li", class_="post-category-link"):
        enlace = tag.find("a")
        if enlace:
            categorias.append(enlace.get_text().strip())

    return resumen, imagen_url, texto, categorias


def guardar_contenido(noticia_id, resumen, imagen_local, texto, categorias):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO contenido (noticia_id, resumen, texto_completo, imagen_url)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (noticia_id) DO NOTHING
        """, (noticia_id, resumen, texto, imagen_local))

        for nombre_categoria in categorias:
            cur.execute("""
                INSERT INTO categorias (nombre)
                VALUES (%s)
                ON CONFLICT (nombre) DO NOTHING
            """, (nombre_categoria,))
            cur.execute("SELECT id FROM categorias WHERE nombre = %s", (nombre_categoria,))
            cat_id = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO noticias_categorias (noticia_id, categoria_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, (noticia_id, cat_id))

        cur.execute("UPDATE noticias SET estado = 'completo' WHERE id = %s", (noticia_id,))
        conn.commit()
        print(f"  guardado contenido para noticia id={noticia_id}")

    except Exception as e:
        print(f"  error guardando id={noticia_id}: {e}")
        conn.rollback()
        cur.execute("UPDATE noticias SET estado = 'error' WHERE id = %s", (noticia_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def correr():
    print(f"Extractor {FUENTE}")
    noticias = obtener_links_pendientes()
    print(f"Noticias aprobadas para extraer: {len(noticias)}")

    if len(noticias) == 0:
        print("No hay noticias aprobadas.")
        return

    for noticia_id, link, titulo in noticias:
        print(f"\nProcesando: {link[:60]}")
        try:
            respuesta = requests.get(link, headers=HEADERS, timeout=10)
            resumen, imagen_url, texto, categorias = extraer_contenido(respuesta.text)
            nombre_imagen = descargar_imagen(imagen_url, titulo)
            guardar_contenido(noticia_id, resumen, nombre_imagen, texto, categorias)
        except Exception as e:
            print(f"  error al descargar: {e}")
        print(f"  esperando {PAUSA_SEGUNDOS} segundos...")
        time.sleep(PAUSA_SEGUNDOS)

    print("\nExtraccion finalizada.")


correr()