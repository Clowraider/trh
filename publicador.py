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
from psycopg2 import errors as psycopg2_errors
import requests
import json
import time
from datetime import datetime
from psycopg2.extras import RealDictCursor

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

def _load_env_file(path='.env'):
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
DB_PORT = int(os.getenv('DB_PORT', '5432'))
DB_NAME = os.getenv('DB_NAME', 'trh')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD')

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_URL = os.getenv('OPENROUTER_URL', 'https://openrouter.ai/api/v1/chat/completions')

MODEL_PRINCIPAL = os.getenv('OPENROUTER_MODEL_PRIMARY', 'openrouter/free')
MODEL_FALLBACK = os.getenv('OPENROUTER_MODEL_FALLBACK', 'deepseek/deepseek-v4-flash')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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


# =============================================================================
# CONSTRUIR EL PROMPT PARA LA IA
# =============================================================================

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
    partes = ["Genera un artículo unificado basado SOLO en la información de las siguientes fuentes:\n"]

    for i, noticia in enumerate(noticias, 1):
        # contenido: texto completo si existe, sino el lead (si hay)
        contenido = noticia['texto_completo']

        partes.append(f"---\nFUENTE {i}: {noticia['fuente']}")
        partes.append(f"TÍTULO: {noticia['titulo']}")

        if noticia['fecha_publicacion']:
            # Mostrar solo la fecha (sin hora), más legible
            fp = noticia['fecha_publicacion']
            fecha_str = fp.date() if hasattr(fp, 'date') else str(fp)
            partes.append(f"FECHA: {fecha_str}")

        # Truncar a 1800 chars para no mandar texto innecesario a la IA
        partes.append(f"CONTENIDO: {contenido[:1800]}...\n")

    partes.append("""
INSTRUCCIONES IMPORTANTES:
- Usa ÚNICAMENTE la información presente en las fuentes proporcionadas.
- NO inventes datos, números, nombres, hechos ni conclusiones que no estén explícitamente en las noticias.

RESOLUCIÓN DE IDENTIDAD Y HECHOS:
- Antes de redactar, unifica entidades y hechos equivalentes entre fuentes.
- Si dos fuentes describen el mismo hecho/persona con diferencias menores (ej: fecha 30 vs 31, edad 84 vs 85), trátalo como UN solo caso, no como casos distintos.
- No infieras múltiples víctimas/protagonistas por variaciones menores de edad, fecha u hora.
- Solo separa en hechos/personas distintas si hay evidencia clara de que sean eventos diferentes.

MANEJO DE CONTRADICCIONES:
- Prioriza el dato respaldado por más fuentes.
- Si hay empate o no se puede resolver, expresa incertidumbre de forma neutral (ej: "84/85 años", "entre el 30 y el 31").
- Cuando exista contradicción, expresa la incertidumbre de forma neutral sin duplicar el caso. En toda la salida, no nombres fuentes ni medios en el título, el resumen o el artículo.

CONSISTENCIA TEMPORAL:
- Normaliza referencias temporales ambiguas (ej: "ayer", "anoche") al contexto del hecho cuando sea posible.
- Si no es posible fijar una fecha única, usa una ventana temporal neutral.

CALIDAD DE SALIDA:
- Escribe en español neutro de Argentina, claro, profesional y objetivo.
- Une la información de forma coherente y natural.
- Antes de responder, verifica internamente:
  1) que no duplicaste protagonistas,
  2) que no hay números incompatibles sin aclaración,
  3) que cada afirmación relevante está sustentada por al menos una fuente.

Genera la respuesta EXACTAMENTE en este formato JSON:

{
  "titulo": "Título atractivo, periodístico y preciso",
  "resumen": "Lead de máximo 280 caracteres",
  "articulo": "Cuerpo completo de la noticia bien estructurado en párrafos",
  "categoria": "Una sola categoría de esta lista: Salud, Política, Deportes, Cultura, Economía, Sociedad, Turismo, Seguridad, Educación"
}

No agregues ningún texto fuera del JSON.""")

    nota_limpia = (nota_ia or '').strip()
    if nota_limpia:
        partes.append("""

GUIA EDITORIAL ADICIONAL (opcional, dada por editor):
- Seguí estas indicaciones SOLO si no contradicen las fuentes.
- No uses esta guía para inventar hechos.
""")
        partes.append(nota_limpia)

    return "\n".join(partes)


# =============================================================================
# LLAMAR A LA IA (OpenRouter)
# =============================================================================

