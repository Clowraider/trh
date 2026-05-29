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

# ================= CONFIGURACIÓN =================

BASE_URL = "https://www.elliberal.com.ar"
DOMAIN = urlparse(BASE_URL).netloc

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
]

EXCLUDE_PATHS = [
    '/autor/',
    '/categoria/',
    '/tag/',
    '/page/',
    '/buscar/',
    '/newsletter/',
]

MAX_URLS_POR_TANDA = 30
MAX_NOTICIAS_POR_EJECUCION = 100
DELAY = 2.5

# =================================================


def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "es-AR,es;q=0.9"
    }


def clean_url(url):
    return urldefrag(url)[0].rstrip('/')


# =================================================
# HASH DE CONTENIDO
# =================================================

def generar_hash_contenido(titulo, texto):

    titulo = (titulo or "").strip()
    texto = (texto or "").strip()

    contenido = titulo + " " + texto[:500]

    # normalización básica
    contenido = " ".join(
        contenido.lower().split()
    )

    return hashlib.sha256(
        contenido.encode("utf-8")
    ).hexdigest()


def is_valid_article_url(url):

    if not url:
        return False

    if not url.startswith(('http://', 'https://')):
        return False

    parsed = urlparse(url)

    if parsed.netloc not in [DOMAIN, f"www.{DOMAIN}"]:
        return False

    path = parsed.path.lower()

    if any(excluded in path for excluded in EXCLUDE_PATHS):
        return False

    # patrón típico:
    # /nota/79983/2026/05/titulo
    if not re.search(r'/nota/\d+/\d{4}/\d{2}/', path):
        return False

    return True


def save_url(url, importancia="baja"):

    if not is_valid_article_url(url):
        return False

    url = normalize_url_for_storage(url)

    conn = get_connection()
    cur = conn.cursor()

    try:

        cur.execute("""
            INSERT INTO urls (url, estado, fuente, importancia)
            VALUES (%s, 0, 'El Liberal', %s)
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

    titulo = soup.find('h1', class_='titulo')

    if not titulo:
        return False

    content = soup.find('div', id='texto_tpl6')

    if not content:
        return False

    parrafos = content.find_all('p')

    return len(parrafos) >= 3


def extraer_fecha_elliberal(soup):

    fecha_div = soup.find('div', class_=re.compile(r'fecha-publicacion'))

    if not fecha_div:
        return None

    texto = fecha_div.get_text(" ", strip=True)

    match = re.search(r'(\d{2})/(\d{2})/(\d{4})', texto)

    if not match:
        return None

    dia = int(match.group(1))
    mes = int(match.group(2))
    año = int(match.group(3))

    hora_match = re.search(r'(\d{2}):(\d{2})', texto)

    hora = 0
    minuto = 0

    if hora_match:
        hora = int(hora_match.group(1))
        minuto = int(hora_match.group(2))

    try:
        return datetime(año, mes, dia, hora, minuto)
    except:
        return None


def extraer_texto_articulo(content):

    if not content:
        return ""

    # eliminar basura
    basura_selectores = [
        'script',
        'style',
        'iframe',
        '.notas-texto-contenedor',
        '.relacionada-en-texto',
        '[data-type="adContainer"]',
        '.adsbygoogle',
        '.external',
        '.whtsppgrp'
    ]

    for selector in basura_selectores:

        for elem in content.select(selector):
            elem.decompose()

    parrafos_limpios = []

    for p in content.find_all('p'):

        texto = p.get_text(" ", strip=True)

        if not texto:
            continue

        if len(texto) < 40:
            continue

        texto_lower = texto.lower()

        # filtros basura
        if 'también te puede interesar' in texto_lower:
            continue

        if 'hacé click aquí' in texto_lower:
            continue

        if 'canal de whatsapp' in texto_lower:
            continue

        if 'publicidad' in texto_lower:
            continue

        parrafos_limpios.append(texto)

    texto_final = '\n\n'.join(parrafos_limpios)

    return texto_final.strip()


def guardar_noticia(url, titulo, fecha_pub, texto, imagen):

    url = normalize_url_for_storage(url)
    fecha_pub = normalize_fecha_publicacion(fecha_pub)

    if not titulo:
        logger.warning("❌ Sin título")
        return False

    if len(texto.strip()) < 300:
        logger.warning(
            f"❌ Texto insuficiente ({len(texto)} chars)"
        )
        return False

    metadata = build_quality_flags(url, titulo, texto, fecha_pub, imagen)

    conn = get_connection()
    cur = conn.cursor()

    try:

        # =================================================
        # HASHES
        # =================================================

        noticia_hash = hashlib.sha256(
            f"{url}{titulo}".encode("utf-8")
        ).hexdigest()

        hash_contenido = generar_hash_contenido(
            titulo,
            texto
        )

        # =================================================
        # DETECTAR DUPLICADOS
        # =================================================

        cur.execute("""
            SELECT id, url_original
            FROM noticias_historico
            WHERE hash_contenido = %s
            LIMIT 1
        """, (hash_contenido,))

        duplicada = cur.fetchone()

        if duplicada:

            logger.info(
                f"⚠️ Noticia duplicada detectada "
                f"(ID existente: {duplicada[0]})"
            )

            return False

        # =================================================
        # INSERTAR NOTICIA
        # =================================================

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
            'El Liberal',
            url,
            titulo,
            texto,
            imagen,
            fecha_pub,
            Json(metadata)
        ))

        conn.commit()

        logger.info(f"✅ Noticia guardada: {titulo[:80]}...")

        return True

    finally:
        cur.close()
        conn.close()


def procesar_pagina(url, importancia_links="baja", extraer_noticia=True):

    logger.info(f"📄 Procesando: {url}")

    session = requests.Session()

    response = session.get(
        url,
        headers=get_random_headers(),
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')

    # =================================================
    # EXTRAER LINKS
    # =================================================

    enlaces_guardados = 0

    for a in soup.find_all('a', href=True):

        full_url = clean_url(urljoin(url, a['href']))

        if is_valid_article_url(full_url):

            if save_url(full_url, importancia_links):
                enlaces_guardados += 1

    logger.info(f"🔗 Links nuevos/actualizados: {enlaces_guardados}")

    if not extraer_noticia:
        return True, False

    # =================================================
    # DETECTAR ARTÍCULO
    # =================================================

    if not is_likely_article(soup):

        logger.info("ℹ️ No es artículo")

        return True, False

    logger.info("📰 Artículo detectado")

    # =================================================
    # TÍTULO
    # =================================================

    titulo_tag = soup.find('h1', class_='titulo')

    titulo = titulo_tag.get_text(strip=True) if titulo_tag else None

    # =================================================
    # FECHA
    # =================================================

    fecha = extraer_fecha_elliberal(soup)

    # =================================================
    # CONTENIDO
    # =================================================

    content = soup.find('div', id='texto_tpl6')

    texto_completo = extraer_texto_articulo(content)

    logger.info(f"📝 Texto extraído: {len(texto_completo)} chars")

    # =================================================
    # IMAGEN
    # =================================================

    img = None

    meta_img = soup.find('meta', property='og:image')

    if meta_img:
        img = meta_img.get('content')

    # =================================================
    # GUARDAR
    # =================================================

    noticia_guardada = guardar_noticia(
        url,
        titulo,
        fecha,
        texto_completo,
        img
    )

    return True, noticia_guardada


# ================= MAIN =================

def main():
    run_crawler_template(
        fuente='El Liberal',
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
