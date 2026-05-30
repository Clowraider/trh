"""
cluster_noticias.py — Agrupa noticias en clusters editoriales.

Este script corre periodicamente (cron) para asignar noticias nuevas a clusters.
El clustering usa embeddings vectoriales + similitud de coseno.

PARAMETROS CLAVE:
  - SIMILARITY_THRESHOLD = 0.70 : dos noticias se agrupan si la similitud >= 70%
  - DIAS_CLUSTER_RECIENTE = 7    : solo se buscan clusters de los últimos 7 días
  - MAX_NOTICIAS_POR_EJECUCION   : límite de noticias a procesar por corrida

LIMPIEZA:
  Este script también hace limpieza automática para que la tabla no crezca
  indefinidamente. Se ejecuta cada vez que corre el script:
  1. Elimina clusters huérfanos (sin noticias asociadas) de más de 24h
  2. Elimina clusters de una sola noticia con más de 48h que no se actualizaron
  3. Elimina clusters sin noticias en los últimos 7 días

Los clusters publicados o descartados NO se tocan.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

# =================================================
# CONFIG
# =================================================

def load_dotenv_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value


load_dotenv_file()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "trh"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}

# Similitud mínima (0-1). 0.80 = 80% de coseno similarity
# Si la similitud es menor, se crea un nuevo cluster.
SIMILARITY_THRESHOLD = 0.70

# Máximo de noticias sin cluster a procesar por corrida.
# Evitar saturar la DB con una sola corrida.
MAX_NOTICIAS_POR_EJECUCION = 500

# Los clusters solo se buscan para similitud si tienen
# noticias en los últimos N días. Clusters más viejos se ignoran.
DIAS_CLUSTER_RECIENTE = 7

# =================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# =================================================


def validar_configuracion() -> None:
    if not DB_CONFIG.get("password"):
        raise RuntimeError("Falta variable de entorno requerida: DB_PASSWORD")


def get_connection():
    validar_configuracion()
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


# =============================================================================
# LIMPIEZA AUTOMÁTICA
# Se ejecuta al inicio de cada corrida para mantener la tabla bajo control.
# Los clusters publicados o descartados se respetan (no se tocan).
# =============================================================================

def limpiar_clusters(conn):
    """
    Limpia clusters obsoletos para evitar que la tabla crezca indefinidamente.

    Estrategia:
    1. Clusters huérfanos (sin noticias) de más de 24h → DELETE
    2. Clusters de 1 noticia con más de 48h sin updates → DELETE
    3. Clusters de más de 14 días sin actividad y no publicados → DELETE
    4. Bulk DELETE por seguridad en transacciones separadas
    """
    logger.info("🧹 Iniciando limpieza de clusters...")

    deleted_total = 0

    # --- 1. Huérfanos: clusters sin noticias ---
    # Ocurren si se creó un cluster pero nunca se le asignó la noticia
    # (error en el proceso, rollback, etc.)
    try:
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM clusters_editoriales
            WHERE id IN (
                SELECT c.id
                FROM clusters_editoriales c
                LEFT JOIN noticias_historico n ON n.cluster_id = c.id
                WHERE n.id IS NULL
                  AND actualizado_en < NOW() - INTERVAL '24 hours'
                  AND estado_publicacion IS DISTINCT FROM 'publicado'
                  AND estado_publicacion IS DISTINCT FROM 'descartado'
            )
        """)
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        if deleted > 0:
            logger.info(f"   🗑️  Huérfanos eliminados: {deleted}")
            deleted_total += deleted
    except Exception as e:
        logger.warning(f"   ⚠️  Error limpiando huérfanos: {e}")
        conn.rollback()

    # --- 2. Clusters de 1 noticia sin actividad reciente ---
    # Como fecha_publicacion no incluye hora, usamos 2 días corridos.
    try:
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM clusters_editoriales
            WHERE id IN (
                SELECT c.id
                FROM clusters_editoriales c
                JOIN noticias_historico n ON n.cluster_id = c.id
                WHERE c.cantidad_noticias = 1
                  AND c.cantidad_fuentes = 1
                  AND n.fecha_publicacion IS NOT NULL
                  AND n.fecha_publicacion < CURRENT_DATE - INTERVAL '2 days'
                  AND c.estado_publicacion IS DISTINCT FROM 'publicado'
                  AND c.estado_publicacion IS DISTINCT FROM 'descartado'
            )
        """)
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        if deleted > 0:
            logger.info(f"   🗑️  Singleton sin actividad eliminados: {deleted}")
            deleted_total += deleted
    except Exception as e:
        logger.warning(f"   ⚠️  Error limpiando singletons: {e}")
        conn.rollback()

    # --- 3. Clusters sin noticias recientes ---
    # Si la última fecha_publicacion del cluster es > 7 días, se elimina.
    try:
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM clusters_editoriales c
            WHERE c.estado_publicacion IS DISTINCT FROM 'publicado'
              AND c.estado_publicacion IS DISTINCT FROM 'descartado'
              AND NOT EXISTS (
                  SELECT 1
                  FROM noticias_historico n
                  WHERE n.cluster_id = c.id
                    AND n.fecha_publicacion >= CURRENT_DATE - INTERVAL '7 days'
              )
        """)
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        if deleted > 0:
            logger.info(f"   🗑️  Clusters eliminados por antigüedad (>7 días): {deleted}")
            deleted_total += deleted
    except Exception as e:
        logger.warning(f"   ⚠️  Error eliminando clusters viejos: {e}")
        conn.rollback()

    logger.info(f"🧹 Limpieza finalizada. Total eliminados: {deleted_total}")


