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
from datetime import datetime

# Agregar el directorio del proyecto al path para poder importar los otros módulos
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash
)
from seleccionar_publicables import get_connection, generar_candidatos
import publicador
import publicapress

app = Flask(__name__)

# Secret key para sesiones (Flask lo requiere aunque no lo usemos para auth)
app.secret_key = 'trh-mvp-secret-key-cambiar-en-produccion'


# =============================================================================
# HELPERS DE BASE DE DATOS
# =============================================================================

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
                    url_wp,
                    nota_editor,
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
            return cur.fetchone()
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
            """)
            return cur.fetchall()
    finally:
        conn.close()


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


# =============================================================================
# RUTAS
# =============================================================================

@app.route("/")
def index():
    """
    Página principal: lista de candidatos a publicación.

    Muestra todos los clusters de las últimas 72h ordenados por:
    1. Estado (generado > generando > pendiente > publicado > descartado)
    2. Score (mayor primero)

    El editor puede hacer clic en cualquier tarjeta para ver el detalle.
    """
    clusters = listar_todos_los_clusters()

    # Traer score editorial recalculado + keywords por cluster
    conn = get_connection()
    try:
        candidatos = generar_candidatos(conn)
        scores_editoriales = {c['id']: c['score_editorial'] for c in candidatos}
        keywords_por_cluster = {
            c['id']: [k.get('valor_normalizado') for k in c.get('keywords', []) if k.get('valor_normalizado')]
            for c in candidatos
        }
    finally:
        conn.close()

    return render_template(
        "panel_index.html",
        clusters=clusters,
        scores_editoriales=scores_editoriales,
        keywords_por_cluster=keywords_por_cluster,
        ahora=datetime.now()
    )


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

    resultado = publicador.generar_articulo_para_cluster(cluster_id)

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


@app.route("/set-foto/<int:cluster_id>", methods=["POST"])
def set_foto_principal(cluster_id):
    """
    Guarda la foto principal elegida por el editor.
    """
    foto_url = request.form.get('foto_url', '')

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE clusters_editoriales
                SET foto_principal = %s,
                    actualizado_en = NOW()
                WHERE id = %s
            """, (foto_url, cluster_id))
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for('cluster_detalle', cluster_id=cluster_id))


@app.route("/descartar/<int:cluster_id>", methods=["POST"])
def descartar_cluster(cluster_id):
    """
    Descarta un cluster para que no aparezca en la lista de candidatos.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
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