def _validar_contenido_generado(contenido):
    requeridos = ['titulo', 'resumen', 'articulo', 'categoria']
    faltantes = [k for k in requeridos if not str(contenido.get(k, '')).strip()]
    if faltantes:
        raise ValueError(f"Respuesta IA incompleta. Faltan campos: {', '.join(faltantes)}")


def llamar_ia_json(prompt, system_prompt, max_tokens=2200, temperature=0.6, title="TRH Publicador"):
    if not OPENROUTER_API_KEY:
        raise RuntimeError('Falta OPENROUTER_API_KEY en entorno (.env)')

    models = [MODEL_PRINCIPAL, MODEL_FALLBACK]

    for modelo in models:
        for intento in range(1, 3):
            try:
                headers = {
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://trh.local",
                    "X-Title": title
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
                    OPENROUTER_URL,
                    headers=headers,
                    json=data,
                    timeout=70
                )

                if response.status_code == 429:
                    logger.warning("Cuota excedida en %s (intento %s)", modelo, intento)
                    time.sleep(2 * intento)
                    continue

                response.raise_for_status()
                result = response.json()
                contenido = result['choices'][0]['message']['content'].strip()
                return json.loads(contenido)

            except (requests.Timeout, requests.ConnectionError) as e:
                logger.warning("Error de red con %s (intento %s): %s", modelo, intento, e)
                time.sleep(2 * intento)
            except json.JSONDecodeError:
                logger.warning("La IA no devolvió JSON válido con %s (intento %s)", modelo, intento)
                time.sleep(2 * intento)
            except ValueError as e:
                logger.warning("Respuesta inválida con %s (intento %s): %s", modelo, intento, e)
                time.sleep(2 * intento)
            except Exception as e:
                logger.warning("Error con modelo %s (intento %s): %s", modelo, intento, e)
                time.sleep(2 * intento)

    raise Exception("Todos los modelos de IA fallaron")


def llamar_ia(prompt):
    parsed = llamar_ia_json(
        prompt,
        system_prompt=(
            "Eres un redactor de noticias profesional. "
            "Tu regla más importante es: NUNCA inventes información. "
            "Solo puedes usar datos que aparezcan explícitamente en las fuentes proporcionadas. "
            "Debes unificar el mismo hecho/persona entre fuentes aunque haya diferencias menores (edad, día exacto), "
            "evitar duplicar protagonistas salvo evidencia clara de casos distintos, "
            "y explicitar contradicciones con redacción neutral (ej: 'según X... mientras que Y...')."
        ),
    )
    _validar_contenido_generado(parsed)
    return parsed


def set_requiere_revision_editorial(cluster_id, requiere_revision):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
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
    except psycopg2_errors.UndefinedColumn:
        conn.rollback()
        logger.warning(
            "No existe clusters_editoriales.requiere_revision_editorial; ejecutar migración manual."
        )
    finally:
        conn.close()


# =============================================================================
# GUARDAR EL CONTENIDO GENERADO EN LA DB
# =============================================================================

def guardar_contenido_ia(cluster_id, contenido):
    """
    Guarda el contenido generado por la IA en el cluster correspondiente.

    Campos actualizados en clusters_editoriales:
    - contenido_ia: JSON con {titulo, resumen, articulo, categoria}
    - estado_publicacion: 'generado'
    - actualizado_en: ahora

    Args:
        cluster_id: ID del cluster en la DB
        contenido: dict con {titulo, resumen, articulo, categoria}
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE clusters_editoriales
                SET
                    contenido_ia = %s,
                    estado_publicacion = 'generado',
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

def generar_articulo_para_cluster(cluster_id, nota_ia=''):
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

    Returns:
        dict con {ok: bool, contenido: dict, mensaje: str}
    """
    logger.info("%s", "=" * 80)
    logger.info("🆕 GENERANDO ARTÍCULO PARA CLUSTER ID: %s", cluster_id)
    logger.info("%s", "=" * 80)

    # Marcar como "generando" para que el panel no muestre inconsistencias
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

    # 1. Obtener noticias
    noticias = obtener_noticias_cluster(cluster_id)
    logger.info("📰 Noticias encontradas: %s", len(noticias))

    if not noticias:
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
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE clusters_editoriales
                    SET estado_publicacion = 'pendiente',
                        nota_editor = %s,
                        actualizado_en = NOW()
                    WHERE id = %s
                """, (f"Error IA: {str(e)[:400]}", cluster_id))
            conn.commit()
        finally:
            conn.close()

        logger.error("❌ Error llamando a la IA: %s", e)
        return {"ok": False, "mensaje": f"Error de IA: {e}"}

    # 4. Guardar en la DB
    guardar_contenido_ia(cluster_id, resultado)

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