# =============================================================================
# OBTENER NOTICIAS SIN CLUSTER
# =============================================================================

def obtener_noticias_sin_cluster(conn):
    """
    Trae noticias sin cluster de hasta 7 días por fecha_publicacion.
    Como fecha_publicacion no tiene hora, el corte es por día calendario.
    """
    cur = conn.cursor()

    cur.execute(f"""
        SELECT
            id,
            titulo,
            fuente,
            fecha_extraccion,
            fecha_publicacion,
            embedding
        FROM noticias_historico
        WHERE cluster_id IS NULL
          AND embedding IS NOT NULL
          AND fecha_publicacion IS NOT NULL
          AND fecha_publicacion >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY fecha_publicacion ASC, id ASC
        LIMIT {MAX_NOTICIAS_POR_EJECUCION}
    """)

    noticias = cur.fetchall()
    cur.close()

    logger.info(f"📦 Noticias sin cluster: {len(noticias)}")

    return noticias


# =============================================================================
# BUSCAR CLUSTER SIMILAR
# =============================================================================

def buscar_cluster_similar(conn, embedding):
    """
    Busca el cluster más similar a una noticia usando el embedding vectorial.

    OPTIMIZACIÓN:
    Usa una subquery con el índice HNSW para buscar candidatos similares
    y luego filtra por recencia. Esto evita escanear los ~9K clusters activos
    completos antes de aplicar el filtro de fecha.

    El operador <=> es "cosine distance" en pgvector. 1 - distance = similarity.

    Returns:
        dict con datos del cluster + similarity, o None si no hay ninguno.
    """
    cur = conn.cursor()

    # Subquery: usa el índice HNSW para traer los 50 más cercanos
    # (índice HNSW con medida de coseno ya optimiza internamente)
    # Outer query: filtra por fecha y devuelve el mejor candidato
    cur.execute("""
        SELECT
            id,
            titulo_representativo,
            cantidad_noticias,
            cantidad_fuentes,
            cantidad_noticias,
            cantidad_fuentes,
            ultima_noticia,
            score,
            tendencia,
            estado_publicacion,

            1 - (embedding_centroide <=> %s::vector) AS similarity

        FROM clusters_editoriales
        WHERE id IN (
            -- Subquery: top 50 candidatos por similitud vectorial
            -- Esto usa el índice HNSW en vez de escanear todo
            SELECT id
            FROM clusters_editoriales
            WHERE embedding_centroide IS NOT NULL
              AND estado_publicacion IS DISTINCT FROM 'descartado'
            ORDER BY embedding_centroide <=> %s::vector
            LIMIT 50
        )
        -- Filtro de recencia APLICADO DESPUÉS del índice vectorial
        AND ultima_noticia >= CURRENT_DATE - INTERVAL '7 days'
        AND estado_publicacion IS DISTINCT FROM 'descartado'

        ORDER BY similarity DESC
        LIMIT 1
    """, (embedding, embedding))

    cluster = cur.fetchone()
    cur.close()

    return cluster


