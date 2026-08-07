# pyright: reportMissingImports=false
"""TRH editorial control panel Flask app."""

import sys
import os
import json
import uuid
import logging
import secrets
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from trh.infrastructure.env_loader import load_project_env

load_project_env()

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    make_response
)
from PIL import Image
from pipeline.seleccionar_publicables import get_connection, generar_candidatos
from trh.editorial.editor_jefe_ia import (
    FeatureError, OpenAICompatibleSelectionClient, build_editorial_context,
    delete_saved_recommendation, load_saved_recommendations, parse_maximum,
    parse_minimum_editorial_score, record_context_failure, save_recommendations,
    select_recommendations,
)
from trh.editorial.editorial_control import generate_article_with_editorial_control
from trh.infrastructure.html_sanitizer import sanitize_article_markup
from trh.publication import publicador, publicapress
from trh.publication.publicador import ARTICLE_CATEGORIES

logger = logging.getLogger(__name__)


def _load_secret_key():
    key = os.getenv("SECRET_KEY")
    if key:
        return key
    if os.getenv("FLASK_ENV", "production").lower() == "development":
        logger.warning(
            "SECRET_KEY no está configurado. Generando clave temporal solo para desarrollo. "
            "Configure SECRET_KEY en .env antes de desplegar en producción."
        )
        return secrets.token_hex(32)
    raise RuntimeError("SECRET_KEY es obligatorio en producción. Configúrelo en el entorno.")


app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "templates"),
    static_folder=str(PROJECT_ROOT / "static"),
)

app.secret_key = _load_secret_key()
app.config["SESSION_LIFETIME_HOURS"] = int(os.getenv("SESSION_LIFETIME_HOURS", "24"))
app.config["AUTH_REQUIRED"] = os.getenv("AUTH_REQUIRED", "True").lower() in ("true", "1", "yes")

TIPOS_KEYWORD_PERMITIDOS = ('keyword', 'persona', 'lugar', 'organizacion')

TEMP_UPLOAD_BASE_DIR = str(PROJECT_ROOT / 'static' / 'uploads' / 'tmp')
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8MB por imagen
MAX_UPLOAD_FILES = 6
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES * MAX_UPLOAD_FILES


def _update_cluster_nota_ia(cluster_id, nota_ia):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                    UPDATE clusters_editoriales
                    SET nota_ia = %s,
                        actualizado_en = NOW()
                    WHERE id = %s
                """,
                (nota_ia, cluster_id),
            )
        conn.commit()
    finally:
        conn.close()


def _generate_cluster_article(cluster_id, nota_ia=None, cluster=None, allowed_states=None, generator=None):
    cluster = cluster or obtener_cluster_db(cluster_id)
    if not cluster:
        return {"status": "missing"}

    estado = cluster.get('estado_publicacion') or 'pendiente'
    allowed_states = allowed_states or ('pendiente', 'generando', 'generado')
    if estado not in allowed_states:
        return {"status": "skipped", "state": estado}

    stored_nota_ia = (cluster.get('nota_ia') or '').strip()
    effective_nota_ia = stored_nota_ia if nota_ia is None else nota_ia.strip()

    if nota_ia is not None and effective_nota_ia != stored_nota_ia:
        _update_cluster_nota_ia(cluster_id, effective_nota_ia)

    generator = generator or app.config.get(
        "EDITOR_JEFE_ARTICLE_GENERATOR", publicador.generar_articulo_para_cluster
    )
    try:
        resultado = generator(cluster_id, nota_ia=effective_nota_ia)
    except Exception as exc:
        return {"status": "failed", "message": str(exc)}

    if resultado.get("ok"):
        return {"status": "generated", "result": resultado}
    return {
        "status": "failed",
        "message": resultado.get('mensaje', 'Error desconocido'),
    }


def _cluster_upload_dir(cluster_id):
    return os.path.join(TEMP_UPLOAD_BASE_DIR, f'cluster_{cluster_id}')


def _ensure_cluster_upload_dir(cluster_id):
    path = _cluster_upload_dir(cluster_id)
    os.makedirs(path, exist_ok=True)
    return path


def _es_imagen_valida(contenido):
    try:
        from io import BytesIO
        with Image.open(BytesIO(contenido)) as img:
            img.verify()
        return True
    except Exception:
        return False


def _listar_fotos_manuales(cluster_id):
    path = _cluster_upload_dir(cluster_id)
    if not os.path.isdir(path):
        return []

    fotos = []
    for name in sorted(os.listdir(path)):
        _, ext = os.path.splitext(name.lower())
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            continue
        fotos.append(f"/static/uploads/tmp/cluster_{cluster_id}/{name}")
    return fotos


def _urls_fotos_permitidas(cluster_id, noticias=None):
    noticias = noticias if noticias is not None else obtener_noticias_cluster(cluster_id)
    urls_noticias = [
        (n.get('url_imagen') or '').strip()
        for n in noticias
        if (n.get('url_imagen') or '').strip()
    ]
    return set(urls_noticias + _listar_fotos_manuales(cluster_id))


def _seleccion_fotos_desde_form(cluster_id, form, noticias=None):
    urls_permitidas = _urls_fotos_permitidas(cluster_id, noticias=noticias)

    foto_principal = (form.get('foto_principal', '') or '').strip()
    if foto_principal and foto_principal not in urls_permitidas:
        foto_principal = ''

    fotos_secundarias = [
        (u or '').strip() for u in form.getlist('fotos_secundarias')
        if (u or '').strip() and (u or '').strip() in urls_permitidas
    ]

    fotos_limpias = []
    for url in fotos_secundarias:
        if url == foto_principal:
            continue
        if url not in fotos_limpias:
            fotos_limpias.append(url)

    return foto_principal, fotos_limpias[:2]


def _guardar_seleccion_fotos(cluster_id, foto_principal, fotos_secundarias):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE clusters_editoriales
                SET foto_principal = %s,
                    fotos_secundarias = %s::jsonb,
                    actualizado_en = NOW()
                WHERE id = %s
            """, (foto_principal, json.dumps(fotos_secundarias, ensure_ascii=False), cluster_id))
        conn.commit()
    finally:
        conn.close()


def _enriquecer_recomendaciones_guardadas_para_publicacion(saved_recommendations):
    enriched = []
    for item in saved_recommendations:
        enriched_item = dict(item)
        cluster = None
        try:
            cluster = obtener_cluster_db(enriched_item['cluster_id'])
            if cluster:
                for field in (
                    'estado_publicacion',
                    'requiere_revision_editorial',
                    'url_wp',
                    'contenido_ia',
                    'foto_principal',
                    'fotos_secundarias',
                    'fotos_manuales',
                ):
                    if field in cluster:
                        enriched_item[field] = cluster.get(field)
        except Exception:
            record_context_failure()

        estado = enriched_item.get('estado_publicacion') or 'pendiente'
        if estado == 'generado' and cluster:
            enriched_item['quick_publish_cluster'] = cluster
            enriched_item['quick_publish_news'] = obtener_noticias_cluster(
                enriched_item['cluster_id']
            )
        enriched.append(enriched_item)
    return enriched


