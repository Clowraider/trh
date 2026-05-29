import requests
from psycopg2.extras import Json
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag
import time
import re
import random
import hashlib
from datetime import datetime
import logging

from common import (
    build_quality_flags,
    get_connection,
    normalize_fecha_publicacion,
    normalize_url_for_storage,
    run_crawler_template,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_URL = "https://sursantiago.com.ar"
DOMAIN = urlparse(BASE_URL).netloc
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
]
EXCLUDE_PATHS = [
    '/wp-admin/', '/wp-includes/', '/clasificados', '/politicas', '/modal',
    '/audios', '/galerias', '/extras', '/widget', '/api/'
]
MAX_URLS_POR_TANDA = 30
MAX_NOTICIAS_POR_EJECUCION = 100
DELAY = 2.8
MAX_RETRIES = 3


def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "es-ES,es;q=0.9"
    }


def clean_url(url):
    return urldefrag(url)[0].rstrip('/')


def generar_hash_contenido(titulo, texto):
    titulo = (titulo or "").strip()
    texto = (texto or "").strip()
    contenido = titulo + " " + texto[:500]
    contenido = " ".join(contenido.lower().split())
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def should_exclude(url):
    path = urlparse(url).path.lower()
    return any(excluded in path for excluded in EXCLUDE_PATHS)


