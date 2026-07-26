import requests
from psycopg2.extras import Json
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag
import time
import re
import hashlib
from datetime import datetime, timedelta
import logging

from common import (
    build_random_headers,
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

BASE_URL = "https://termasdigital.com.ar"
DOMAIN = urlparse(BASE_URL).netloc

EXCLUDE_PATHS = [
    '/wp-admin/', '/wp-includes/', '/author/', '/category/', '/tag/', '/page/', '/feed/'
]

MAX_URLS_POR_TANDA = 30
MAX_NOTICIAS_POR_EJECUCION = 100
DELAY = 2.8
MAX_RETRIES = 3
def clean_url(url):
    return urldefrag(url)[0].rstrip('/')


def generar_hash_contenido(titulo, texto):
    titulo = (titulo or "").strip()
    texto = (texto or "").strip()
    contenido = titulo + " " + texto[:500]
    contenido = " ".join(contenido.lower().split())
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


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

    if len(path) < 20:
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
            VALUES (%s, 0, 'TermasDigital', %s)
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
    if not soup.find('h1'):
        return False
    content = soup.select_one('div.entry-content')
    if not content:
        return False
    return len(content.find_all('p')) >= 3


def extraer_fecha_termasdigital(soup):
    """
    Nueva lógica:
    - Solo aceptar fecha de publicación en formato tipo: "9 abril, 2026"
    - Cualquier otro formato => None (se usará fecha_extraccion en DB)
    """
    meses = {
        'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
        'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
        'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
    }

    fecha_span = soup.select_one('span.date.meta-item')
    if not fecha_span:
        return None

    texto = fecha_span.get_text(" ", strip=True).lower()

    # Acepta estrictamente fechas absolutas con año explícito.
    # Ejemplos válidos: "9 abril, 2026" / "09 abril 2026"
    match = re.search(r'^(\d{1,2})\s+([a-záéíóú]+),?\s+(\d{4})$', texto)
    if not match:
        return None

    dia = int(match.group(1))
    mes_txt = match.group(2)
    anio = int(match.group(3))
    mes = meses.get(mes_txt)

    if not mes:
        return None

    try:
        return datetime(anio, mes, dia)
    except Exception:
        return None


def extraer_texto_articulo(content):
    if not content:
        return ""

    basura_selectores = [
        'script', 'style', 'iframe', '.heateor_ffc_facebook_comments',
        '.sharedaddy', '.jp-relatedposts', '.fb-comments', '#fb-root'
    ]

    for selector in basura_selectores:
        for elem in content.select(selector):
            elem.decompose()

    parrafos_limpios = []
    for p in content.find_all('p'):
        texto = p.get_text(" ", strip=True)
        if len(texto) < 30:
            continue
        texto_lower = texto.lower()
        if 'facebook' in texto_lower or 'twitter' in texto_lower or 'instagram' in texto_lower:
            continue
        parrafos_limpios.append(texto)

    return '\n\n'.join(parrafos_limpios).strip()


def guardar_noticia(url, titulo, fecha_pub, texto, imagen):
    url = normalize_url_for_storage(url)
    fecha_pub = normalize_fecha_publicacion(fecha_pub)

    # Regla solicitada: fecha_publicacion nunca vacía.
    # Si no se pudo extraer una fecha de publicación válida,
    # usar la fecha/hora de extracción (ahora).
    if fecha_pub is None:
        fecha_pub = datetime.now()

    if not titulo:
        logger.warning("❌ Sin título")
        return False
    if len(texto.strip()) < 300:
        logger.warning(f"❌ Texto insuficiente ({len(texto)} chars): {titulo}")
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
        if cur.fetchone():
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
            noticia_hash, hash_contenido, 'TermasDigital', url,
            titulo, texto, imagen, fecha_pub, Json(metadata)
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
    response = None

    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(url, headers=build_random_headers(), timeout=30)
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

    enlaces_guardados = 0
    for a in soup.find_all('a', href=True):
        href = a.get('href')
        if not isinstance(href, str):
            continue
        full_url = clean_url(urljoin(url, href))
        if is_valid_article_url(full_url):
            if save_url(full_url, importancia_links):
                enlaces_guardados += 1

    logger.info(f"🔗 Enlaces nuevos/actualizados: {enlaces_guardados}")

    if not extraer_noticia:
        return True, False

    if not is_likely_article(soup):
        logger.info("ℹ️ No detectado como artículo")
        return True, False

    logger.info("📰 Detectado como artículo")

    titulo_tag = soup.find('h1')
    titulo = titulo_tag.get_text(strip=True) if titulo_tag else None
    fecha = extraer_fecha_termasdigital(soup)
    content = soup.select_one('div.entry-content')
    texto_completo = extraer_texto_articulo(content)
    logger.info(f"📝 Texto extraído: {len(texto_completo)} caracteres")

    img = None
    meta_img = soup.find('meta', property='og:image')
    if meta_img:
        img = meta_img.get('content')

    noticia_guardada = guardar_noticia(url, titulo, fecha, texto_completo, img)
    return True, noticia_guardada


def main():
    run_crawler_template(
        fuente='TermasDigital',
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
