# pyright: reportGeneralTypeIssues=false
"""
publicador.py — Genera artículos con IA a partir de un cluster de noticias.

Este script es la SEGUNDA parte del flujo de publicación:

  1. (antes de esto) El crawler juntó noticias y el clustering las agrupó
  2. El panel muestra candidatos → el editor elige uno
  3. El editor hace clic en "Generar con IA" → ESTE script genera el artículo
  4. El panel muestra el resultado → el editor aprueba
  5. publicapress.py publica en WordPress

Funciones exportadas (las usa app.py / el panel):
  - generar_articulo_para_cluster(cluster_id)  → dict con {titulo, resumen, articulo, categoria}
  - guardar_contenido_ia(cluster_id, contenido)  → guarda en la DB
  - obtener_cluster_con_detalles(cluster_id)     → para el panel de preview
"""

import os
import logging
import psycopg2
import requests
import json
import time
from string import Template
from datetime import datetime
from psycopg2.extras import RealDictCursor

from trh.clusters.repository import (
    get_cluster_news_for_user,
    get_or_create_user_cluster_state,
    save_user_cluster_content,
    update_user_cluster_state,
)
from trh.infrastructure.ai_response_parser import extract_json_object
from trh.infrastructure.env_loader import load_project_env
from trh.infrastructure.prompt_loader import load_json_file, load_prompt_text

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

load_project_env()

DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
DB_PORT = int(os.getenv('DB_PORT', '5432'))
DB_NAME = os.getenv('DB_NAME', 'trh')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD')

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')

OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
ARTICLE_WRITER_MAX_TOKENS = int(os.getenv('ARTICLE_WRITER_MAX_TOKENS', '4000'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ARTICLE_WRITER_SYSTEM_PROMPT = load_prompt_text(
    'ARTICLE_WRITER_SYSTEM_PROMPT_FILE',
    logger,
)

REQUIRED_ARTICLE_WRITER_TEMPLATE_PLACEHOLDERS = {
    'sources_block',
    'editorial_guidance_block',
    'categories_list',
}


def _validate_article_categories(value):
    if not isinstance(value, dict):
        raise ValueError("categories file must be a JSON object")

    categories = value.get("categories")
    if not isinstance(categories, list) or len(categories) == 0:
        raise ValueError("categories file must contain a non-empty list of strings")

    if not all(isinstance(cat, str) and cat for cat in categories):
        raise ValueError("all categories must be non-empty strings")

    return categories


ARTICLE_CATEGORIES = load_json_file(
    'ARTICLE_CATEGORIES_FILE',
    logger,
    _validate_article_categories,
)
ARTICLE_CATEGORIES_LIST = ", ".join(ARTICLE_CATEGORIES)


def _extract_template_placeholders(template_text):
    template = Template(template_text)
    placeholders = set()

    for match in template.pattern.finditer(template.template):
        name = match.group('named') or match.group('braced')
        if name:
            placeholders.add(name)

    return placeholders


def _load_article_writer_user_prompt_template():
    template_text = load_prompt_text(
        'ARTICLE_WRITER_USER_PROMPT_FILE',
        logger,
    )
    placeholders = _extract_template_placeholders(template_text)
    missing_placeholders = sorted(
        REQUIRED_ARTICLE_WRITER_TEMPLATE_PLACEHOLDERS - placeholders
    )

    if missing_placeholders:
        raise RuntimeError(
            'ARTICLE_WRITER_USER_PROMPT_FILE is missing required placeholders: '
            + ', '.join(f'${name}' for name in missing_placeholders)
        )

    return template_text


ARTICLE_WRITER_USER_PROMPT_TEMPLATE = _load_article_writer_user_prompt_template()


# =============================================================================
# CONEXIÓN A LA BASE DE DATOS
# =============================================================================

def get_connection():
    """
    Crea y devuelve una conexión a PostgreSQL.
    El cursor usa RealDictCursor para que cada fila venga como dict
    en lugar de tupla — más fácil de leer (row['columna'] en vez de row[3]).
    """
    if not DB_PASSWORD:
        raise RuntimeError('Falta DB_PASSWORD en entorno (.env)')
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor
    )


# =============================================================================
# OBTENER LAS NOTICIAS DE UN CLUSTER
# =============================================================================

def obtener_noticias_cluster(cluster_id):
    """
    Trae todas las noticias que pertenecen a un cluster.
    Se usa para construir el prompt que se envía a la IA.

    Tabla: noticias_historico (schema real, no la tabla 'clusters' inventada)

    Returns:
        Lista de dicts con: fuente, titulo, fecha_publicacion, texto_completo, url_imagen
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # texto_completo es el artículo completo extraído por el crawler
            # (o puede venir solo el lead si el crawler no pudo obtener el body)
            cur.execute("""
                SELECT
                    fuente,
                    titulo,
                    fecha_publicacion,
                    COALESCE(texto_completo, '') AS texto_completo,
                    url_imagen
                FROM noticias_historico
                WHERE cluster_id = %s
                ORDER BY fecha_publicacion DESC, fuente
            """, (cluster_id,))
            return cur.fetchall()
    finally:
        conn.close()


def obtener_noticias_cluster_para_usuario(cluster_id, user_id):
    """Return cluster news filtered to the user's subscribed sources."""
    if user_id is None:
        return obtener_noticias_cluster(cluster_id)
    return get_cluster_news_for_user(cluster_id, user_id)


# =============================================================================
# CONSTRUIR EL PROMPT PARA LA IA
# =============================================================================

def _build_article_sources_block(noticias):
    partes = []

    for i, noticia in enumerate(noticias, 1):
        contenido = noticia['texto_completo']

        partes.append(f"---\nFUENTE {i}: {noticia['fuente']}")
        partes.append(f"TÍTULO: {noticia['titulo']}")

        if noticia['fecha_publicacion']:
            fp = noticia['fecha_publicacion']
            fecha_str = fp.date() if hasattr(fp, 'date') else str(fp)
            partes.append(f"FECHA: {fecha_str}")

        partes.append(f"CONTENIDO: {contenido[:1800]}...\n")

    return "\n".join(partes)


def _build_editorial_guidance_block(nota_ia=''):
    nota_limpia = (nota_ia or '').strip()
    if not nota_limpia:
        return ''

    return """

GUIA EDITORIAL ADICIONAL (opcional, dada por editor):
- Seguí estas indicaciones SOLO si no contradicen las fuentes.
- No uses esta guía para inventar hechos.
{nota}
""".format(nota=nota_limpia)


def construir_prompt(noticias, nota_ia=''):
    """
    Arma el texto (prompt) que se envía a la IA.

    El prompt le dice a la IA:
    - De dónde salen los datos (las noticias del cluster)
    - Cómo debe escribir (estilo periodístico argentino)
    - Qué formato quiere el resultado (JSON con título, resumen, artículo, categoría)

    Se le pasa como máximo ~1800 caracteres de cada noticia
    para no gastar tokens de más.
    """
    prompt_template = Template(ARTICLE_WRITER_USER_PROMPT_TEMPLATE)
    return prompt_template.safe_substitute(
        sources_block=_build_article_sources_block(noticias),
        editorial_guidance_block=_build_editorial_guidance_block(nota_ia),
        categories_list=ARTICLE_CATEGORIES_LIST,
    )


# =============================================================================
# LLAMAR A LA IA (OpenAI-compatible)
# =============================================================================

def _validar_contenido_generado(contenido):
    requeridos = ['titulo', 'resumen', 'articulo', 'categoria']
    faltantes = [k for k in requeridos if not str(contenido.get(k, '')).strip()]
    if faltantes:
        raise ValueError(f"Respuesta IA incompleta. Faltan campos: {', '.join(faltantes)}")


def _is_likely_truncated_response(content):
    if not isinstance(content, str) or not content.strip():
        return False
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(
            line for line in cleaned.splitlines()
            if not line.strip().startswith("```")
        ).strip()
    return cleaned.startswith("{") and not cleaned.rstrip().endswith("}")


def llamar_ia_json(prompt, system_prompt, max_tokens=ARTICLE_WRITER_MAX_TOKENS, temperature=0.6, title="TRH Publicador"):
    if not OPENAI_API_KEY:
        raise RuntimeError('Falta OPENAI_API_KEY en entorno (.env)')

    modelo = OPENAI_MODEL
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        data = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}
        }

        response = requests.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers=headers,
            json=data,
            timeout=70
        )

        response.raise_for_status()
        result = response.json()
        contenido = result['choices'][0]['message']['content'].strip()
        return extract_json_object(contenido)

    except (requests.Timeout, requests.ConnectionError) as e:
        logger.warning("Error de red con la IA: %s", e)
    except (json.JSONDecodeError, ValueError) as e:
        preview = repr(contenido[:240] if isinstance(contenido, str) else "")
        if _is_likely_truncated_response(contenido):
            logger.warning("La respuesta de la IA parece estar truncada: %s preview=%s", e, preview)
        else:
            logger.warning("La IA no devolvió JSON válido: %s preview=%s", e, preview)
    except Exception as e:
        logger.warning("Error con la IA: %s", e)

    raise Exception("El proveedor de IA falló")


def llamar_ia(prompt):
    parsed = llamar_ia_json(
        prompt,
        system_prompt=ARTICLE_WRITER_SYSTEM_PROMPT,
    )
    _validar_contenido_generado(parsed)
    return parsed


