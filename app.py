# pyright: reportMissingImports=false
"""
app.py — Panel de Control TRH

Aplicación Flask que sirve como panel editorial:
  - /                   → Lista de candidatos a publicación
  - /cluster/<id>       → Detalle del cluster: noticias, fotos, generar con IA
  - /generar/<id>       → (POST) Genera el artículo con IA
  - /preview/<id>       → Muestra el artículo generado para revisión
  - /publicar/<id>      → (POST) Publica en WordPress
  - /set-foto/<id>      → (POST) Guardar foto principal elegida por el editor
  - /guardar-edicion/<id> → (POST) Guardar edición del editor

Para correr: python app.py
Se levanta en http://0.0.0.0:5000
"""

import sys
import os
import json
import uuid
from datetime import datetime

# Agregar el directorio del proyecto al path para poder importar los otros módulos
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
from seleccionar_publicables import get_connection, generar_candidatos
from editor_jefe_ia import (
    FeatureError, OpenRouterSelectionClient, build_editorial_context, parse_maximum,
    parse_minimum_editorial_score, record_context_failure, select_recommendations,
)
import publicador
import publicapress

app = Flask(__name__)

# Secret key para sesiones (Flask lo requiere aunque no lo usemos para auth)
app.secret_key = 'trh-mvp-secret-key-cambiar-en-produccion'

TIPOS_KEYWORD_PERMITIDOS = ('keyword', 'persona', 'lugar', 'organizacion')

TEMP_UPLOAD_BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'tmp')
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8MB por imagen
MAX_UPLOAD_FILES = 6
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES * MAX_UPLOAD_FILES


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