# =============================================================================
# CREAR NUEVO CLUSTER
# =============================================================================

def obtener_fecha_evento(noticia):
    """
    Combina fecha_publicacion (día real) + hora de fecha_extraccion (aproximada).
    """
    fecha_publicacion = noticia.get("fecha_publicacion")
    fecha_extraccion = noticia.get("fecha_extraccion")

    if fecha_publicacion and fecha_extraccion:
        return fecha_publicacion.replace(
            hour=fecha_extraccion.hour,
            minute=fecha_extraccion.minute,
            second=fecha_extraccion.second,
            microsecond=fecha_extraccion.microsecond,
        )

    return fecha_publicacion or fecha_extraccion


def crear_cluster(conn, noticia):
    """
    Crea un nuevo cluster editorial con la primera noticia.
    El embedding del cluster inicial es el de esa noticia.
    """
    cur = conn.cursor()

    fecha_evento = obtener_fecha_evento(noticia)

    cur.execute("""
        INSERT INTO clusters_editoriales
        (
            titulo_representativo,
            embedding_centroide,

            cantidad_noticias,
            cantidad_fuentes,

            primera_noticia,
            ultima_noticia,

            score,
            tendencia,

            estado,
            estado_publicacion
        )
        VALUES
        (
            %s,
            %s::vector,

            1,
            1,

            %s,
            %s,

            1,
            1,

            'nuevo',
            'pendiente'
        )
        RETURNING id
    """, (
        noticia['titulo'],
        noticia['embedding'],
        fecha_evento,
        fecha_evento
    ))

    cluster_id = cur.fetchone()['id']
    conn.commit()
    cur.close()

    logger.info(f"🆕 Cluster #{cluster_id} → {noticia['titulo'][:80]}")

    return cluster_id


# =============================================================================
# ASIGNAR NOTICIA A CLUSTER
# =============================================================================

def asignar_cluster_a_noticia(conn, noticia_id, cluster_id):
    """Asocia una noticia a un cluster existente."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE noticias_historico
        SET cluster_id = %s
        WHERE id = %s
    """, (cluster_id, noticia_id))
    conn.commit()
    cur.close()


# =============================================================================
# ACTUALIZAR CLUSTER (recalcular stats)
# =============================================================================