def _enriquecer_items_con_keywords_panel(
    items,
    priority_keywords_rows,
    keywords_por_cluster=None,
    source_field='keywords',
):
    raw_keywords_por_cluster = {}

    for item in items:
        cluster_id = item.get('cluster_id')
        if cluster_id is None:
            continue

        keywords = None
        if keywords_por_cluster and cluster_id in keywords_por_cluster:
            keywords = keywords_por_cluster.get(cluster_id)
        elif source_field:
            keywords = item.get(source_field)

        if keywords:
            raw_keywords_por_cluster[cluster_id] = keywords

    highlighted_keywords = build_cluster_keywords_for_panel(
        raw_keywords_por_cluster,
        priority_keywords_rows,
    )

    enriched = []
    for item in items:
        enriched_item = dict(item)
        enriched_item['cluster_keywords'] = highlighted_keywords.get(
            item.get('cluster_id'),
            [],
        )
        enriched.append(enriched_item)

    return enriched


# =============================================================================
# HELPERS DE BASE DE DATOS
# =============================================================================

def _normalizar_fotos_secundarias(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def obtener_cluster_db(cluster_id):
    """
    Obtiene un cluster por su ID con todas las columnas relevantes.
    Devuelve None si no existe.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    titulo_representativo,
                    contenido_ia,
                    estado_publicacion,
                    requiere_revision_editorial,
                    foto_principal,
                    fotos_secundarias,
                    url_wp,
                    nota_editor,
                    nota_ia,
                    ultima_publicacion,
                    veces_publicado,
                    cantidad_noticias,
                    cantidad_fuentes,
                    primera_noticia,
                    ultima_noticia,
                    score,
                    estado,
                    actualizado_en
                FROM clusters_editoriales
                WHERE id = %s
            """, (cluster_id,))
            row = cur.fetchone()
            if row:
                row['fotos_secundarias'] = _normalizar_fotos_secundarias(row.get('fotos_secundarias'))
                row['fotos_manuales'] = _listar_fotos_manuales(cluster_id)
            return row
    finally:
        conn.close()


def obtener_noticias_cluster(cluster_id):
    """
    Obtiene todas las noticias de un cluster para mostrar en el detalle.
    Incluye url_imagen para la selección de foto principal.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    fuente,
                    titulo,
                    url_original,
                    url_imagen,
                    fecha_publicacion,
                    fecha_extraccion
                FROM noticias_historico
                WHERE cluster_id = %s
                ORDER BY fecha_publicacion DESC, fuente
            """, (cluster_id,))
            return cur.fetchall()
    finally:
        conn.close()


def _normalize_fotos_secundarias(value):
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return []


def _split_requires_pending_publication_state(estado_publicacion):
    estado = (estado_publicacion or 'pendiente').strip() or 'pendiente'
    return estado in {'generando', 'generado', 'publicado'}


def _revert_requires_generated_asset_reset(estado_publicacion):
    estado = (estado_publicacion or 'pendiente').strip() or 'pendiente'
    return estado in {'generado', 'publicado'}


def _generation_in_flight_blocks_revert(estado_publicacion):
    estado = (estado_publicacion or 'pendiente').strip() or 'pendiente'
    return estado == 'generando'


def _published_cluster_blocks_transition(estado_publicacion):
    estado = (estado_publicacion or 'pendiente').strip() or 'pendiente'
    return estado == 'publicado'


def _resolve_cluster_publication_state(cluster_actual, *, total_noticias, reset_generated_content=False):
    estado_publicacion = (cluster_actual.get('estado_publicacion') or 'pendiente').strip() or 'pendiente'
    contenido_ia = cluster_actual.get('contenido_ia')
    foto_principal = cluster_actual.get('foto_principal')
    fotos_secundarias = _normalize_fotos_secundarias(cluster_actual.get('fotos_secundarias'))

    if total_noticias == 0:
        estado_publicacion = 'descartado'
    elif reset_generated_content:
        estado_publicacion = 'pendiente'
        contenido_ia = None
        foto_principal = None
        fotos_secundarias = []

    return {
        'estado_publicacion': estado_publicacion,
        'contenido_ia': contenido_ia,
        'foto_principal': foto_principal,
        'fotos_secundarias': fotos_secundarias,
    }


def _normalize_contenido_ia_for_db(contenido_ia):
    if contenido_ia is None:
        return None
    if isinstance(contenido_ia, (dict, list)):
        return json.dumps(contenido_ia, ensure_ascii=False)
    return contenido_ia


def recalcular_cluster_editorial(cur, cluster_id, *, reset_generated_content=False):
    """
    Recalcula metadata de un cluster editorial según sus noticias actuales.
    """
    cur.execute("""
        SELECT
            COUNT(*)::int AS total_noticias,
            COUNT(DISTINCT fuente)::int AS total_fuentes,
            MIN(COALESCE(fecha_publicacion, fecha_extraccion)) AS primera,
            MAX(COALESCE(fecha_publicacion, fecha_extraccion)) AS ultima
        FROM noticias_historico
        WHERE cluster_id = %s
    """, (cluster_id,))
    agg = cur.fetchone() or {}

    total_noticias = int(agg.get('total_noticias') or 0)
    total_fuentes = int(agg.get('total_fuentes') or 0)
    primera = agg.get('primera')
    ultima = agg.get('ultima')

    cur.execute("""
        SELECT titulo
        FROM noticias_historico
        WHERE cluster_id = %s
        ORDER BY COALESCE(fecha_publicacion, fecha_extraccion) DESC, id DESC
        LIMIT 1
    """, (cluster_id,))
    top = cur.fetchone() or {}
    titulo = (top.get('titulo') or '').strip() or f"Cluster #{cluster_id}"

    cur.execute("""
        SELECT estado_publicacion, contenido_ia, foto_principal, fotos_secundarias
        FROM clusters_editoriales
        WHERE id = %s
    """, (cluster_id,))
    cluster_actual = cur.fetchone() or {}

    score = total_noticias * 2 + total_fuentes * 5
    tendencia = total_noticias

    publication_state = _resolve_cluster_publication_state(
        cluster_actual,
        total_noticias=total_noticias,
        reset_generated_content=reset_generated_content,
    )

    cur.execute("""
        UPDATE clusters_editoriales
        SET
            titulo_representativo = %s,
            cantidad_noticias = %s,
            cantidad_fuentes = %s,
            primera_noticia = %s,
            ultima_noticia = %s,
            score = %s,
            tendencia = %s,
            estado_publicacion = %s,
            contenido_ia = %s,
            foto_principal = %s,
            fotos_secundarias = %s::jsonb,
            actualizado_en = NOW()
        WHERE id = %s
    """, (
        titulo,
        total_noticias,
        total_fuentes,
        primera,
        ultima,
        score,
        tendencia,
        publication_state['estado_publicacion'],
        _normalize_contenido_ia_for_db(publication_state['contenido_ia']),
        publication_state['foto_principal'],
        json.dumps(publication_state['fotos_secundarias'], ensure_ascii=False),
        cluster_id,
    ))


