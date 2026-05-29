import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg2
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "trh"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )


def normalize_url_for_storage(url: str) -> str:
    if not url:
        return url

    parsed = urlsplit(url.strip())
    tracking_prefixes = (
        "utm_",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "_hs",
        "vero_",
    )

    clean_pairs = []
    for k, v in parse_qsl(parsed.query, keep_blank_values=True):
        lk = k.lower()
        if lk.startswith(tracking_prefixes):
            continue
        clean_pairs.append((k, v))

    clean_query = urlencode(clean_pairs, doseq=True)
    normalized = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), clean_query, ""))
    return normalized


def normalize_fecha_publicacion(fecha: datetime | None) -> datetime | None:
    if fecha is None:
        return None

    if fecha.tzinfo is not None:
        fecha = fecha.replace(tzinfo=None)

    return fecha.replace(second=0, microsecond=0)


def build_quality_flags(url: str | None, titulo: str | None, texto: str | None, fecha: datetime | None, imagen: str | None) -> dict:
    titulo_len = len((titulo or "").strip())
    texto_len = len((texto or "").strip())

    return {
        "quality": {
            "titulo_ok": titulo_len >= 20,
            "texto_ok": texto_len >= 300,
            "fecha_ok": fecha is not None,
            "imagen_ok": bool((imagen or "").strip()),
            "url_limpia_ok": "utm_" not in (url or "") and "fbclid=" not in (url or "") and "gclid=" not in (url or ""),
            "titulo_len": titulo_len,
            "texto_len": texto_len,
        }
    }


def _obtener_pendientes_priorizados(fuente: str, max_urls_por_tanda: int, faltan: int) -> list[tuple[int, str]]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        limite = min(max_urls_por_tanda, faltan)

        cur.execute(
            """
            SELECT id, url
            FROM urls
            WHERE estado = 0
              AND fuente = %s
              AND importancia = 'alta'
            ORDER BY id ASC
            LIMIT %s
            """,
            (fuente, limite),
        )
        pending = cur.fetchall()

        if pending:
            return pending

        cur.execute(
            """
            SELECT id, url
            FROM urls
            WHERE estado = 0
              AND fuente = %s
              AND COALESCE(importancia, 'baja') = 'baja'
            ORDER BY id ASC
            LIMIT %s
            """,
            (fuente, limite),
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def _marcar_url_procesada(url_id: int, success: bool):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE urls
            SET estado = %s,
                fecha_procesado = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (1 if success else 2, url_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def run_crawler_template(
    *,
    fuente: str,
    base_url: str,
    process_page: Callable[..., tuple[bool, bool]],
    max_urls_por_tanda: int,
    max_noticias_por_ejecucion: int,
    delay_base: float,
    delay_random_min: float,
    delay_random_max: float,
    logger,
):
    logger.info(f"🚀 Iniciando crawler plantilla: {fuente} - {base_url}")

    try:
        logger.info("🏠 Procesando BASE_URL primero")
        process_page(base_url, importancia_links="alta", extraer_noticia=False)
    except Exception as e:
        logger.error(f"❌ Error procesando BASE_URL: {e}")

    noticias_guardadas = 0

    while noticias_guardadas < max_noticias_por_ejecucion:
        faltan = max_noticias_por_ejecucion - noticias_guardadas
        pending = _obtener_pendientes_priorizados(fuente, max_urls_por_tanda, faltan)

        if not pending:
            logger.info("🎉 No hay más URLs pendientes.")
            break

        for url_id, url in pending:
            logger.info(f"🔄 Procesando ({url_id})")

            try:
                success, noticia_guardada = process_page(
                    url,
                    importancia_links="baja",
                    extraer_noticia=True,
                )
            except Exception as e:
                logger.error(f"❌ Error procesando {url}: {e}")
                success = False
                noticia_guardada = False

            _marcar_url_procesada(url_id, success)

            if noticia_guardada:
                noticias_guardadas += 1

            if noticias_guardadas >= max_noticias_por_ejecucion:
                logger.info(f"🎯 Cupo alcanzado: {noticias_guardadas}/{max_noticias_por_ejecucion}")
                break

            time.sleep(delay_base + random.uniform(delay_random_min, delay_random_max))