def set_requiere_revision_editorial(cluster_id, requiere_revision, nota_editor=None, user_id=None):
    if user_id is not None:
        _set_requiere_revision_editorial_per_user(
            cluster_id, requiere_revision, nota_editor, user_id
        )
        return

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if requiere_revision and nota_editor:
                cur.execute(
                    """
                        SELECT nota_editor
                        FROM clusters_editoriales
                        WHERE id = %s
                        FOR UPDATE
                    """,
                    (cluster_id,),
                )
                row = cur.fetchone()
                existing = (row.get("nota_editor") or "") if row else ""
                separator = "\n\n---\n\n" if existing.strip() else ""
                updated = f"{existing}{separator}{nota_editor}".strip()
                # Keep a generous but bounded size so the textarea remains usable.
                if len(updated) > 4000:
                    updated = updated[-4000:]
                cur.execute(
                    """
                        UPDATE clusters_editoriales
                        SET requiere_revision_editorial = %s,
                            nota_editor = %s,
                            actualizado_en = NOW()
                        WHERE id = %s
                    """,
                    (True, updated, cluster_id),
                )
            else:
                cur.execute(
                    """
                        UPDATE clusters_editoriales
                        SET requiere_revision_editorial = %s,
                            actualizado_en = NOW()
                        WHERE id = %s
                    """,
                    (requiere_revision, cluster_id),
                )
        conn.commit()
    finally:
        conn.close()


def _append_editorial_note(existing, nota_editor):
    separator = "\n\n---\n\n" if existing.strip() else ""
    updated = f"{existing}{separator}{nota_editor}".strip()
    if len(updated) > 4000:
        updated = updated[-4000:]
    return updated


def _set_requiere_revision_editorial_per_user(cluster_id, requiere_revision, nota_editor, user_id):
    fields = {"requiere_revision_editorial": bool(requiere_revision)}
    if requiere_revision and nota_editor:
        state = get_or_create_user_cluster_state(user_id, cluster_id)
        updated = _append_editorial_note(state.get("nota_editor") or "", nota_editor)
        fields["nota_editor"] = updated
    update_user_cluster_state(user_id, cluster_id, **fields)


# =============================================================================
# GUARDAR EL CONTENIDO GENERADO EN LA DB
# =============================================================================

def guardar_contenido_ia(cluster_id, contenido, user_id=None):
    """
    Guarda el contenido generado por la IA.

    Cuando se provee ``user_id`` el contenido se persiste en
    ``user_cluster_states`` (contenido_ia, titulo_representativo y estado
    generado). Sin ``user_id`` se conserva el comportamiento legacy de
    escribir en ``clusters_editoriales`` para compatibilidad con el CLI.

    Args:
        cluster_id: ID del cluster en la DB
        contenido: dict con {titulo, resumen, articulo, categoria}
        user_id: ID del usuario que genera el artículo (opcional)
    """
    if user_id is not None:
        save_user_cluster_content(
            user_id,
            cluster_id,
            titulo_representativo=contenido.get("titulo"),
            contenido_ia=contenido,
        )
        update_user_cluster_state(
            user_id,
            cluster_id,
            estado_publicacion='generado',
        )
        return

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE clusters_editoriales
                SET estado_publicacion = 'generado'
                WHERE id = %s
            """, (cluster_id,))
            cur.execute("""
                UPDATE clusters_editoriales
                SET
                    contenido_ia = %s,
                    actualizado_en = NOW()
                WHERE id = %s
            """, (json.dumps(contenido, ensure_ascii=False), cluster_id))
        conn.commit()
    finally:
        conn.close()


# =============================================================================
# OBTENER CLUSTER CON DETALLES (para el panel de preview)
# =============================================================================

def obtener_cluster_con_detalles(cluster_id):
    """
    Trae un cluster con todas las noticias y el contenido IA generado.
    Lo usa el panel para mostrar el resultado antes de publicar.

    Returns:
        dict con todos los campos del cluster + lista de noticias
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Datos del cluster
            cur.execute("""
                SELECT
                    id,
                    titulo_representativo,
                    contenido_ia,
                    estado_publicacion,
                    foto_principal,
                    url_wp,
                    ultima_publicacion,
                    veces_publicado,
                    cantidad_noticias,
                    cantidad_fuentes,
                    ultima_noticia,
                    score
                FROM clusters_editoriales
                WHERE id = %s
            """, (cluster_id,))
            cluster = cur.fetchone()

            if not cluster:
                return None

            cluster = dict(cluster)

            # Noticias del cluster (para mostrar en preview y para elegir foto)
            cur.execute("""
                SELECT
                    fuente,
                    titulo,
                    url_imagen,
                    url_original,
                    fecha_publicacion
                FROM noticias_historico
                WHERE cluster_id = %s
                ORDER BY fecha_publicacion DESC
            """, (cluster_id,))
            cluster['noticias'] = cur.fetchall()  # type: ignore[index]

            return cluster
    finally:
        conn.close()