def listar_todos_los_clusters():
    """
    Lista TODOS los clusters de las últimas 72h ordenados por:
    1. Estado de publicación (generado > generando > pendiente > publicado > descartado)
    2. Score editorial (mayor primero)
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    ce.id,
                    ce.titulo_representativo,
                    ce.cantidad_noticias,
                    ce.cantidad_fuentes,
                    ce.score,
                    ce.tendencia,
                    ce.estado_publicacion,
                    ce.url_wp,
                    ce.contenido_ia,
                    ce.foto_principal,
                    ce.primera_noticia,
                    ce.ultima_noticia,
                    ce.ultima_publicacion,
                    ce.veces_publicado,
                    ce.actualizado_en
                FROM clusters_editoriales ce
                JOIN noticias_historico n ON n.cluster_id = ce.id
                WHERE COALESCE(n.fecha_publicacion, n.fecha_extraccion)
                        >= NOW() - INTERVAL '7 days'
                  AND ce.estado_publicacion IS DISTINCT FROM 'descartado'
                GROUP BY ce.id, ce.titulo_representativo, ce.cantidad_noticias,
                         ce.cantidad_fuentes, ce.score, ce.tendencia,
                         ce.estado_publicacion, ce.url_wp, ce.contenido_ia,
                         ce.foto_principal, ce.primera_noticia, ce.ultima_noticia,
                         ce.ultima_publicacion, ce.veces_publicado, ce.actualizado_en
                ORDER BY
                    CASE ce.estado_publicacion
                        WHEN 'generado'   THEN 1
                        WHEN 'generando'  THEN 2
                        WHEN 'pendiente'  THEN 3
                        WHEN 'publicado'  THEN 4
                        WHEN 'descartado' THEN 5
                        ELSE 6
                    END,
                    ce.score DESC
                LIMIT 200
            """)
            return cur.fetchall()
    finally:
        conn.close()


def obtener_keywords_por_clusters_ids(conn, cluster_ids):
    """
    Obtiene keywords agregadas por cluster para un conjunto de IDs.
    """
    if not cluster_ids:
        return {}

    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT
                nh.cluster_id,
                nk.valor_normalizado
            FROM noticias_keywords nk
            JOIN noticias_historico nh ON nh.id = nk.noticia_id
            WHERE nh.cluster_id = ANY(%s)
              AND nk.valor_normalizado IS NOT NULL
              AND nk.valor_normalizado <> ''
        """, (cluster_ids,))

        out = {}
        for row in cur.fetchall():
            out.setdefault(row['cluster_id'], []).append(row['valor_normalizado'])

        for cluster_id in out:
            out[cluster_id] = sorted(set(out[cluster_id]))

        return out


def parse_contenido_ia(raw):
    """
    Parsea contenido_ia que puede venir como dict o como string JSON.
    Devuelve un dict o None.
    """
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def contenido_ia_para_panel(contenido_ia):
    if not contenido_ia:
        return None

    contenido_panel = dict(contenido_ia)
    contenido_panel['articulo_html_panel'] = sanitize_article_markup(
        contenido_ia.get('articulo', '')
    )
    return contenido_panel


def _bloquea_publicacion_por_revision_editorial(cluster):
    estado = cluster.get('estado_publicacion') or 'pendiente'
    return estado == 'generado' and bool(cluster.get('requiere_revision_editorial'))


def obtener_reporte_calidad(fuente=None, desde=None, hasta=None):
    """
    Agrega métricas de metadata.quality por fuente.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            where = ["metadata IS NOT NULL", "metadata ? 'quality'"]
            params = []

            if fuente:
                where.append("fuente = %s")
                params.append(fuente)
            if desde:
                where.append("COALESCE(fecha_publicacion, fecha_extraccion) >= %s::date")
                params.append(desde)
            if hasta:
                where.append("COALESCE(fecha_publicacion, fecha_extraccion) < (%s::date + INTERVAL '1 day')")
                params.append(hasta)

            where_sql = " AND ".join(where)

            cur.execute(f"""
                SELECT
                    fuente,
                    COUNT(*) AS total,
                    SUM(CASE WHEN COALESCE((metadata->'quality'->>'titulo_ok')::boolean, FALSE) THEN 1 ELSE 0 END) AS titulo_ok,
                    SUM(CASE WHEN COALESCE((metadata->'quality'->>'texto_ok')::boolean, FALSE) THEN 1 ELSE 0 END) AS texto_ok,
                    SUM(CASE WHEN COALESCE((metadata->'quality'->>'fecha_ok')::boolean, FALSE) THEN 1 ELSE 0 END) AS fecha_ok,
                    SUM(CASE WHEN COALESCE((metadata->'quality'->>'imagen_ok')::boolean, FALSE) THEN 1 ELSE 0 END) AS imagen_ok,
                    SUM(CASE WHEN COALESCE((metadata->'quality'->>'url_limpia_ok')::boolean, FALSE) THEN 1 ELSE 0 END) AS url_limpia_ok,
                    ROUND(AVG(NULLIF((metadata->'quality'->>'titulo_len')::int, 0)), 1) AS titulo_len_avg,
                    ROUND(AVG(NULLIF((metadata->'quality'->>'texto_len')::int, 0)), 1) AS texto_len_avg
                FROM noticias_historico
                WHERE {where_sql}
                GROUP BY fuente
                ORDER BY total DESC, fuente
            """, params)
            filas = cur.fetchall()

            cur.execute(f"""
                SELECT DISTINCT fuente
                FROM noticias_historico
                WHERE {where_sql}
                ORDER BY fuente
            """, params)
            fuentes = [r['fuente'] for r in cur.fetchall() if r.get('fuente')]

            return filas, fuentes
    finally:
        conn.close()


def obtener_estadisticas_extraccion():
    """
    Devuelve la cantidad diaria de noticias extraídas de los últimos 7 días
    (incluyendo hoy), separadas por fuente.

    Retorna:
        dict con {
            'fechas': ['YYYY-MM-DD', ...],
            'fuentes': ['fuente1', ...],
            'series': {
                'fuente1': [c1, c2, ...],
                ...
            }
        }
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                WITH dias AS (
                    SELECT generate_series(
                        CURRENT_DATE - INTERVAL '6 days',
                        CURRENT_DATE,
                        INTERVAL '1 day'
                    )::date AS dia
                ),
                fuentes_activas AS (
                    SELECT DISTINCT fuente
                    FROM noticias_historico
                    WHERE fuente IS NOT NULL
                      AND fecha_extraccion >= CURRENT_DATE - INTERVAL '6 days'
                ),
                base AS (
                    SELECT d.dia, f.fuente
                    FROM dias d
                    CROSS JOIN fuentes_activas f
                )
                SELECT
                    b.dia AS fecha,
                    b.fuente,
                    COUNT(n.id) AS cantidad
                FROM base b
                LEFT JOIN noticias_historico n
                    ON n.fuente = b.fuente
                    AND n.fecha_extraccion::date = b.dia
                GROUP BY b.dia, b.fuente
                ORDER BY b.dia, b.fuente
            """)
            filas = cur.fetchall()

            fechas = sorted({f['fecha'] for f in filas})
            fechas_str = [f.strftime('%Y-%m-%d') for f in fechas]
            fuentes = sorted({f['fuente'] for f in filas})

            data = {(f['fecha'], f['fuente']): f['cantidad'] for f in filas}
            series = {
                fuente: [data.get((fecha, fuente), 0) for fecha in fechas]
                for fuente in fuentes
            }

            return {
                'fechas': fechas_str,
                'fuentes': fuentes,
                'series': series,
            }
    finally:
        conn.close()


