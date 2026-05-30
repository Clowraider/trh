import os
import logging
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor


def _load_env_file(path='.env'):
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_env_file()

# =================================================
# CONFIG
# =================================================

DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': os.getenv('DB_NAME', 'trh'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD')
}

MAX_CANDIDATOS = int(os.getenv('MAX_CANDIDATOS', '10'))
VENTANA_DIAS = int(os.getenv('PUBLICABLES_WINDOW_DAYS', '7'))
HORAS_PENALIZACION_PUBLICADO = int(os.getenv('HORAS_PENALIZACION_PUBLICADO', '6'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# =================================================
# DB
# =================================================

def get_connection():
    if not DB_CONFIG['password']:
        raise RuntimeError('Falta DB_PASSWORD en entorno (.env)')
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


# =================================================
# DATA LOADERS (BATCH)
# =================================================

def obtener_clusters_activos(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                c.id,
                c.titulo_representativo,
                c.cantidad_noticias,
                c.cantidad_fuentes,
                c.score,
                c.tendencia,
                c.primera_noticia,
                c.ultima_noticia,
                c.estado,
                c.veces_publicado,
                c.ultima_publicacion
            FROM clusters_editoriales c
            JOIN noticias_historico n ON n.cluster_id = c.id
            WHERE (
                    CASE
                        WHEN n.fecha_publicacion IS NOT NULL THEN
                            (n.fecha_publicacion::date + COALESCE(n.fecha_extraccion::time, TIME '00:00:00'))
                        ELSE n.fecha_extraccion
                    END
                  ) >= NOW() - (%s::int * INTERVAL '1 day')
              AND c.estado_publicacion IS DISTINCT FROM 'descartado'
            GROUP BY c.id, c.titulo_representativo, c.cantidad_noticias,
                     c.cantidad_fuentes, c.score, c.tendencia,
                     c.primera_noticia, c.ultima_noticia,
                     c.estado, c.estado_publicacion,
                     c.veces_publicado, c.ultima_publicacion
            ORDER BY c.ultima_noticia DESC
            """,
            (VENTANA_DIAS,)
        )
        return cur.fetchall()


def obtener_recientes_por_cluster(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                cluster_id,
                COUNT(*) FILTER (
                    WHERE (
                        CASE
                            WHEN fecha_publicacion IS NOT NULL THEN
                                (fecha_publicacion::date + COALESCE(fecha_extraccion::time, TIME '00:00:00'))
                            ELSE fecha_extraccion
                        END
                    ) >= NOW() - INTERVAL '2 hours'
                ) AS noticias_2h,
                COUNT(*) FILTER (
                    WHERE (
                        CASE
                            WHEN fecha_publicacion IS NOT NULL THEN
                                (fecha_publicacion::date + COALESCE(fecha_extraccion::time, TIME '00:00:00'))
                            ELSE fecha_extraccion
                        END
                    ) >= NOW() - INTERVAL '6 hours'
                ) AS noticias_6h,
                COUNT(*) FILTER (
                    WHERE (
                        CASE
                            WHEN fecha_publicacion IS NOT NULL THEN
                                (fecha_publicacion::date + COALESCE(fecha_extraccion::time, TIME '00:00:00'))
                            ELSE fecha_extraccion
                        END
                    ) >= NOW() - INTERVAL '24 hours'
                ) AS noticias_24h
            FROM noticias_historico
            WHERE (
                    CASE
                        WHEN fecha_publicacion IS NOT NULL THEN
                            (fecha_publicacion::date + COALESCE(fecha_extraccion::time, TIME '00:00:00'))
                        ELSE fecha_extraccion
                    END
                  ) >= NOW() - (%s::int * INTERVAL '1 day')
              AND cluster_id IS NOT NULL
            GROUP BY cluster_id
            """,
            (VENTANA_DIAS,)
        )
        return {
            r['cluster_id']: {
                'noticias_2h': r['noticias_2h'],
                'noticias_6h': r['noticias_6h'],
                'noticias_24h': r['noticias_24h']
            }
            for r in cur.fetchall()
        }


def obtener_prioridades(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT keyword, tipo, puntos
            FROM keywords_prioridad
            WHERE activo = TRUE
            """
        )
        return cur.fetchall()


def obtener_keywords_por_cluster(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT
                nh.cluster_id,
                nk.tipo,
                nk.valor_normalizado
            FROM noticias_keywords nk
            JOIN noticias_historico nh ON nh.id = nk.noticia_id
            WHERE nh.cluster_id IS NOT NULL
              AND (
                    CASE
                        WHEN nh.fecha_publicacion IS NOT NULL THEN
                            (nh.fecha_publicacion::date + COALESCE(nh.fecha_extraccion::time, TIME '00:00:00'))
                        ELSE nh.fecha_extraccion
                    END
                  ) >= NOW() - (%s::int * INTERVAL '1 day')
            """,
            (VENTANA_DIAS,)
        )
        out = {}
        for row in cur.fetchall():
            out.setdefault(row['cluster_id'], []).append({
                'tipo': row['tipo'],
                'valor_normalizado': row['valor_normalizado']
            })
        return out


def obtener_noticias_fuente_por_cluster(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH ranked AS (
                SELECT
                    id,
                    cluster_id,
                    fuente,
                    titulo,
                    url_original,
                    fecha_extraccion,
                    ROW_NUMBER() OVER (
                        PARTITION BY cluster_id
                        ORDER BY
                            CASE
                                WHEN fecha_publicacion IS NOT NULL THEN
                                    (fecha_publicacion::date + COALESCE(fecha_extraccion::time, TIME '00:00:00'))
                                ELSE fecha_extraccion
                            END DESC
                    ) AS rn
                FROM noticias_historico
                WHERE cluster_id IS NOT NULL
                  AND (
                        CASE
                            WHEN fecha_publicacion IS NOT NULL THEN
                                (fecha_publicacion::date + COALESCE(fecha_extraccion::time, TIME '00:00:00'))
                            ELSE fecha_extraccion
                        END
                      ) >= NOW() - (%s::int * INTERVAL '1 day')
            )
            SELECT id, cluster_id, fuente, titulo, url_original, fecha_extraccion
            FROM ranked
            WHERE rn <= 15
            """,
            (VENTANA_DIAS,)
        )
        out = {}
        for row in cur.fetchall():
            out.setdefault(row['cluster_id'], []).append({
                'id': row['id'],
                'fuente': row['fuente'],
                'titulo': row['titulo'],
                'url_original': row['url_original'],
                'fecha_extraccion': row['fecha_extraccion']
            })
        return out


# =================================================
# SCORE
# =================================================

def _ahora_utc():
    return datetime.now(timezone.utc)


def _horas_desde(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (_ahora_utc() - dt).total_seconds() / 3600


def calcular_score_prioridades(cluster_keywords, prioridades):
    score = 0
    razones = []
    keywords_cluster = {k['valor_normalizado'].lower().strip() for k in cluster_keywords if k.get('valor_normalizado')}

    for prioridad in prioridades:
        keyword = (prioridad['keyword'] or '').lower().strip()
        if keyword and keyword in keywords_cluster:
            puntos = prioridad['puntos']
            score += puntos
            razones.append(f"+{puntos} prioridad: {keyword}")

    return score, razones


def calcular_score_editorial(cluster, recientes, cluster_keywords, prioridades):
    score = 0
    razones = []

    score += cluster['cantidad_noticias'] * 2
    razones.append(f"{cluster['cantidad_noticias']} noticias")

    score += cluster['cantidad_fuentes'] * 8
    razones.append(f"{cluster['cantidad_fuentes']} fuentes")

    tendencia = cluster.get('tendencia') or 0
    score += tendencia * 4
    razones.append(f"tendencia={tendencia}")

    noticias_2h = recientes.get('noticias_2h', 0)
    noticias_6h = recientes.get('noticias_6h', 0)
    noticias_24h = recientes.get('noticias_24h', 0)

    score += noticias_2h * 10
    score += noticias_6h * 5
    score += noticias_24h * 2

    if noticias_2h > 0:
        razones.append(f"{noticias_2h} noticias en 2h")
    if noticias_6h > 0:
        razones.append(f"{noticias_6h} noticias en 6h")

    if noticias_2h >= 5:
        score += 50
        razones.append('BONUS crecimiento explosivo')

    if cluster['cantidad_fuentes'] >= 5:
        score += 40
        razones.append('BONUS múltiples medios')

    score_prioridades, razones_prioridades = calcular_score_prioridades(cluster_keywords, prioridades)
    score += score_prioridades
    razones.extend(razones_prioridades)

    if cluster['cantidad_fuentes'] <= 1:
        score -= 20
        razones.append('PENALIZACIÓN fuente única')

    horas_publicado = _horas_desde(cluster.get('ultima_publicacion'))
    if horas_publicado is not None and horas_publicado < HORAS_PENALIZACION_PUBLICADO:
        score -= 40
        razones.append('PENALIZACIÓN publicado recientemente')

    horas_ultima = _horas_desde(cluster.get('ultima_noticia'))
    if horas_ultima is not None and horas_ultima > 24:
        score -= 60
        razones.append('PENALIZACIÓN cluster viejo')

    horas_primera = _horas_desde(cluster.get('primera_noticia'))
    if horas_primera is not None and horas_primera <= 6:
        score += 25
        razones.append('BONUS historia nueva')

    return {
        'score_final': round(score, 2),
        'razones': razones,
        'noticias_2h': noticias_2h,
        'noticias_6h': noticias_6h,
        'noticias_24h': noticias_24h
    }


# =================================================
# CANDIDATOS
# =================================================

def generar_candidatos(conn):
    clusters = obtener_clusters_activos(conn)
    logger.info(f"📦 Clusters activos encontrados: {len(clusters)}")

    recientes_map = obtener_recientes_por_cluster(conn)
    keywords_map = obtener_keywords_por_cluster(conn)
    noticias_map = obtener_noticias_fuente_por_cluster(conn)
    prioridades = obtener_prioridades(conn)

    candidatos = []

    for cluster in clusters:
        try:
            recientes = recientes_map.get(cluster['id'], {'noticias_2h': 0, 'noticias_6h': 0, 'noticias_24h': 0})
            cluster_keywords = keywords_map.get(cluster['id'], [])

            resultado = calcular_score_editorial(cluster, recientes, cluster_keywords, prioridades)
            cluster['score_editorial'] = resultado['score_final']
            cluster['razones'] = resultado['razones']
            cluster['noticias_2h'] = resultado['noticias_2h']
            cluster['noticias_6h'] = resultado['noticias_6h']
            cluster['noticias_24h'] = resultado['noticias_24h']
            cluster['noticias_fuente'] = noticias_map.get(cluster['id'], [])
            cluster['keywords'] = cluster_keywords
            candidatos.append(cluster)
        except Exception as e:
            logger.exception(f"❌ Error calculando cluster {cluster['id']}: {e}")

    candidatos.sort(key=lambda x: x['score_editorial'], reverse=True)
    return candidatos[:MAX_CANDIDATOS]


# =================================================
# DEBUG CLI
# =================================================

def mostrar_candidatos(candidatos):
    print("\n" + "=" * 100)
    print("📰 CANDIDATOS EDITORIALES")
    print("=" * 100 + "\n")

    for i, cluster in enumerate(candidatos, start=1):
        print(f"{i}. CLUSTER #{cluster['id']}")
        print("-" * 100)
        print(f"Título: {cluster['titulo_representativo']}")
        print(f"Score editorial: {cluster['score_editorial']}")
        print(f"Noticias: {cluster['cantidad_noticias']}")
        print(f"Fuentes: {cluster['cantidad_fuentes']}")
        print(f"Tendencia: {cluster['tendencia']}")
        print(f"Última noticia: {cluster['ultima_noticia']}")
        print(f"Veces publicado: {cluster['veces_publicado']}")


def main():
    logger.info('🚀 Iniciando selección editorial')
    conn = get_connection()
    try:
        candidatos = generar_candidatos(conn)
        mostrar_candidatos(candidatos)
        logger.info(f"✅ Candidatos generados: {len(candidatos)}")
    finally:
        conn.close()
    logger.info('🎉 Proceso finalizado')


if __name__ == '__main__':
    main()
