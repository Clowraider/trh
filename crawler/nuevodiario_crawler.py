import requests
from psycopg2.extras import Json
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag
import time
import re
import hashlib
from datetime import datetime
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

# ================= CONFIGURACIÓN =================

BASE_URL = "https://nuevodiarioweb.com.ar"
DOMAIN = urlparse(BASE_URL).netloc

EXCLUDE_PATHS = [
    '/wp-admin/',
    '/wp-includes/',
    '/clasificados',
    '/politicas',
    '/modal',
    '/audios',
    '/galerias',
    '/extras',
    '/temas',
    '/edicion-impresa'
]

EXCLUDE_EXTENSIONS = (
    '.jpg',
    '.jpeg',
    '.png',
    '.webp',
    '.gif',
    '.svg',
    '.bmp',
    '.ico',
    '.avif'
)

MAX_URLS_POR_TANDA = 30
MAX_NOTICIAS_POR_EJECUCION = 100
DELAY = 2.8
MAX_RETRIES = 3

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


def should_exclude(url):

    path = urlparse(url).path.lower()

    # excluir paths
    if any(
        excluded in path
        for excluded in EXCLUDE_PATHS
    ):
        return True

    # excluir archivos multimedia
    if path.endswith(EXCLUDE_EXTENSIONS):
        return True

    return False


def save_url(url, importancia="baja"):

    if not url or DOMAIN not in url:
        return False

    url = normalize_url_for_storage(url)

    conn = get_connection()
    cur = conn.cursor()

    try:

        cur.execute("""
            INSERT INTO urls (url, estado, fuente, importancia)
            VALUES (%s, 0, 'Nuevo Diario Web', %s)
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

    h1 = soup.find(
        'h1',
        class_='titulo-nota'
    )

    ps = len(soup.find_all('p'))

    return h1 is not None and ps > 5


def extraer_fecha_nuevodiario(soup):

    time_tag = soup.find(
        'time',
        class_='fecha-nota'
    )

    if not time_tag:
        return None

    texto = time_tag.get_text(
        " ",
        strip=True
    ).lower()

    meses = {
        'enero': 1,
        'febrero': 2,
        'marzo': 3,
        'abril': 4,
        'mayo': 5,
        'junio': 6,
        'julio': 7,
        'agosto': 8,
        'septiembre': 9,
        'octubre': 10,
        'noviembre': 11,
        'diciembre': 12
    }

    match = re.search(
        r'(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})',
        texto
    )

    if not match:
        return None

    try:

        dia = int(match.group(1))
        mes = meses.get(match.group(2))
        anio = int(match.group(3))

        if not mes:
            return None

        return datetime(
            anio,
            mes,
            dia
        )

    except Exception as e:

        logger.warning(
            f"Error parseando fecha: {e}"
        )

        return None


def html_a_texto(html_content):

    if not html_content:
        return ''

    soup = BeautifulSoup(html_content, 'html.parser')

    # Eliminar etiquetas innecesarias
    for tag in [
        'script',
        'style',
        'iframe',
        'button'
    ]:

        for elem in soup.find_all(tag):
            elem.decompose()

    texto = soup.get_text(separator='\n')

    # Limpiar líneas vacías
    return '\n'.join(
        line.strip()
        for line in texto.split('\n')
        if line.strip()
    )


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
            'Nuevo Diario Web',
            url,
            titulo,
            texto,
            imagen,
            fecha_pub,
            Json(metadata)
        ))

        conn.commit()

        logger.info(
            f"✅ Noticia guardada: {titulo[:70]}..."
        )

        return True

    finally:
        cur.close()
        conn.close()


def procesar_pagina(url, importancia_links="baja", extraer_noticia=True):

    session = requests.Session()
    response = None

    for attempt in range(MAX_RETRIES):

        try:

            response = session.get(
                url,
                headers=build_random_headers(),
                timeout=30
            )

            if response.status_code == 200:
                break

            time.sleep(3 * (attempt + 1))

        except Exception as e:

            logger.warning(
                f"Intento {attempt+1} fallido: {e}"
            )

            if attempt == MAX_RETRIES - 1:
                raise

    if response is None:
        raise RuntimeError("No se pudo obtener respuesta HTTP")

    soup = BeautifulSoup(
        response.text,
        'html.parser'
    )

    logger.info(
        f"📄 Procesando: {url} | "
        f"Título: {soup.title.string[:80] if soup.title else 'Sin título'}"
    )

    # =================================================
    # EXTRAER LINKS
    # =================================================

    enlaces_guardados = 0

    for a in soup.find_all('a', href=True):

        full_url = clean_url(
            urljoin(url, a['href'])
        )

        # =================================================
        # SOLO URLs DEL SITIO
        # =================================================

        if not full_url.startswith(BASE_URL):
            continue

        if not should_exclude(full_url):

            if save_url(full_url, importancia_links):

                enlaces_guardados += 1

                logger.debug(
                    f"   → URL guardada: {full_url}"
                )

    logger.info(
        f"🔗 Enlaces nuevos/actualizados en esta página: "
        f"{enlaces_guardados}"
    )

    if not extraer_noticia:
        return True, False

    # =================================================
    # EXTRAER ARTÍCULO
    # =================================================

    if is_likely_article(soup):

        logger.info("📰 Detectado como ARTÍCULO")

        titulo = None

        h1 = soup.find(
            'h1',
            class_='titulo-nota'
        )

        if h1:
            titulo = h1.get_text(
                strip=True
            )

        fecha = extraer_fecha_nuevodiario(
            soup
        )

        section = soup.select_one(
            '#main article section'
        )

        texto_completo = ""

        if section:

            # =============================================
            # LIMPIEZA BÁSICA
            # =============================================

            for tag in section.find_all([
                'script',
                'style',
                'iframe',
                'button',
                'aside'
            ]):
                tag.decompose()

            parrafos = []

            for p in section.find_all('p'):

                texto_p = p.get_text(
                    " ",
                    strip=True
                )

                texto_lower = texto_p.lower()

                # =========================================
                # OMITIR BLOQUES BASURA
                # =========================================

                patrones_basura = [
                    'te puede interesar:',
                    'lee también:',
                    'leé también:'
                ]

                if any(
                    patron in texto_lower
                    for patron in patrones_basura
                ):
                    continue

                if len(texto_p) > 40:

                    parrafos.append(str(p))

            texto_completo = html_a_texto(
                ''.join(parrafos)
            )

        img = None

        figure = soup.find(
            'figure',
            class_='nota-foto'
        )

        if figure:

            imagen_tag = figure.find('img')

            if imagen_tag:

                img = (
                    imagen_tag.get('data-src')
                    or imagen_tag.get('src')
                )

        if not img:

            meta_img = soup.find(
                'meta',
                property='og:image'
            )

            if meta_img:
                img = meta_img.get('content')

        if titulo and len(texto_completo) > 300:

            noticia_guardada = guardar_noticia(
                url,
                titulo,
                fecha,
                texto_completo,
                img
            )

            return True, noticia_guardada

    return True, False


# ================= MAIN =================

def main():
    run_crawler_template(
        fuente='Nuevo Diario Web',
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