def normalizar_keyword_minima(keyword):
    """
    Normalización mínima acordada: trim + minúsculas.
    No elimina tildes ni espacios internos.
    """
    return (keyword or '').strip().lower()


def normalizar_tipo_keyword(tipo_raw):
    tipo = (tipo_raw or '').strip().lower()
    if not tipo:
        return None
    if tipo not in TIPOS_KEYWORD_PERMITIDOS:
        return '__invalid__'
    return tipo


def listar_keywords_prioridad(q=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            params = []
            where = []
            if q:
                where.append("keyword ILIKE %s")
                params.append(f"%{q}%")

            where_sql = f"WHERE {' AND '.join(where)}" if where else ""

            cur.execute(f"""
                SELECT id, keyword, tipo, puntos, activo, creado_en
                FROM keywords_prioridad
                {where_sql}
                ORDER BY activo DESC, puntos DESC, keyword ASC
                LIMIT 500
            """, params)
            return cur.fetchall()
    finally:
        conn.close()


def listar_keywords_prioridad_activas():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT keyword, activo
                FROM keywords_prioridad
                WHERE activo = TRUE
                ORDER BY keyword ASC
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


def build_cluster_keywords_for_panel(keywords_por_cluster, priority_keywords_rows):
    priority_keywords = {
        normalizar_keyword_minima(row.get('keyword'))
        for row in priority_keywords_rows
        if row.get('activo') and normalizar_keyword_minima(row.get('keyword'))
    }

    return {
        cluster_id: [
            {
                'label': keyword,
                'is_priority': normalizar_keyword_minima(keyword) in priority_keywords,
            }
            for keyword in keywords
        ]
        for cluster_id, keywords in keywords_por_cluster.items()
    }


# =============================================================================
# RUTAS
# =============================================================================

@app.route("/")
def index():
    """
    Página principal: lista de candidatos a publicación.

    Permite ordenar por score técnico o score editorial,
    manteniendo prioridad por estado de publicación.
    """
    orden_actual = (request.args.get('orden') or 'editorial').strip().lower()
    if orden_actual not in ('score', 'editorial'):
        orden_actual = 'editorial'

    clusters = listar_todos_los_clusters()

    # Traer score editorial recalculado + keywords por cluster
    conn = get_connection()
    try:
        candidatos = generar_candidatos(conn)
        scores_editoriales = {c['id']: c['score_editorial'] for c in candidatos}

        prioridad_estado = {
            'generado': 1,
            'generando': 2,
            'pendiente': 3,
            'publicado': 4,
            'descartado': 5,
        }

        def score_secundario(cluster):
            if orden_actual == 'editorial':
                return scores_editoriales.get(cluster['id']) or float('-inf')
            return cluster.get('score') or 0

        clusters = sorted(
            clusters,
            key=lambda c: (
                prioridad_estado.get(c.get('estado_publicacion'), 6),
                -score_secundario(c),
            )
        )

        cluster_ids = [c['id'] for c in clusters]
        keywords_por_cluster = obtener_keywords_por_clusters_ids(conn, cluster_ids)
        keywords_por_cluster = build_cluster_keywords_for_panel(
            keywords_por_cluster,
            listar_keywords_prioridad_activas(),
        )
    finally:
        conn.close()

    return render_template(
        "panel_index.html",
        clusters=clusters,
        scores_editoriales=scores_editoriales,
        keywords_por_cluster=keywords_por_cluster,
        orden_actual=orden_actual,
        ahora=datetime.now()
    )


@app.route("/editor-jefe-ia", methods=["GET", "POST"])
def editor_jefe_ia():
    state, selections, maximum, minimum_editorial_score = "idle", [], "", "50"
    saved_recommendations = []
    priority_keywords_rows = []
    connection_factory = app.config.get(
        "EDITOR_JEFE_CONNECTION_FACTORY", get_connection
    )
    load_saved = app.config.get(
        "EDITOR_JEFE_LOAD_SAVED_RECOMMENDATIONS", load_saved_recommendations
    )
    save_saved = app.config.get(
        "EDITOR_JEFE_SAVE_RECOMMENDATIONS", save_recommendations
    )
    try:
        saved_recommendations = load_saved(connection_factory)
        if request.method == "POST":
            maximum = request.form.get("maximum", "")
            minimum_editorial_score = request.form.get("minimum_editorial_score", "50")
            try:
                parsed_maximum = parse_maximum(maximum)
                parsed_minimum_score = parse_minimum_editorial_score(minimum_editorial_score)
                builder = app.config.get("EDITOR_JEFE_CONTEXT_BUILDER", build_editorial_context)
                recommended_ids = {item["cluster_id"] for item in saved_recommendations}
                candidates = [
                    candidate
                    for candidate in builder(connection_factory)
                    if candidate["cluster_id"] not in recommended_ids
                    and candidate["editorial_score"] >= parsed_minimum_score
                ]
                if candidates:
                    client_factory = app.config.get(
                        "EDITOR_JEFE_CLIENT_FACTORY", OpenAICompatibleSelectionClient
                    )
                    outcome = select_recommendations(
                        candidates, parsed_maximum, client_factory()
                    )
                    selections = outcome.selections
                    if selections:
                        try:
                            save_saved(connection_factory, selections)
                            saved_recommendations = load_saved(connection_factory)
                        except Exception:
                            record_context_failure()
                            flash(
                                "La recomendación se generó, pero no se pudo guardar el listado persistente.",
                                "warning",
                            )
                    if outcome.failed_batches:
                        if selections:
                            state = "partial"
                        elif set(outcome.failure_codes) == {"payload_failure"}:
                            state = "capacity"
                        else:
                            state = "error"
                    else:
                        state = "recommendation" if selections else "zero"
                else:
                    state = "no-eligible"
            except FeatureError as error:
                if error.code == "input_failure":
                    state = "invalid-maximum"
                elif error.code == "minimum_score_failure":
                    state = "invalid-minimum-score"
                elif error.code == "payload_failure":
                    state = "capacity"
                else:
                    state = "error"
                selections = []
    except Exception:
        record_context_failure()
        state, selections, saved_recommendations = "error", [], []

    try:
        priority_keywords_rows = listar_keywords_prioridad_activas()
    except Exception:
        record_context_failure()

    selections = _enriquecer_items_con_keywords_panel(
        selections,
        priority_keywords_rows,
    )

    saved_recommendations = _enriquecer_recomendaciones_guardadas_para_publicacion(
        saved_recommendations
    )

    saved_keywords_por_cluster = {}
    saved_cluster_ids = [item.get('cluster_id') for item in saved_recommendations if item.get('cluster_id') is not None]
    if saved_cluster_ids:
        conn = None
        try:
            conn = connection_factory()
            saved_keywords_por_cluster = obtener_keywords_por_clusters_ids(
                conn,
                saved_cluster_ids,
            )
        except Exception:
            record_context_failure()
        finally:
            if conn is not None:
                conn.close()

    saved_recommendations = _enriquecer_items_con_keywords_panel(
        saved_recommendations,
        priority_keywords_rows,
        keywords_por_cluster=saved_keywords_por_cluster,
    )

    response = make_response(render_template(
        "panel_editor_jefe_ia.html", state=state,
        selections=selections, maximum=maximum,
        minimum_editorial_score=minimum_editorial_score,
        saved_recommendations=saved_recommendations,
    ))
    response.headers["Cache-Control"] = "no-store, private"
    return response


@app.route("/reportes/calidad")
def reporte_calidad():
    fuente = (request.args.get('fuente') or '').strip() or None
    desde = (request.args.get('desde') or '').strip() or None
    hasta = (request.args.get('hasta') or '').strip() or None

    filas, fuentes = obtener_reporte_calidad(
        fuente=fuente,
        desde=desde,
        hasta=hasta
    )
    stats_extraccion = obtener_estadisticas_extraccion()

    return render_template(
        "panel_calidad.html",
        filas=filas,
        fuentes=fuentes,
        fuente_actual=fuente or '',
        desde=desde or '',
        hasta=hasta or '',
        stats_extraccion=stats_extraccion
    )


@app.route("/keywords-prioridad")
def panel_keywords_prioridad():
    q = (request.args.get('q') or '').strip()
    rows = listar_keywords_prioridad(q=q or None)
    return render_template(
        "panel_keywords_prioridad.html",
        rows=rows,
        q=q,
        tipos_permitidos=TIPOS_KEYWORD_PERMITIDOS,
        ahora=datetime.now()
    )


def _redirect_keyword_priority_return_target():
    return_to = (request.form.get('return_to') or request.args.get('return_to') or '').strip()
    if return_to == 'editor_jefe_ia':
        return redirect(url_for('editor_jefe_ia'))
    return redirect(url_for('index'))


@app.route("/keywords-prioridad/crear", methods=["POST"])
def crear_keyword_prioridad():
    keyword = normalizar_keyword_minima(request.form.get('keyword', ''))
    tipo = normalizar_tipo_keyword(request.form.get('tipo'))
    activo = (request.form.get('activo') == 'on')

    try:
        puntos = int(request.form.get('puntos', '0'))
    except ValueError:
        flash("Puntaje inválido", "warning")
        return redirect(url_for('panel_keywords_prioridad'))

    if not keyword:
        flash("La keyword no puede estar vacía", "warning")
        return redirect(url_for('panel_keywords_prioridad'))
    if tipo == '__invalid__':
        flash("Tipo inválido. Usá: keyword, persona, lugar u organizacion", "warning")
        return redirect(url_for('panel_keywords_prioridad'))

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM keywords_prioridad
                WHERE lower(trim(keyword)) = %s
                LIMIT 1
                """,
                (keyword,)
            )
            if cur.fetchone():
                flash("Ya existe esa keyword (comparación en minúsculas)", "warning")
                return redirect(url_for('panel_keywords_prioridad'))

            cur.execute(
                """
                INSERT INTO keywords_prioridad (keyword, tipo, puntos, activo)
                VALUES (%s, %s, %s, %s)
                """,
                (keyword, tipo, puntos, activo)
            )
        conn.commit()
        flash("Keyword creada", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error creando keyword: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for('panel_keywords_prioridad'))


@app.route("/keywords-prioridad/<int:keyword_id>/editar", methods=["POST"])
def editar_keyword_prioridad(keyword_id):
    keyword = normalizar_keyword_minima(request.form.get('keyword', ''))
    tipo = normalizar_tipo_keyword(request.form.get('tipo'))
    activo = (request.form.get('activo') == 'on')

    try:
        puntos = int(request.form.get('puntos', '0'))
    except ValueError:
        flash("Puntaje inválido", "warning")
        return redirect(url_for('panel_keywords_prioridad'))

    if not keyword:
        flash("La keyword no puede estar vacía", "warning")
        return redirect(url_for('panel_keywords_prioridad'))
    if tipo == '__invalid__':
        flash("Tipo inválido. Usá: keyword, persona, lugar u organizacion", "warning")
        return redirect(url_for('panel_keywords_prioridad'))

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM keywords_prioridad
                WHERE lower(trim(keyword)) = %s
                  AND id <> %s
                LIMIT 1
                """,
                (keyword, keyword_id)
            )
            if cur.fetchone():
                flash("Ya existe otra keyword igual en minúsculas", "warning")
                return redirect(url_for('panel_keywords_prioridad'))

            cur.execute(
                """
                UPDATE keywords_prioridad
                SET keyword = %s,
                    tipo = %s,
                    puntos = %s,
                    activo = %s
                WHERE id = %s
                """,
                (keyword, tipo, puntos, activo, keyword_id)
            )
            if cur.rowcount == 0:
                flash("Keyword no encontrada", "warning")
                return redirect(url_for('panel_keywords_prioridad'))

        conn.commit()
        flash("Keyword actualizada", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error actualizando keyword: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for('panel_keywords_prioridad'))