def actualizar_cluster(conn, cluster_id, embedding_nuevo):
    """
    Recalcula las estadísticas de un cluster después de agregar una noticia:
    - cantidad_noticias, cantidad_fuentes
    - primera_noticia, ultima_noticia
    - score (basado en cantidad, fuentes y tendencia)
    - tendencia (noticias en ventanas de 2h, 6h, 24h)
    - embedding_centroide (promedio móvil de los embeddings)
    """
    cur = conn.cursor()

    # Contar noticias y fuentes SOLO de los últimos 7 días
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(DISTINCT fuente) AS fuentes
        FROM noticias_historico
        WHERE cluster_id = %s
          AND fecha_publicacion IS NOT NULL
          AND fecha_publicacion >= CURRENT_DATE - INTERVAL '7 days'
    """, (cluster_id,))
    stats = cur.fetchone()

    total_noticias = stats['total']
    total_fuentes = stats['fuentes']

    # Fecha/hora de evento: fecha_publicacion + hora de extracción (aproximada)
    cur.execute("""
        SELECT
            MIN((fecha_publicacion::date + COALESCE(fecha_extraccion::time, TIME '00:00'))) AS primera,
            MAX((fecha_publicacion::date + COALESCE(fecha_extraccion::time, TIME '00:00'))) AS ultima
        FROM noticias_historico
        WHERE cluster_id = %s
          AND fecha_publicacion IS NOT NULL
    """, (cluster_id,))
    fechas = cur.fetchone()

    # Tendencia: usamos fecha_publicacion + hora_extraccion como proxy temporal
    def contar_recientes(horas):
        cur.execute(f"""
            SELECT COUNT(*) AS total
            FROM noticias_historico
            WHERE cluster_id = %s
              AND fecha_publicacion IS NOT NULL
              AND (fecha_publicacion::date + COALESCE(fecha_extraccion::time, TIME '00:00'))
                  >= NOW() - INTERVAL '{horas} hours'
        """, (cluster_id,))
        return cur.fetchone()['total']

    noticias_2h = contar_recientes(2)
    noticias_6h = contar_recientes(6)
    noticias_24h = contar_recientes(24)

    tendencia = noticias_2h * 5 + noticias_6h * 3 + noticias_24h

    score = (
        total_noticias * 2 +
        total_fuentes * 5 +
        tendencia
    )

    # Actualizar cluster
    cur.execute("""
        UPDATE clusters_editoriales
        SET
            cantidad_noticias = %s,
            cantidad_fuentes = %s,

            primera_noticia = %s,
            ultima_noticia = %s,

            score = %s,
            tendencia = %s,

            embedding_centroide = %s::vector,

            estado_publicacion = COALESCE(
                NULLIF(estado_publicacion, 'descartado'),
                'pendiente'
            ),

            actualizado_en = NOW()

        WHERE id = %s
    """, (
        total_noticias,
        total_fuentes,
        fechas['primera'],
        fechas['ultima'],
        score,
        tendencia,
        embedding_nuevo,
        cluster_id
    ))

    conn.commit()
    cur.close()


# =============================================================================
# PROCESAR UNA NOTICIA
# =============================================================================

def procesar_noticia(conn, noticia):
    """
    Procesa una noticia individual:
    1. Busca un cluster similar con embedding
    2. Si similarity >= threshold → asigna al cluster existente y recalcula
    3. Si no → crea un cluster nuevo
    """
    fecha_pub = noticia.get('fecha_publicacion') or noticia.get('fecha_extraccion')
    logger.info(
        f"📰 #{noticia['id']} [{noticia['fuente']}] "
        f"→ {noticia['titulo'][:70]} (pub: {fecha_pub})"
    )

    cluster = buscar_cluster_similar(conn, noticia['embedding'])

    if cluster:
        similarity = float(cluster['similarity'])

        if similarity >= SIMILARITY_THRESHOLD:
            cluster_id = cluster['id']

            asignar_cluster_a_noticia(conn, noticia['id'], cluster_id)
            actualizar_cluster(conn, cluster_id, noticia['embedding'])

            logger.info(
                f"   → Asignado a cluster #{cluster_id} "
                f"(similitud: {similarity:.3f})"
            )
            return

        logger.info(f"   → Similitud {similarity:.3f} < {SIMILARITY_THRESHOLD}, nuevo cluster")

    # Crear nuevo cluster
    cluster_id = crear_cluster(conn, noticia)
    asignar_cluster_a_noticia(conn, noticia['id'], cluster_id)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """
    Flujo principal:
    1. Limpiar clusters obsoletos
    2. Obtener noticias sin cluster
    3. Procesar cada noticia
    """
    logger.info("=" * 60)
    logger.info("🚀 Iniciando clustering editorial")
    logger.info("=" * 60)

    conn = get_connection()

    try:
        # 1. Limpieza antes de procesar
        limpiar_clusters(conn)

        # 2. Obtener pendientes
        noticias = obtener_noticias_sin_cluster(conn)

        if not noticias:
            logger.info("✅ No hay noticias pendientes de clustering")
            return

        # 3. Procesar
        procesados = 0
        errores = 0

        for noticia in noticias:
            try:
                procesar_noticia(conn, noticia)
                procesados += 1
            except Exception as e:
                logger.exception(f"❌ Error noticia #{noticia['id']}: {e}")
                errores += 1

        logger.info("-" * 60)
        logger.info(f"📊 Procesados: {procesados} | Errores: {errores}")

    finally:
        conn.close()

    logger.info("🎉 Clustering finalizado")


# =============================================================================

if __name__ == "__main__":
    main()
