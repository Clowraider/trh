import html
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit, urlunsplit

import psycopg2
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:138.0) Gecko/20100101 Firefox/138.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:138.0) Gecko/20100101 Firefox/138.0",
]

DEFAULT_ARTICLE_REMOVABLE_SELECTORS = (
    "script",
    "style",
    "iframe",
)

PROMO_PREFIX_PUNCTUATION = (":", ";", ",", ".", "!", "?", "¡", "¿", "-", "—")


def _merge_unique_values(values: Iterable[str]) -> tuple[str, ...]:
    merged: list[str] = []

    for value in values:
        normalized = value.strip()
        if normalized and normalized not in merged:
            merged.append(normalized)

    return tuple(merged)


def build_article_removable_selectors(*extra_selectors: str) -> tuple[str, ...]:
    return _merge_unique_values((*DEFAULT_ARTICLE_REMOVABLE_SELECTORS, *extra_selectors))


def build_low_value_paragraph_phrases(*extra_phrases: str) -> tuple[str, ...]:
    return _merge_unique_values(phrase.lower() for phrase in extra_phrases)


def matches_low_value_paragraph_phrase(
    text: str | None,
    phrase: str,
    *,
    require_prefix: bool = False,
) -> bool:
    collapsed = " ".join((text or "").split())
    normalized_phrase = phrase.strip().lower()
    if not collapsed or not normalized_phrase:
        return False

    text_lower = collapsed.lower()

    if not require_prefix:
        return normalized_phrase in text_lower

    if not text_lower.startswith(normalized_phrase):
        return False

    suffix = text_lower[len(normalized_phrase):].lstrip()
    return not suffix or suffix.startswith(PROMO_PREFIX_PUNCTUATION)


def remove_selected_content(container, *, extra_selectors: Iterable[str] = ()) -> None:
    if container is None:
        return

    for selector in build_article_removable_selectors(*extra_selectors):
        for elem in container.select(selector):
            elem.decompose()


def should_skip_paragraph_text(
    text: str | None,
    *,
    min_length: int = 0,
    extra_phrases: Iterable[str] = (),
    leading_phrases: Iterable[str] = (),
) -> bool:
    collapsed = " ".join((text or "").split())
    if not collapsed:
        return True

    if len(collapsed) < min_length:
        return True

    normalized_leading_phrases = set(build_low_value_paragraph_phrases(*leading_phrases))
    phrases = build_low_value_paragraph_phrases(*extra_phrases, *leading_phrases)

    return any(
        matches_low_value_paragraph_phrase(
            collapsed,
            phrase,
            require_prefix=phrase in normalized_leading_phrases,
        )
        for phrase in phrases
    )


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
    normalized = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
    return normalized


def _strip_formatting_tags(value: str) -> str:
    value = re.sub(r"<\s*br\s*/?\s*>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</?(?:p|div|section|article|li|ul|ol|h[1-6]|blockquote)\b[^>]*>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    return html.unescape(value)


def normalize_title_for_storage(title: str | None) -> str:
    if not title:
        return ""

    normalized = _strip_formatting_tags(title)
    return " ".join(normalized.split())


def normalize_text_for_storage(text: str | None) -> str:
    if not text:
        return ""

    normalized = _strip_formatting_tags(text)
    lines = []

    for line in normalized.splitlines():
        collapsed = " ".join(line.split())
        if collapsed:
            lines.append(collapsed)

    return "\n".join(lines)


def normalize_image_url_for_storage(url: str | None) -> str | None:
    if not url:
        return None

    normalized = url.strip()
    return normalized or None


def normalize_fecha_publicacion(fecha: datetime | None) -> datetime | None:
    if fecha is None:
        return None

    if fecha.tzinfo is not None:
        fecha = fecha.replace(tzinfo=None)

    return fecha.replace(second=0, microsecond=0)


def normalize_noticia_fields_for_storage(
    *,
    url: str,
    titulo: str | None,
    texto: str | None,
    imagen: str | None,
    fecha_publicacion: datetime | None,
) -> tuple[str, str, str, str | None, datetime | None]:
    return (
        normalize_url_for_storage(url),
        normalize_title_for_storage(titulo),
        normalize_text_for_storage(texto),
        normalize_image_url_for_storage(imagen),
        normalize_fecha_publicacion(fecha_publicacion),
    )


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


def build_random_headers(accept_language: str = "es-ES,es;q=0.9") -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": accept_language,
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
        process_page(
            base_url,
            importancia_links="alta",
            extraer_noticia=False,
            extraer_links=True,
        )
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
                    extraer_links=False,
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