@app.route("/keywords-prioridad/<int:keyword_id>/borrar", methods=["POST"])
def borrar_keyword_prioridad(keyword_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM keywords_prioridad WHERE id = %s", (keyword_id,))
            if cur.rowcount == 0:
                flash("Keyword no encontrada", "warning")
                return redirect(url_for('panel_keywords_prioridad'))
        conn.commit()
        flash("Keyword borrada", "info")
    except Exception as e:
        conn.rollback()
        flash(f"Error borrando keyword: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for('panel_keywords_prioridad'))


@app.route("/keywords-prioridad/buscar")
def buscar_keyword_prioridad():
    keyword = normalizar_keyword_minima(request.args.get('keyword', ''))
    if not keyword:
        return jsonify({"ok": False, "error": "keyword vacía"}), 400

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, keyword, tipo, puntos, activo, creado_en
                FROM keywords_prioridad
                WHERE lower(trim(keyword)) = %s
                LIMIT 1
                """,
                (keyword,)
            )
            row = cur.fetchone()

            if not row:
                return jsonify({
                    "ok": True,
                    "exists": False,
                    "keyword": keyword,
                    "tipos_permitidos": list(TIPOS_KEYWORD_PERMITIDOS)
                })

            return jsonify({
                "ok": True,
                "exists": True,
                "row": {
                    "id": row['id'],
                    "keyword": row['keyword'],
                    "tipo": row['tipo'],
                    "puntos": row['puntos'],
                    "activo": bool(row['activo'])
                },
                "tipos_permitidos": list(TIPOS_KEYWORD_PERMITIDOS)
            })
    finally:
        conn.close()


@app.route("/keywords-prioridad/upsert", methods=["POST"])
def upsert_keyword_prioridad():
    keyword = normalizar_keyword_minima(request.form.get('keyword', ''))
    tipo = normalizar_tipo_keyword(request.form.get('tipo'))
    activo = (request.form.get('activo') == 'on')

    try:
        puntos = int(request.form.get('puntos', '0'))
    except ValueError:
        flash("Puntaje inválido", "warning")
        return _redirect_keyword_priority_return_target()

    if not keyword:
        flash("La keyword no puede estar vacía", "warning")
        return _redirect_keyword_priority_return_target()
    if tipo == '__invalid__':
        flash("Tipo inválido. Usá: keyword, persona, lugar u organizacion", "warning")
        return _redirect_keyword_priority_return_target()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM keywords_prioridad
                WHERE lower(trim(keyword)) = %s
                LIMIT 1
                """,
                (keyword,)
            )
            existente = cur.fetchone()

            if existente:
                cur.execute(
                    """
                    UPDATE keywords_prioridad
                    SET tipo = %s,
                        puntos = %s,
                        activo = %s
                    WHERE id = %s
                    """,
                    (tipo, puntos, activo, existente['id'])
                )
                accion = "actualizada"
            else:
                cur.execute(
                    """
                    INSERT INTO keywords_prioridad (keyword, tipo, puntos, activo)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (keyword, tipo, puntos, activo)
                )
                accion = "creada"

        conn.commit()
        flash(f"Keyword {accion}: {keyword}", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error guardando keyword: {e}", "danger")
    finally:
        conn.close()

    return _redirect_keyword_priority_return_target()


@app.route("/cluster/<int:cluster_id>")
def cluster_detalle(cluster_id):
    """
    Detalle de un cluster específico.

    Muestra:
    - Metadata del cluster (score, cantidad de noticias/fuentes)
    - Lista de noticias fuente (con foto, título, URL, fuente)
    - Selector de foto principal
    - Botón "Generar con IA" (si está pendiente)
    - Artículo generado (si ya se generó)
    - Botón "Publicar en WordPress" (si está generado)
    """
    cluster = obtener_cluster_db(cluster_id)

    if not cluster:
        flash(f"Cluster {cluster_id} no encontrado", "danger")
        return redirect(url_for('index'))

    noticias = obtener_noticias_cluster(cluster_id)
    contenido_ia = contenido_ia_para_panel(
        parse_contenido_ia(cluster.get('contenido_ia'))
    )

    # Evitamos recalcular toda la lista (costoso) para cada detalle.
    score_editorial = cluster.get('score', 0)

    return render_template(
        "panel_cluster.html",
        cluster=cluster,
        noticias=noticias,
        contenido_ia=contenido_ia,
        score_editorial=score_editorial,
        ahora=datetime.now()
    )


@app.route("/generar/<int:cluster_id>", methods=["POST"])
def generar_articulo(cluster_id):
    """
    Genera el artículo con IA para el cluster indicado.

    Recibe POST del botón "Generar con IA".
    Llama a publicador.generar_articulo_para_cluster() y redirige al detalle.
    """
    outcome = _generate_cluster_article(
        cluster_id,
        nota_ia=request.form.get('nota_ia', ''),
    )

    if outcome["status"] == "missing":
        flash("Cluster no encontrado", "danger")
        return redirect(url_for('index'))

    if outcome["status"] == "skipped":
        flash(
            f"No se puede generar/regenerar: estado actual = '{outcome['state']}'",
            "warning"
        )
        return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

    if outcome["status"] == "generated":
        flash("✅ Artículo generado correctamente", "success")
    else:
        flash(
            f"❌ Error: {outcome.get('message', 'Error desconocido')}",
            "danger"
        )

    return redirect(url_for('cluster_detalle', cluster_id=cluster_id))


@app.route("/editor-jefe-ia/generar-guardadas", methods=["POST"])
def generar_articulos_guardados_editor_jefe_ia():
    connection_factory = app.config.get(
        "EDITOR_JEFE_CONNECTION_FACTORY", get_connection
    )
    load_saved = app.config.get(
        "EDITOR_JEFE_LOAD_SAVED_RECOMMENDATIONS", load_saved_recommendations
    )
    bulk_generator = app.config.get(
        "EDITOR_JEFE_BULK_ARTICLE_GENERATOR",
        generate_article_with_editorial_control,
    )

    try:
        saved_recommendations = load_saved(connection_factory)
    except Exception:
        record_context_failure()
        flash("No se pudieron cargar las propuestas guardadas. Probá de nuevo.", "danger")
        return redirect(url_for('editor_jefe_ia'))

    if not saved_recommendations:
        flash("No hay propuestas guardadas para generar.", "info")
        return redirect(url_for('editor_jefe_ia'))

    generated = 0
    skipped = 0
    failed = 0

    for item in saved_recommendations:
        cluster_id = item["cluster_id"]
        outcome = _generate_cluster_article(
            cluster_id,
            cluster=obtener_cluster_db(cluster_id),
            allowed_states=('pendiente',),
            generator=bulk_generator,
        )
        if outcome["status"] == "generated":
            generated += 1
        elif outcome["status"] == "failed":
            failed += 1
        else:
            skipped += 1

    category = "success" if failed == 0 else "warning"
    flash(
        "Generación IA desde propuestas guardadas: "
        f"{generated} generados, {skipped} omitidos, {failed} fallidos.",
        category,
    )
    return redirect(url_for('editor_jefe_ia'))


@app.route("/preview/<int:cluster_id>")
def preview_articulo(cluster_id):
    """
    Muestra el artículo generado para revisión y edición.

    Permite al editor:
    - Leer el resultado de la IA
    - Editar título, resumen, contenido y categoría
    - Guardar cambios
    - Publicar en WordPress
    """
    cluster = obtener_cluster_db(cluster_id)
    if not cluster:
        flash("Cluster no encontrado", "danger")
        return redirect(url_for('index'))

    estado = cluster.get('estado_publicacion') or 'pendiente'
    if estado not in ('generado', 'generando'):
        flash("Primero generá el artículo con IA", "info")
        return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

    noticias = obtener_noticias_cluster(cluster_id)
    contenido_ia = parse_contenido_ia(cluster.get('contenido_ia'))

    return render_template(
        "panel_preview.html",
        cluster=cluster,
        contenido_ia=contenido_ia,
        noticias=noticias,
        categories=ARTICLE_CATEGORIES,
        ahora=datetime.now()
    )


@app.route("/guardar-edicion/<int:cluster_id>", methods=["POST"])
def guardar_edicion(cluster_id):
    """
    Guarda los cambios del editor (título, resumen, artículo, categoría, notas).

    El contenido se guarda como JSON en contenido_ia.
    """
    contenido_json_str = request.form.get('contenido_json', '')

    try:
        contenido = json.loads(contenido_json_str)
    except json.JSONDecodeError:
        flash("Error: contenido no es JSON válido", "danger")
        return redirect(url_for('preview_articulo', cluster_id=cluster_id))

    nota_editor = request.form.get('nota_editor', '')

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE clusters_editoriales
                SET
                    contenido_ia = %s,
                    nota_editor = %s,
                    actualizado_en = NOW()
                WHERE id = %s
            """, (json.dumps(contenido, ensure_ascii=False), nota_editor, cluster_id))
        conn.commit()
        flash("✅ Cambios guardados", "success")
    except Exception as e:
        conn.rollback()
        flash(f"❌ Error guardando: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for('preview_articulo', cluster_id=cluster_id))


@app.route("/publicar/<int:cluster_id>", methods=["POST"])
def publicar_cluster(cluster_id):
    """
    Publica el cluster en WordPress.

    Recibe POST del botón "Publicar en WordPress" en el preview.
    """
    cluster = obtener_cluster_db(cluster_id)
    if not cluster:
        flash("Cluster no encontrado", "danger")
        return redirect(url_for('index'))

    estado = cluster.get('estado_publicacion') or 'pendiente'
    if estado != 'generado':
        flash("Primero generá el artículo con IA", "info")
        return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

    if _bloquea_publicacion_por_revision_editorial(cluster):
        flash(
            "No se puede publicar hasta aprobar la revisión editorial en el detalle del cluster.",
            "warning",
        )
        return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

    redirect_to_cluster = request.form.get('return_to') == 'cluster_detalle'
    if request.form.get('save_photos_before_publish') == '1':
        try:
            foto_principal, fotos_secundarias = _seleccion_fotos_desde_form(
                cluster_id, request.form
            )
            _guardar_seleccion_fotos(
                cluster_id, foto_principal, fotos_secundarias
            )
        except Exception as e:
            flash(f"❌ Error guardando fotos: {e}", "danger")
            return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

    resultado = publicapress.publicar_cluster(cluster_id)

    if resultado["ok"]:
        delete_saved = app.config.get(
            "EDITOR_JEFE_DELETE_SAVED_RECOMMENDATION", delete_saved_recommendation
        )
        try:
            delete_saved(get_connection, cluster_id)
        except Exception:
            record_context_failure()
            flash(
                f"✅ Published! → {resultado['url_wp']}. No se pudo limpiar la recomendación guardada.",
                "warning",
            )
            return redirect(url_for('cluster_detalle', cluster_id=cluster_id))
        flash(f"✅ Published! → {resultado['url_wp']}", "success")
        return redirect(url_for('cluster_detalle', cluster_id=cluster_id))
    else:
        flash(f"❌ Error: {resultado.get('mensaje', 'Desconocido')}", "danger")
        endpoint = 'cluster_detalle' if redirect_to_cluster else 'preview_articulo'
        return redirect(url_for(endpoint, cluster_id=cluster_id))


@app.route("/aprobar-revision-editorial/<int:cluster_id>", methods=["POST"])
def aprobar_revision_editorial(cluster_id):
    cluster = obtener_cluster_db(cluster_id)
    if not cluster:
        flash("Cluster no encontrado", "danger")
        return redirect(url_for('index'))

    if not cluster.get('requiere_revision_editorial'):
        flash("Este cluster ya no requiere revisión editorial.", "info")
        return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

    set_review_required = app.config.get(
        "EDITORIAL_REVIEW_FLAG_SETTER", publicador.set_requiere_revision_editorial
    )
    set_review_required(cluster_id, False)
    flash("Revisión editorial aprobada. Ya podés publicar.", "success")
    return redirect(url_for('cluster_detalle', cluster_id=cluster_id))


@app.route("/upload-fotos/<int:cluster_id>", methods=["POST"])
def upload_fotos(cluster_id):
    """Sube fotos manuales temporales para un cluster."""
    cluster = obtener_cluster_db(cluster_id)
    if not cluster:
        flash("Cluster no encontrado", "danger")
        return redirect(url_for('index'))

    archivos = request.files.getlist('fotos')[:MAX_UPLOAD_FILES]
    if not archivos:
        flash("Seleccioná al menos una foto", "warning")
        return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

    destino = _ensure_cluster_upload_dir(cluster_id)
    subidas = 0

    for archivo in archivos:
        if not archivo or not archivo.filename:
            continue
        nombre = archivo.filename.strip()
        _, ext = os.path.splitext(nombre.lower())
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            continue

        contenido = archivo.read()
        if not contenido or len(contenido) > MAX_UPLOAD_BYTES or not _es_imagen_valida(contenido):
            continue

        nombre_final = f"{uuid.uuid4().hex}{ext}"
        with open(os.path.join(destino, nombre_final), 'wb') as fh:
            fh.write(contenido)
        subidas += 1

    if subidas:
        flash(f"{subidas} foto(s) temporales subidas", "success")
    else:
        flash("No se subieron fotos válidas (formatos: jpg, png, gif, webp; máx 8MB)", "warning")

    return redirect(url_for('cluster_detalle', cluster_id=cluster_id))


@app.route("/set-foto/<int:cluster_id>", methods=["POST"])
def set_foto_principal(cluster_id):
    """
    Guarda la foto principal y hasta 2 fotos secundarias elegidas por el editor.
    """
    foto_principal, fotos_limpias = _seleccion_fotos_desde_form(cluster_id, request.form)
    _guardar_seleccion_fotos(cluster_id, foto_principal, fotos_limpias)
    flash("Fotos guardadas", "success")

    return redirect(url_for('cluster_detalle', cluster_id=cluster_id))


@app.route("/split-cluster/<int:cluster_id>", methods=["POST"])
def split_cluster(cluster_id):
    """
    Crea un nuevo cluster moviendo noticias seleccionadas desde cluster_id.
    """
    raw_ids = request.form.getlist('noticias_split')
    noticia_ids = []
    for raw in raw_ids:
        try:
            noticia_ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    noticia_ids = sorted(set(noticia_ids))

    if not noticia_ids:
        flash("Seleccioná al menos una noticia para crear el nuevo cluster.", "warning")
        return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, estado_publicacion FROM clusters_editoriales WHERE id = %s", (cluster_id,))
            origen = cur.fetchone()
            if not origen:
                flash("Cluster origen no encontrado.", "danger")
                return redirect(url_for('index'))

            if _split_requires_pending_publication_state(origen.get('estado_publicacion')):
                if _published_cluster_blocks_transition(origen.get('estado_publicacion')):
                    flash(
                        "No se puede partir un cluster publicado porque ya tiene una nota activa en WordPress.",
                        "warning",
                    )
                elif _generation_in_flight_blocks_revert(origen.get('estado_publicacion')):
                    flash(
                        "No se puede partir un cluster mientras se está generando el artículo. Esperá a que termine el proceso.",
                        "warning",
                    )
                else:
                    flash(
                        "No se puede partir un cluster generado. Revertí primero a pendiente si necesitás dividirlo.",
                        "warning",
                    )
                return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

            cur.execute("SELECT COUNT(*) AS total FROM noticias_historico WHERE cluster_id = %s", (cluster_id,))
            total_origen = int((cur.fetchone() or {}).get('total') or 0)
            if total_origen <= 1:
                flash("El cluster debe tener al menos 2 noticias para poder partirse.", "warning")
                return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

            cur.execute("""
                SELECT id
                FROM noticias_historico
                WHERE cluster_id = %s
                  AND id = ANY(%s)
            """, (cluster_id, noticia_ids))
            ids_validos = sorted([row['id'] for row in cur.fetchall()])

            if not ids_validos:
                flash("Las noticias seleccionadas no pertenecen al cluster actual.", "warning")
                return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

            if len(ids_validos) >= total_origen:
                flash("No podés mover todas las noticias: dejá al menos una en el cluster original.", "warning")
                return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

            nota = f"Cluster creado por split manual desde #{cluster_id} el {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            cur.execute("""
                INSERT INTO clusters_editoriales
                    (titulo_representativo, estado, estado_publicacion, fotos_secundarias, nota_editor)
                VALUES
                    (%s, 'nuevo', 'pendiente', '[]'::jsonb, %s)
                RETURNING id
            """, (f"Cluster derivado de #{cluster_id}", nota))
            nuevo_cluster_id = cur.fetchone()['id']

            cur.execute("""
                UPDATE noticias_historico
                SET cluster_id = %s,
                    cluster_asignado_en = NOW()
                WHERE cluster_id = %s
                  AND id = ANY(%s)
            """, (nuevo_cluster_id, cluster_id, ids_validos))

            if cur.rowcount != len(ids_validos):
                raise RuntimeError("No se pudieron mover todas las noticias seleccionadas.")

            recalcular_cluster_editorial(cur, cluster_id)
            recalcular_cluster_editorial(cur, nuevo_cluster_id, reset_generated_content=True)

        conn.commit()
        flash(
            f"✅ Nuevo cluster #{nuevo_cluster_id} creado con {len(ids_validos)} noticias.",
            "success"
        )
        return redirect(url_for('cluster_detalle', cluster_id=nuevo_cluster_id))
    except Exception as e:
        conn.rollback()
        flash(f"❌ Error partiendo cluster: {e}", "danger")
        return redirect(url_for('cluster_detalle', cluster_id=cluster_id))
    finally:
        conn.close()


@app.route("/descartar/<int:cluster_id>", methods=["POST"])
def descartar_cluster(cluster_id):
    """
    Descarta un cluster para que no aparezca en la lista de candidatos.
    """
    redirect_endpoint = request.form.get("return_to")
    redirect_target = (
        url_for("editor_jefe_ia")
        if redirect_endpoint == "editor_jefe_ia"
        else url_for("index")
    )

    conn = get_connection()
    delete_saved = app.config.get(
        "EDITOR_JEFE_DELETE_SAVED_RECOMMENDATION", delete_saved_recommendation
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, estado_publicacion FROM clusters_editoriales WHERE id = %s",
                (cluster_id,)
            )
            cluster = cur.fetchone()

            if not cluster:
                flash("Cluster no encontrado", "warning")
                return redirect(redirect_target)

            estado_actual = cluster.get('estado_publicacion') or 'pendiente'
            if estado_actual == 'descartado':
                flash("El cluster ya estaba descartado", "info")
                return redirect(redirect_target)

            cur.execute("""
                UPDATE clusters_editoriales
                SET estado_publicacion = 'descartado',
                    actualizado_en = NOW()
                WHERE id = %s
            """, (cluster_id,))
        conn.commit()
    finally:
        conn.close()

    try:
        delete_saved(get_connection, cluster_id)
    except Exception:
        record_context_failure()
        flash("Cluster descartado, pero no se pudo limpiar la recomendación guardada.", "warning")
        return redirect(redirect_target)

    flash("Cluster descartado", "info")
    return redirect(redirect_target)


@app.route("/revertir/<int:cluster_id>", methods=["POST"])
def revertir_estado(cluster_id):
    """
    Revierte un cluster a 'pendiente' para poder regenerar el artículo.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, estado_publicacion, requiere_revision_editorial FROM clusters_editoriales WHERE id = %s",
                (cluster_id,),
            )
            cluster = cur.fetchone()
            if not cluster:
                flash("Cluster no encontrado", "warning")
                return redirect(url_for('index'))

            if _generation_in_flight_blocks_revert(cluster.get('estado_publicacion')):
                flash(
                    "No se puede revertir un cluster mientras la generación sigue en curso.",
                    "warning",
                )
                return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

            if _published_cluster_blocks_transition(cluster.get('estado_publicacion')):
                flash(
                    "No se puede revertir un cluster publicado porque la nota sigue activa en WordPress.",
                    "warning",
                )
                return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

            if _revert_requires_generated_asset_reset(cluster.get('estado_publicacion')):
                cur.execute("""
                    UPDATE clusters_editoriales
                    SET estado_publicacion = 'pendiente',
                        contenido_ia = NULL,
                        foto_principal = NULL,
                        fotos_secundarias = '[]'::jsonb,
                        url_wp = NULL,
                        requiere_revision_editorial = FALSE,
                        actualizado_en = NOW()
                    WHERE id = %s
                """, (cluster_id,))
            else:
                cur.execute("""
                    UPDATE clusters_editoriales
                    SET estado_publicacion = 'pendiente',
                        actualizado_en = NOW()
                    WHERE id = %s
                """, (cluster_id,))
        conn.commit()
        flash("Revertido a pendiente", "info")
    finally:
        conn.close()

    return redirect(url_for('cluster_detalle', cluster_id=cluster_id))


# =============================================================================
# STATIC / UTILITY
# =============================================================================

@app.route("/noticia/<int:noticia_id>")
def redirigir_noticia(noticia_id):
    """
    Redirige a la URL original de la noticia en el medio.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT url_original FROM noticias_historico WHERE id = %s",
                (noticia_id,)
            )
            row = cur.fetchone()
            if row and row['url_original']:
                return redirect(row['url_original'])
    finally:
        conn.close()

    flash("URL de la noticia no encontrada", "warning")
    return redirect(url_for('index'))


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("🚀 Panel de Control TRH — Modo MVP")
    print("=" * 60)
    print()
    print("  Panel:      http://localhost:5000/")
    print("  Ctrl+C para detener")
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )


if __name__ == "__main__":
    main()
