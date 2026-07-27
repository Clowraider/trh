#!/usr/bin/env python3
"""
Crawler plantilla / ejemplo funcional.

Este archivo es una guía concreta: funciona para La Nación (Argentina)
pero está pensado para que lo copies, renombres y adaptes a cualquier
sitio de noticias.

Para crear tu propio crawler:
  1. Copiá este archivo como crawler/sites/<mi_sitio>_crawler.py
  2. Cambiá BASE_URL, FUENTE y los XPATH_*.
  3. Ajustá EXCLUDE_PATHS y EXCLUDE_EXTENSIONS si hace falta.
  4. Adaptá la lógica de extracción de fecha/hora/imagen si el sitio usa
     otros atributos o formatos.
  5. Ejecutalo con: python crawler/sites/<mi_sitio>_crawler.py

Requisitos mínimos que debe cumplir un crawler:
  - Extraer: url, titulo, texto (cuerpo de la noticia), fecha_publicacion.
  - Opcional pero recomendado: imagen.
  - Guardar links internos descubiertos en la tabla `urls`.
  - Llamar a run_crawler_template() al final para que corra dentro del
    pipeline común.
"""

import argparse
import hashlib
import html
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from lxml import html as lhtml
from psycopg2.extras import Json

# Aseguramos que este script pueda importar crawler/common.py aunque se
# ejecute directamente con: python crawler/sites/plantilla_crawler.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import (
    build_quality_flags,
    build_random_headers,
    get_connection,
    normalize_noticia_fields_for_storage,
    normalize_url_for_storage,
    remove_selected_content,
    run_crawler_template,
    should_skip_paragraph_text,
)

# =================================================
# CONFIGURACIÓN DEL SITIO
# =================================================

# URL raíz del medio. Se usa para filtrar links y para armar URLs absolutas.
BASE_URL = "https://www.lanacion.com.ar"

# URL de ejemplo para el modo test. Debería ser una noticia real del sitio.
TEST_URL = (
    "https://www.lanacion.com.ar/politica/"
    "el-canciller-de-lula-recibio-al-embajador-argentino-en-brasilia-"
    "y-le-transmitio-el-repudio-de-su-nid27072026/"
)

# Identificador de la fuente. Debe coincidir con el valor que guarda save_url().
FUENTE = "La_Nacion"

# Bandera global de modo test. En este modo no se toca la base de datos.
TEST_MODE = False

# Límites de ejecución. Ajustá según el tamaño del sitio y la frecuencia.
MAX_URLS_POR_TANDA = 30
MAX_NOTICIAS_POR_EJECUCION = 100
DELAY = 2.8
MAX_RETRIES = 3

# Paths que no queremos rastrear (admin, archivos estáticos, etc.)
# IMPORTANTE: no incluyas secciones que SÍ contengan noticias, como /politica/.
EXCLUDE_PATHS = [
    "/wp-admin/",
    "/wp-includes/",
    "/tema/",
]

# Extensiones de archivo que nunca queremos guardar como URLs a scrapear.
EXCLUDE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".pdf",
    ".mp3",
    ".mp4",
    ".zip",
    ".xml",
    ".rss",
)

# XPaths de ejemplo para La Nación.
# Estos selectores apuntan a un artículo típico del sitio.
XPATH_TITULO = "/html/body/div[1]/div[3]/main/div[13]/div/div/h1/text()"
XPATH_TEXTO = "/html/body/div[1]/div[3]/main/div[14]/div[1]/section/div/div[2]/div/div"
XPATH_FECHA = "/html/body/div[1]/div[3]/main/div[14]/div[1]/div/div/div[2]/ul/li[1]/time"
XPATH_HORA = "/html/body/div[1]/div[3]/main/div[14]/div[1]/div/div/div[2]/ul/li[2]/time"
XPATH_IMAGEN = "/html/body/div[1]/div[3]/main/div[14]/div[1]/div/div/div[5]/section/div/section/figure/div/div/img"

# Longitud mínima del cuerpo para considerar que es una noticia válida.
MIN_TEXT_LENGTH = 300

# Longitud mínima del título.
MIN_TITLE_LENGTH = 10

# Logger estándar. Recomendable mantener este formato para que el pipeline
# pueda leer la salida en caso de depuración.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =================================================
# FUNCIONES AUXILIARES GENÉRICAS
# (Podés tocarlas, pero en general sirven para la mayoría de los sitios.)
# =================================================


def clean_url(url: str) -> str:
    """Devuelve la URL sin fragmentos (#) y sin barra final."""
    return urldefrag(url)[0].rstrip("/")