def recalcular_cluster_editorial(cur, cluster_id):
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

    score = total_noticias * 2 + total_fuentes * 5
    tendencia = total_noticias

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
            estado_publicacion = CASE
                WHEN %s = 0 THEN 'descartado'
                ELSE 'pendiente'
            END,
            contenido_ia = CASE WHEN %s = 0 THEN contenido_ia ELSE NULL END,
            foto_principal = CASE WHEN %s = 0 THEN foto_principal ELSE NULL END,
            fotos_secundarias = CASE WHEN %s = 0 THEN fotos_secundarias ELSE '[]'::jsonb END,
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
        total_noticias,
        total_noticias,
        total_noticias,
        total_noticias,
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
    if request.method == "POST":
        maximum = request.form.get("maximum", "")
        minimum_editorial_score = request.form.get("minimum_editorial_score", "50")
        try:
            parsed_maximum = parse_maximum(maximum)
            parsed_minimum_score = parse_minimum_editorial_score(minimum_editorial_score)
            builder = app.config.get("EDITOR_JEFE_CONTEXT_BUILDER", build_editorial_context)
            connection_factory = app.config.get(
                "EDITOR_JEFE_CONNECTION_FACTORY", get_connection
            )
            candidates = [
                candidate
                for candidate in builder(connection_factory, obtener_keywords_por_clusters_ids)
                if candidate["editorial_score"] > parsed_minimum_score
            ]
            if candidates:
                client_factory = app.config.get(
                    "EDITOR_JEFE_CLIENT_FACTORY", OpenRouterSelectionClient
                )
                selections = select_recommendations(
                    candidates, parsed_maximum, client_factory()
                )
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
            state, selections = "error", []
    response = make_response(render_template(
        "panel_editor_jefe_ia.html", state=state,
        selections=selections, maximum=maximum,
        minimum_editorial_score=minimum_editorial_score,
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

    return render_template(
        "panel_calidad.html",
        filas=filas,
        fuentes=fuentes,
        fuente_actual=fuente or '',
        desde=desde or '',
        hasta=hasta or ''
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
        return redirect(url_for('index'))

    if not keyword:
        flash("La keyword no puede estar vacía", "warning")
        return redirect(url_for('index'))
    if tipo == '__invalid__':
        flash("Tipo inválido. Usá: keyword, persona, lugar u organizacion", "warning")
        return redirect(url_for('index'))

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

    return redirect(url_for('index'))


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
    contenido_ia = parse_contenido_ia(cluster.get('contenido_ia'))

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
    cluster = obtener_cluster_db(cluster_id)
    if not cluster:
        flash("Cluster no encontrado", "danger")
        return redirect(url_for('index'))

    estado = cluster.get('estado_publicacion') or 'pendiente'

    if estado not in ('pendiente', 'generando', 'generado'):
        flash(
            f"No se puede generar/regenerar: estado actual = '{estado}'",
            "warning"
        )
        return redirect(url_for('cluster_detalle', cluster_id=cluster_id))

    nota_ia = (request.form.get('nota_ia', '') or '').strip()

    if nota_ia != (cluster.get('nota_ia') or '').strip():
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE clusters_editoriales
                    SET nota_ia = %s,
                        actualizado_en = NOW()
                    WHERE id = %s
                """, (nota_ia, cluster_id))
            conn.commit()
        finally:
            conn.close()

    resultado = publicador.generar_articulo_para_cluster(cluster_id, nota_ia=nota_ia)

    if resultado["ok"]:
        flash("✅ Artículo generado correctamente", "success")
    else:
        flash(
            f"❌ Error: {resultado.get('mensaje', 'Error desconocido')}",
            "danger"
        )

    return redirect(url_for('cluster_detalle', cluster_id=cluster_id))


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

    resultado = publicapress.publicar_cluster(cluster_id)

    if resultado["ok"]:
        flash(f"✅ Published! → {resultado['url_wp']}", "success")
        return redirect(url_for('cluster_detalle', cluster_id=cluster_id))
    else:
        flash(f"❌ Error: {resultado.get('mensaje', 'Desconocido')}", "danger")
        return redirect(url_for('preview_articulo', cluster_id=cluster_id))


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
    urls_noticias = [
        (n.get('url_imagen') or '').strip()
        for n in obtener_noticias_cluster(cluster_id)
        if (n.get('url_imagen') or '').strip()
    ]
    urls_permitidas = set(urls_noticias + _listar_fotos_manuales(cluster_id))

    foto_principal = (request.form.get('foto_principal', '') or '').strip()
    if foto_principal and foto_principal not in urls_permitidas:
        foto_principal = ''

    fotos_secundarias = [
        (u or '').strip() for u in request.form.getlist('fotos_secundarias')
        if (u or '').strip() and (u or '').strip() in urls_permitidas
    ]

    # Limpiar duplicados preservando orden
    fotos_limpias = []
    for url in fotos_secundarias:
        if url == foto_principal:
            continue
        if url not in fotos_limpias:
            fotos_limpias.append(url)
    fotos_limpias = fotos_limpias[:2]

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE clusters_editoriales
                SET foto_principal = %s,
                    fotos_secundarias = %s::jsonb,
                    actualizado_en = NOW()
                WHERE id = %s
            """, (foto_principal, json.dumps(fotos_limpias, ensure_ascii=False), cluster_id))
        conn.commit()
        flash("Fotos guardadas", "success")
    finally:
        conn.close()

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
            cur.execute("SELECT id FROM clusters_editoriales WHERE id = %s", (cluster_id,))
            origen = cur.fetchone()
            if not origen:
                flash("Cluster origen no encontrado.", "danger")
                return redirect(url_for('index'))

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
            recalcular_cluster_editorial(cur, nuevo_cluster_id)

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
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, estado_publicacion FROM clusters_editoriales WHERE id = %s",
                (cluster_id,)
            )
            cluster = cur.fetchone()

            if not cluster:
                flash("Cluster no encontrado", "warning")
                return redirect(url_for('index'))

            estado_actual = cluster.get('estado_publicacion') or 'pendiente'
            if estado_actual == 'descartado':
                flash("El cluster ya estaba descartado", "info")
                return redirect(url_for('index'))

            cur.execute("""
                UPDATE clusters_editoriales
                SET estado_publicacion = 'descartado',
                    actualizado_en = NOW()
                WHERE id = %s
            """, (cluster_id,))
        conn.commit()
        flash("Cluster descartado", "info")
    finally:
        conn.close()

    return redirect(url_for('index'))


@app.route("/revertir/<int:cluster_id>", methods=["POST"])
def revertir_estado(cluster_id):
    """
    Revierte un cluster a 'pendiente' para poder regenerar el artículo.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
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

if __name__ == "__main__":
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