def save_url(url, importancia="baja"):
    if not url or DOMAIN not in url:
        return False

    url = normalize_url_for_storage(url)

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO urls (url, estado, fuente, importancia)
            VALUES (%s, 0, 'Sur Santiago', %s)
            ON CONFLICT (url) DO UPDATE
            SET importancia = CASE
                WHEN EXCLUDED.importancia = 'alta' THEN 'alta'
                ELSE COALESCE(urls.importancia, 'baja')
            END
        """, (url, importancia))

        inserted_or_updated = cur.rowcount > 0
        conn.commit()
        return inserted_or_updated
    finally:
        cur.close()
        conn.close()


def is_likely_article(soup):
    h1 = soup.find('h1', class_='titulo-nota')
    if not h1:
        h1 = soup.find('h1')

    ps_validos = [p for p in soup.find_all('p') if len(p.get_text(strip=True)) > 40]
    return h1 is not None and len(ps_validos) >= 4


def extraer_fecha_sursantiago(soup):
    for elem in soup.find_all(string=True):
        texto = elem.strip()
        if "Creado:" in texto:
            match = re.search(r'(\d{1,2})\s+([a-záéíóú]+)\s*,?\s*(\d{4})', texto.lower())
            if match:
                dia = int(match.group(1))
                mes_str = match.group(2)
                anio = int(match.group(3))
                meses = {
                    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
                    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
                    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
                }
                mes = meses.get(mes_str)
                if mes and 2020 <= anio <= 2030:
                    return datetime(anio, mes, dia)

    texto_completo = soup.get_text().lower()
    match = re.search(r'(\d{1,2})\s+([a-záéíóú]+)\s*,?\s*(\d{4})', texto_completo)
    if match:
        dia = int(match.group(1))
        mes_str = match.group(2)
        anio = int(match.group(3))
        meses = {
            'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
            'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
            'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
        }
        mes = meses.get(mes_str)
        if mes and 2020 <= anio <= 2030 and 1 <= dia <= 31:
            return datetime(anio, mes, dia)

    return None


def html_a_texto(html_content):
    if not html_content:
        return ''

    soup = BeautifulSoup(html_content, 'html.parser')
    for tag in ['script', 'style', 'iframe', 'button']:
        for elem in soup.find_all(tag):
            elem.decompose()

    texto = soup.get_text(separator='\n')
    return '\n'.join(line.strip() for line in texto.split('\n') if line.strip())


def guardar_noticia(url, titulo, fecha_pub, texto, imagen):
    url = normalize_url_for_storage(url)
    fecha_pub = normalize_fecha_publicacion(fecha_pub)

    if not titulo:
        logger.warning("❌ Sin título")
        return False

    if len(texto.strip()) < 300:
        logger.warning(f"❌ Texto insuficiente ({len(texto)} chars)")
        return False

    metadata = build_quality_flags(url, titulo, texto, fecha_pub, imagen)

    conn = get_connection()
    cur = conn.cursor()

    try:
        noticia_hash = hashlib.sha256(f"{url}{titulo}".encode("utf-8")).hexdigest()
        hash_contenido = generar_hash_contenido(titulo, texto)

        cur.execute("""
            SELECT id, url_original
            FROM noticias_historico
            WHERE hash_contenido = %s
            LIMIT 1
        """, (hash_contenido,))

        duplicada = cur.fetchone()
        if duplicada:
            logger.info(f"⚠️ Noticia duplicada detectada (ID existente: {duplicada[0]})")
            return False

        cur.execute("""
            INSERT INTO noticias_historico
            (
                noticia_hash,
                hash_contenido,
                fuente,
                url_original,
                titulo,
                texto_completo,
                url_imagen,
                fecha_publicacion,
                metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (url_original)
            DO UPDATE SET
                titulo = EXCLUDED.titulo,
                texto_completo = EXCLUDED.texto_completo,
                url_imagen = EXCLUDED.url_imagen,
                fecha_publicacion = EXCLUDED.fecha_publicacion,
                hash_contenido = EXCLUDED.hash_contenido,
                metadata = EXCLUDED.metadata
        """, (
            noticia_hash,
            hash_contenido,
            'Sur Santiago',
            url,
            titulo,
            texto,
            imagen,
            fecha_pub,
            Json(metadata)
        ))

        conn.commit()
        logger.info(f"✅ Noticia guardada: {titulo[:70]}...")
        return True
    finally:
        cur.close()
        conn.close()


def extraer_contenido_sursantiago(soup):
    parrafos = []
    cortar_en = False

    for elem in soup.find_all(['p', 'h2', 'h3', 'h4']):
        if cortar_en:
            break

        texto = elem.get_text(" ", strip=True)
        texto_lower = texto.lower()

        if len(texto) < 30:
            continue

        patrones_corte = [
            'más noticias', 'publica aquí', 'te puede interesar',
            'lee también', 'leé también', 'facebook', 'twitter',
            'widget', 'compartir', 'siguientes notas'
        ]

        if any(p in texto_lower for p in patrones_corte):
            cortar_en = True
            continue

        if elem.name in ['h2', 'h3', 'h4']:
            parrafos.append(f"<h3>{texto}</h3>")
        else:
            parrafos.append(str(elem))

    if not parrafos:
        return ""

    return html_a_texto(''.join(parrafos))


def extraer_imagen_sursantiago(soup):
    img_tag = soup.find('img', class_='img-fluid')
    if img_tag:
        src = img_tag.get('src') or img_tag.get('data-src')
        if src and src.startswith('http'):
            return src

    for figure_class in ['nota-foto', 'img-nota']:
        figure = soup.find('figure', class_=figure_class)
        if figure:
            img = figure.find('img')
            if img:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src and src.startswith('http'):
                    return src

    meta = soup.find('meta', property='og:image')
    if meta and meta.get('content'):
        return meta.get('content')

    return None


def procesar_pagina(url, importancia_links="baja", extraer_noticia=True):
    session = requests.Session()
    response = None

    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(url, headers=get_random_headers(), timeout=30)
            if response.status_code == 200:
                break
            time.sleep(3 * (attempt + 1))
        except Exception as e:
            logger.warning(f"Intento {attempt+1} fallido: {e}")
            if attempt == MAX_RETRIES - 1:
                raise

    if response is None:
        raise RuntimeError("No se pudo obtener respuesta HTTP")

    soup = BeautifulSoup(response.text, 'html.parser')

    logger.info(f"📄 Procesando: {url} | Título: {soup.title.string[:80] if soup.title else 'Sin título'}")

    enlaces_guardados = 0
    for a in soup.find_all('a', href=True):
        full_url = clean_url(urljoin(url, a['href']))
        if not full_url.startswith(BASE_URL):
            continue
        if DOMAIN in full_url and not should_exclude(full_url):
            if save_url(full_url, importancia_links):
                enlaces_guardados += 1
                logger.debug(f"   → URL guardada: {full_url}")

    logger.info(f"🔗 Enlaces nuevos/actualizados en esta página: {enlaces_guardados}")

    if not extraer_noticia:
        return True, False

    if is_likely_article(soup):
        logger.info("📰 Detectado como ARTÍCULO")

        titulo = None
        h1 = soup.find('h1', class_='titulo-nota')
        if not h1:
            h1 = soup.find('h1')
        if h1:
            titulo = h1.get_text(strip=True)

        fecha = extraer_fecha_sursantiago(soup)
        texto_completo = extraer_contenido_sursantiago(soup)
        img = extraer_imagen_sursantiago(soup)

        if titulo and len(texto_completo) > 300:
            noticia_guardada = guardar_noticia(url, titulo, fecha, texto_completo, img)
            return True, noticia_guardada

        logger.warning(f"⚠️ No se guardó: titulo={bool(titulo)}, texto_len={len(texto_completo)}")

    return True, False


def main():
    run_crawler_template(
        fuente='Sur Santiago',
        base_url=BASE_URL,
        process_page=procesar_pagina,
        max_urls_por_tanda=MAX_URLS_POR_TANDA,
        max_noticias_por_ejecucion=MAX_NOTICIAS_POR_EJECUCION,
        delay_base=DELAY,
        delay_random_min=0.5,
        delay_random_max=2,
        logger=logger,
    )


if __name__ == "__main__":
    main()