def generar_hash_contenido(titulo: str | None, texto: str | None) -> str:
    """Hash usado para detectar noticias duplicadas por contenido."""
    contenido = f"{(titulo or '').strip()} {(texto or '').strip()[:500]}"
    contenido = " ".join(contenido.lower().split())
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def should_exclude(url: str) -> bool:
    """Decide si una URL no debe agregarse a la cola de procesamiento."""
    path = urlparse(url).path.lower()

    if any(excluded in path for excluded in EXCLUDE_PATHS):
        return True

    if path.endswith(EXCLUDE_EXTENSIONS):
        return True

    return False


def save_url(url: str, importancia: str = "baja") -> bool:
    """Guarda una URL descubierta en la tabla `urls` para procesar después."""
    if not url or BASE_URL not in url:
        return False

    url = normalize_url_for_storage(url)

    if TEST_MODE:
        # En modo test no tocamos la base de datos, solo logueamos en debug.
        logger.debug(f"[TEST] Link descubierto ({importancia}): {url}")
        return True

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO urls (url, estado, fuente, importancia)
            VALUES (%s, 0, %s, %s)
            ON CONFLICT (url) DO UPDATE
            SET importancia = CASE
                WHEN EXCLUDED.importancia = 'alta' THEN 'alta'
                ELSE COALESCE(urls.importancia, 'baja')
            END
            """,
            (url, FUENTE, importancia),
        )

        inserted_or_updated = cur.rowcount > 0
        conn.commit()
        return inserted_or_updated

    finally:
        cur.close()
        conn.close()


def html_a_texto(html_content: str) -> str:
    """Convierte HTML a texto plano, preservando párrafos."""
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "html.parser")

    # Sacamos etiquetas que nunca aportan contenido editorial.
    for tag in ["script", "style", "iframe", "button", "aside", "nav"]:
        for elem in soup.find_all(tag):
            elem.decompose()

    # Convertimos <br>, <p>, etc. en saltos de línea para que el texto no quede
    # todo pegado.
    for br in soup.find_all("br"):
        br.replace_with("\n")

    texto = soup.get_text(separator="\n", strip=True)
    lineas = [" ".join(linea.split()) for linea in texto.splitlines() if linea.strip()]
    return "\n".join(lineas)


# =================================================
# FUNCIONES ESPECÍFICAS DE EXTRACCIÓN
# (Estas SÍ las vas a adaptar para cada sitio.)
# =================================================


def is_likely_article(soup: BeautifulSoup) -> bool:
    """Heurística rápida para decidir si la página es una noticia."""
    tree = lhtml.fromstring(str(soup))
    titulo = tree.xpath(XPATH_TITULO)
    cuerpo = tree.xpath(XPATH_TEXTO)
    return bool(titulo) and bool(cuerpo)


def _extraer_texto_xpath(tree: lhtml.HtmlElement, xpath: str) -> str | None:
    """Extrae texto plano de un elemento dado un XPath."""
    elementos = tree.xpath(xpath)
    if not elementos:
        return None

    # Si el XPath apunta a un nodo de texto, devuelve un string directamente.
    # Si apunta a un elemento, lo convertimos a texto.
    primero = elementos[0]
    if isinstance(primero, str):
        return primero.strip() or None

    # Para elementos HTML, usamos text_content() y luego limpiamos.
    return html.unescape(" ".join(primero.text_content().split())) or None


def _extraer_atributo_xpath(tree: lhtml.HtmlElement, xpath: str, atributo: str) -> str | None:
    """Extrae un atributo de un elemento dado un XPath (ej. src de <img>)."""
    elementos = tree.xpath(xpath)
    if not elementos:
        return None

    primero = elementos[0]
    if isinstance(primero, str):
        return None

    return primero.get(atributo)


def _parse_time_element(tree: lhtml.HtmlElement, xpath: str) -> datetime | None:
    """Intenta obtener un datetime desde un elemento <time>."""
    elementos = tree.xpath(xpath)
    if not elementos or isinstance(elementos[0], str):
        return None

    elem = elementos[0]

    # Lo ideal es que el <time> tenga el atributo datetime en ISO 8601.
    attr = elem.get("datetime")
    if attr:
        try:
            return datetime.fromisoformat(attr.replace("Z", "+00:00"))
        except ValueError:
            pass

    # Si no, intentamos parsear el texto visible.
    texto = " ".join(elem.text_content().split())
    if not texto:
        return None

    # Ejemplos soportados: "27 de julio de 2026" o "27/07/2026".
    meses = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }

    match = re.search(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})", texto.lower())
    if match:
        dia = int(match.group(1))
        mes = meses.get(match.group(2))
        anio = int(match.group(3))
        if mes:
            return datetime(anio, mes, dia)

    # Fallback a dateutil si está disponible.
    try:
        from dateutil import parser
        return parser.parse(texto, dayfirst=True)
    except Exception:
        return None


def extraer_fecha(tree: lhtml.HtmlElement) -> datetime | None:
    """Combina fecha y hora del artículo en un solo datetime."""
    fecha = _parse_time_element(tree, XPATH_FECHA)
    hora = _parse_time_element(tree, XPATH_HORA)

    if fecha and hora:
        return fecha.replace(
            hour=hora.hour,
            minute=hora.minute,
            second=0,
            microsecond=0,
        )

    return fecha


def extraer_imagen(tree: lhtml.HtmlElement) -> str | None:
    """Devuelve la URL de la imagen principal, resuelta contra BASE_URL."""
    src = _extraer_atributo_xpath(tree, XPATH_IMAGEN, "src")
    if src:
        return urljoin(BASE_URL, src)

    # Algunos sitios usan data-src para lazy loading.
    data_src = _extraer_atributo_xpath(tree, XPATH_IMAGEN, "data-src")
    if data_src:
        return urljoin(BASE_URL, data_src)

    return None


# =================================================
# PERSISTENCIA DE LA NOTICIA
# =================================================


def guardar_noticia(
    url: str,
    titulo: str | None,
    fecha_pub: datetime | None,
    texto: str | None,
    imagen: str | None,
) -> bool:
    """Inserta o actualiza una noticia en noticias_historico."""
    url, titulo, texto, imagen, fecha_pub = normalize_noticia_fields_for_storage(
        url=url,
        titulo=titulo,
        texto=texto,
        imagen=imagen,
        fecha_publicacion=fecha_pub,
    )

    if not titulo or len(titulo.strip()) < MIN_TITLE_LENGTH:
        logger.warning("❌ Sin título o título muy corto")
        return False

    if len((texto or "").strip()) < MIN_TEXT_LENGTH:
        logger.warning(f"❌ Texto insuficiente ({len(texto or '')} chars)")
        return False

    metadata = build_quality_flags(url, titulo, texto, fecha_pub, imagen)

    if TEST_MODE:
        # En modo test mostramos los campos extraídos sin tocar la base de datos.
        print("\n" + "=" * 60)
        print(" MODO TEST - Noticia extraída (no se guarda en DB)")
        print("=" * 60)
        print(f"Fuente:          {FUENTE}")
        print(f"URL:             {url}")
        print(f"Título:          {titulo}")
        print(f"Fecha/Hora:      {fecha_pub}")
        print(f"Imagen:          {imagen}")
        print(f"Longitud texto:  {len(texto or '')} caracteres")
        print(f"Quality flags:   {metadata['quality']}")
        print("-" * 60)
        print("Texto completo extraído:")
        print(texto or "")
        print("=" * 60 + "\n")
        return True

    conn = get_connection()
    cur = conn.cursor()

    try:
        noticia_hash = hashlib.sha256(f"{url}{titulo}".encode("utf-8")).hexdigest()
        hash_contenido = generar_hash_contenido(titulo, texto)

        # Evitamos duplicados por contenido (título + texto).
        cur.execute(
            "SELECT id, url_original FROM noticias_historico WHERE hash_contenido = %s LIMIT 1",
            (hash_contenido,),
        )
        if cur.fetchone():
            logger.info("⚠️ Noticia duplicada detectada")
            return False

        cur.execute(
            """
            INSERT INTO noticias_historico
                (noticia_hash, hash_contenido, fuente, url_original, titulo, texto_completo, url_imagen, fecha_publicacion, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (url_original) DO UPDATE SET
                titulo = EXCLUDED.titulo,
                texto_completo = EXCLUDED.texto_completo,
                url_imagen = EXCLUDED.url_imagen,
                fecha_publicacion = EXCLUDED.fecha_publicacion,
                hash_contenido = EXCLUDED.hash_contenido,
                metadata = EXCLUDED.metadata
            """,
            (
                noticia_hash,
                hash_contenido,
                FUENTE,
                url,
                titulo,
                texto,
                imagen,
                fecha_pub,
                Json(metadata),
            ),
        )

        conn.commit()
        logger.info(f"✅ Noticia guardada: {titulo[:70]}...")
        return True

    finally:
        cur.close()
        conn.close()


# =================================================
# FUNCIÓN PRINCIPAL POR PÁGINA
# (Requerida por run_crawler_template.)
# =================================================


def procesar_pagina(
    url: str,
    importancia_links: str = "baja",
    extraer_noticia: bool = True,
    extraer_links: bool = True,
) -> tuple[bool, bool]:
    """
    Procesa una URL:
      - Si extraer_links=True, descubre y encola links internos.
      - Si extraer_noticia=True y la página es un artículo, extrae y guarda
        la noticia.

    Debe devolver (success, noticia_guardada).
    """
    session = requests.Session()
    response = None

    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(
                url,
                headers=build_random_headers(),
                timeout=30,
            )
            if response.status_code == 200:
                break
            time.sleep(3 * (attempt + 1))
        except Exception as e:
            logger.warning(f"Intento {attempt + 1} fallido: {e}")
            if attempt == MAX_RETRIES - 1:
                raise

    if response is None:
        raise RuntimeError("No se pudo obtener respuesta HTTP")

    soup = BeautifulSoup(response.text, "html.parser")
    logger.info(f"📄 Procesando: {url}")

    # =================================================
    # EXTRAER LINKS
    # =================================================
    enlaces_guardados = 0

    if extraer_links:
        for a in soup.find_all("a", href=True):
            full_url = clean_url(urljoin(url, a["href"]))

            if not full_url.startswith(BASE_URL):
                continue

            if should_exclude(full_url):
                continue

            if save_url(full_url, importancia_links):
                enlaces_guardados += 1
                logger.debug(f"   → URL guardada: {full_url}")

    logger.info(f"🔗 Enlaces nuevos/actualizados en esta página: {enlaces_guardados}")

    if not extraer_noticia:
        return True, False

    # =================================================
    # EXTRAER ARTÍCULO
    # =================================================
    if is_likely_article(soup):
        logger.info("📰 Detectado como ARTÍCULO")

        tree = lhtml.fromstring(str(soup))

        titulo = _extraer_texto_xpath(tree, XPATH_TITULO)
        fecha = extraer_fecha(tree)
        imagen = extraer_imagen(tree)

        # Extraemos el HTML sucio del cuerpo y lo convertimos a texto.
        elementos_cuerpo = tree.xpath(XPATH_TEXTO)
        texto_completo = ""
        if elementos_cuerpo and not isinstance(elementos_cuerpo[0], str):
            html_cuerpo = lhtml.tostring(elementos_cuerpo[0], encoding="unicode")
            texto_completo = html_a_texto(html_cuerpo)

        if titulo and len(texto_completo.strip()) >= MIN_TEXT_LENGTH:
            noticia_guardada = guardar_noticia(
                url=url,
                titulo=titulo,
                fecha_pub=fecha,
                texto=texto_completo,
                imagen=imagen,
            )
            return True, noticia_guardada

    return True, False


# =================================================
# PUNTO DE ENTRADA
# =================================================


def ejecutar_modo_test(url: str = TEST_URL):
    """Procesa una URL de ejemplo sin tocar la base de datos."""
    print("\n" + "=" * 60)
    print(" MODO TEST ACTIVADO")
    print(" No se guardará nada en la base de datos.")
    print(f" URL de prueba: {url}")
    print("=" * 60 + "\n")

    success, noticia_guardada = procesar_pagina(
        url,
        importancia_links="alta",
        extraer_noticia=True,
        extraer_links=True,
    )

    print("\n" + "=" * 60)
    if success and noticia_guardada:
        print("✅ MODO TEST: noticia extraída correctamente.")
    elif success:
        print("⚠️  MODO TEST: la página se procesó pero no se detectó como noticia.")
    else:
        print("❌ MODO TEST: error al procesar la página.")
    print("=" * 60 + "\n")


def main():
    """Conecta el crawler con la plantilla de ejecución común."""
    parser = argparse.ArgumentParser(
        description=f"Crawler para {FUENTE}.",
    )
    parser.add_argument(
        "-t",
        "--test",
        action="store_true",
        help="Modo test: no guarda en la base de datos y muestra los campos extraídos.",
    )
    parser.add_argument(
        "--url",
        default=TEST_URL,
        help=f"URL a usar en modo test (por defecto: {TEST_URL})",
    )
    args = parser.parse_args()

    if args.test:
        global TEST_MODE
        TEST_MODE = True
        ejecutar_modo_test(args.url)
        return

    run_crawler_template(
        fuente=FUENTE,
        base_url=BASE_URL,
        process_page=procesar_pagina,
        max_urls_por_tanda=MAX_URLS_POR_TANDA,
        max_noticias_por_ejecucion=MAX_NOTICIAS_POR_EJECUCION,
        delay_base=DELAY,
        delay_random_min=0.5,
        delay_random_max=2.0,
        logger=logger,
    )


if __name__ == "__main__":
    main()