# =============================================================================
# FUNCIÓN PRINCIPAL: GENERAR Y GUARDAR
# =============================================================================

def generar_articulo_para_cluster(cluster_id, nota_ia='', user_id=None):
    """
    Función principal que orquesta todo el proceso de generación.

    Flujo:
      1. Obtener noticias del cluster
      2. Construir el prompt
      3. Llamar a la IA
      4. Guardar en la DB
      5. Devolver el resultado

    Esta es la función que llama el panel (app.py) cuando el editor
    hace clic en "Generar con IA".

    Args:
        cluster_id: ID del cluster a procesar
        nota_ia: nota editorial opcional para guiar a la IA
        user_id: ID del usuario que genera; si se provee, el estado de
            publicación se escribe en user_cluster_states.

    Returns:
        dict con {ok: bool, contenido: dict, mensaje: str}
    """
    logger.info("%s", "=" * 80)
    logger.info("🆕 GENERANDO ARTÍCULO PARA CLUSTER ID: %s", cluster_id)
    logger.info("%s", "=" * 80)

    def _set_estado_generando():
        if user_id is not None:
            update_user_cluster_state(
                user_id,
                cluster_id,
                estado_publicacion='generando',
            )
        else:
            conn = get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE clusters_editoriales
                        SET estado_publicacion = 'generando'
                        WHERE id = %s
                    """, (cluster_id,))
                conn.commit()
            finally:
                conn.close()

    def _restore_estado_pendiente(nota_editor=None):
        if user_id is not None:
            fields = {"estado_publicacion": "pendiente"}
            if nota_editor is not None:
                fields["nota_editor"] = nota_editor
            update_user_cluster_state(user_id, cluster_id, **fields)
            return
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                if nota_editor is not None:
                    cur.execute("""
                        UPDATE clusters_editoriales
                        SET nota_editor = %s,
                            actualizado_en = NOW()
                        WHERE id = %s
                    """, (nota_editor, cluster_id))
                else:
                    cur.execute("""
                        UPDATE clusters_editoriales
                        SET estado_publicacion = 'pendiente',
                            actualizado_en = NOW()
                        WHERE id = %s
                    """, (cluster_id,))
            conn.commit()
        finally:
            conn.close()

    # Marcar como "generando" para que el panel no muestre inconsistencias
    _set_estado_generando()

    # 1. Obtener noticias (filtradas por fuentes suscriptas cuando hay usuario)
    noticias = obtener_noticias_cluster_para_usuario(cluster_id, user_id)
    logger.info("📰 Noticias encontradas: %s", len(noticias))

    if not noticias:
        _restore_estado_pendiente()
        return {
            "ok": False,
            "mensaje": "El cluster no tiene noticias asociadas."
        }

    # 2. Construir prompt
    prompt = construir_prompt(noticias, nota_ia=nota_ia)

    # 3. Llamar a la IA
    logger.info("🤖 Llamando a la IA...")
    try:
        resultado = llamar_ia(prompt)
    except Exception as e:
        # Si falla la IA, marcar como pendiente de nuevo
        _restore_estado_pendiente(nota_editor=f"Error IA: {str(e)[:400]}")
        logger.error("❌ Error llamando a la IA: %s", e)
        return {"ok": False, "mensaje": f"Error de IA: {e}"}

    # 4. Guardar en la DB
    guardar_contenido_ia(cluster_id, resultado, user_id=user_id)

    # 5. Mostrar en consola
    logger.info("✅ Artículo generado | Título: %s | Categoría: %s", resultado.get('titulo', 'N/A'), resultado.get('categoria', 'N/A'))

    return {"ok": True, "contenido": resultado}


# =============================================================================
# MAIN — ejecución directa (para testing)
# =============================================================================

if __name__ == "__main__":
    """
    Uso directo: python publicador.py
    Busca un cluster pendiente y genera su artículo.
    Para uso normal, el panel (app.py) llama a generar_articulo_para_cluster().
    """
    import sys

    print("🚀 Iniciando Publicador TRH")
    print("Modo: generación directa (para testing)")

    if len(sys.argv) > 1:
        # python publicador.py <cluster_id>
        cluster_id = int(sys.argv[1])
        resultado = generar_articulo_para_cluster(cluster_id)
    else:
        # Buscar un cluster pendiente automáticamente
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM clusters_editoriales
                    WHERE estado_publicacion = 'pendiente'
                    ORDER BY score DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                if not row:
                    print("No hay clusters pendientes.")
                    sys.exit(0)
                row = dict(row)
                cluster_id = row['id']
                resultado = generar_articulo_para_cluster(cluster_id)
        finally:
            conn.close()

    if resultado["ok"]:
        print("\n✅ Proceso completado correctamente.")
    else:
        print(f"\n❌ Error: {resultado.get('mensaje')}")
