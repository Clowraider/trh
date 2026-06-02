# pyright: reportMissingImports=false
"""
publicapress.py — Publica el artículo generado en WordPress.

Este script es la TERCERA y última parte del flujo:

  1. (antes) Crawlers alimentan la DB → clustering agrupa noticias
  2. El editor elige un cluster en el panel
  3. publicador.py genera el artículo con IA → se guarda en contenido_ia
  4. El editor revisa en el panel → hace clic en Publicar
  5. ESTE script: obtiene el contenido, busca/crea categoría, publica en WP

Funciones exportadas:
  - publicar_cluster(cluster_id)  → publica y devuelve {ok, url_wp, mensaje}
  - test_wordpress_auth()          → prueba la conexión con WP
"""

# pyright: reportGeneralTypeIssues=false
import os
import io
import logging
import time
import shutil
import requests
import base64
import json
import psycopg2
from urllib.parse import urlparse
from psycopg2.extras import RealDictCursor
from PIL import Image, ImageDraw, ImageFont

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

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "trh"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD")
}

WP_URL = os.getenv("WP_URL", "https://trh.com.ar").rstrip('/')
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")

def _env_float(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


WATERMARK_ENABLED = os.getenv("WATERMARK_ENABLED", "false").lower() in ("1", "true", "yes", "on")
WATERMARK_MODE = os.getenv("WATERMARK_MODE", "text").lower()  # text | logo | both
WATERMARK_TEXT = os.getenv("WATERMARK_TEXT", "TRH.com.ar")
WATERMARK_OPACITY = _env_float("WATERMARK_OPACITY", 0.35)
WATERMARK_POSITION = os.getenv("WATERMARK_POSITION", "bottom_right").lower()  # bottom_right|bottom_left|top_right|top_left|center
WATERMARK_MARGIN = _env_int("WATERMARK_MARGIN", 24)
WATERMARK_LOGO_PATH = os.getenv("WATERMARK_LOGO_PATH", "")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TEMP_UPLOAD_BASE_DIR = os.path.join(PROJECT_ROOT, 'static', 'uploads', 'tmp')


# =============================================================================
# AUTENTICACIÓN WORDPRESS (Basic Auth con Application Password)
# =============================================================================

def _get_wp_headers():
    """
    Construye los headers de autenticación para la REST API de WordPress.

    WordPress usa autenticación Basic Auth:
      - Se combina username:app_password
      - Se encodea en Base64
      - Se manda como header: Authorization: Basic <base64>

    No es la forma más segura del mundo (no usa OAuth2),
    pero es estándar para scripts/MVP con Application Passwords.
    """
    if not WP_USERNAME or not WP_APP_PASSWORD:
        raise RuntimeError('Falta WP_USERNAME o WP_APP_PASSWORD en entorno (.env)')
    credentials = f"{WP_USERNAME}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode()).decode('utf-8')
    return {
        'Authorization': f'Basic {token}',
        'Content-Type': 'application/json'
    }


def test_wordpress_auth():
    """
    Prueba la conexión con WordPress consultando /wp-json/wp/v2/users/me.
    Si responde 200, la auth funciona. Si no, algo está mal.

    Returns:
        bool: True si la conexión es exitosa
    """
    logger.info("🔍 Probando autenticación con WordPress...")
    response = _request_with_retry(
        "GET",
        f"{WP_URL}/wp-json/wp/v2/users/me",
        headers=_get_wp_headers(),
        timeout=20
    )

    if response.status_code == 200:
        user = response.json()
        logger.info("✅ Autenticación EXITOSA → Usuario: %s - Roles: %s", user.get('name'), user.get('roles'))
        return True

    logger.error("❌ Falló la autenticación: %s", response.text[:300])
    return False

# =============================================================================
# CONEXIÓN A LA BASE DE DATOS
# =============================================================================

def get_connection():
    """Crea una conexión a PostgreSQL."""
    if not DB_CONFIG['password']:
        raise RuntimeError('Falta DB_PASSWORD en entorno (.env)')
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def _request_with_retry(method, url, attempts=3, backoff=1.5, **kwargs):
    last_error = None
    for intento in range(1, attempts + 1):
        try:
            resp = requests.request(method, url, timeout=kwargs.pop('timeout', 30), **kwargs)
            if resp.status_code >= 500:
                logger.warning("WP %s %s devolvió %s (intento %s)", method, url, resp.status_code, intento)
                time.sleep(backoff * intento)
                continue
            return resp
        except (requests.Timeout, requests.ConnectionError) as e:
            last_error = e
            logger.warning("Error de red en %s %s (intento %s): %s", method, url, intento, e)
            time.sleep(backoff * intento)
    if last_error:
        raise last_error
    raise RuntimeError(f"Falló request {method} {url}")


def _validar_contenido_publicable(contenido):
    faltantes = [k for k in ('titulo', 'resumen', 'articulo') if not str(contenido.get(k, '')).strip()]
    if faltantes:
        raise ValueError(f"Contenido IA incompleto para publicar. Faltan: {', '.join(faltantes)}")


def _guardar_error_publicacion(conn, cluster_id, mensaje):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE clusters_editoriales
            SET nota_editor = %s,
                actualizado_en = NOW()
            WHERE id = %s
        """, (f"Error publicación WP: {mensaje[:400]}", cluster_id))
    conn.commit()


# =============================================================================
# CATEGORÍAS EN WORDPRESS
# =============================================================================

def _normalizar_slug(texto):
    """
    Convierte un texto a slug (URL-friendly).

    Ejemplo: "Economía y Política" → "economia-y-politica"
    Reemplaza tildes y caracteres especiales.
    """
    for a, b in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")]:
        texto = texto.replace(a, b)
    # Solo letras, números y guiones
    slug = ""
    for c in texto.lower()[:100]:
        if c.isalnum():
            slug += c
        elif c == " ":
            slug += "-"
    return slug


def categoria_existe(nombre):
    """
    Busca si ya existe una categoría en WordPress con ese nombre.

    Busca por nombre exacto (case insensitive) en las primeras 10 páginas.
    Si la encuentra, devuelve su ID. Si no, devuelve None.

    Args:
        nombre: string con el nombre de la categoría

    Returns:
        int con el ID de la categoría o None si no existe
    """
    headers = _get_wp_headers()
    response = _request_with_retry(
        "GET",
        f"{WP_URL}/wp-json/wp/v2/categories",
        headers=headers,
        params={'search': nombre, 'per_page': 10}
    )
    if response.status_code == 200:
        for cat in response.json():
            if cat['name'].lower().strip() == nombre.lower().strip():
                return cat['id']
    return None


def crear_categoria(nombre):
    """
    Crea una nueva categoría en WordPress.

    El slug se genera automáticamente a partir del nombre
    (ver _normalizar_slug). La descripción es informativa nomás.

    Args:
        nombre: nombre de la categoría

    Returns:
        int con el ID de la categoría creada, o None si falló
    """
    data = {
        "name": nombre,
        "description": f"Categoría automática: {nombre}",
        "slug": _normalizar_slug(nombre)
    }

    headers = _get_wp_headers()
    response = _request_with_retry(
        "POST",
        f"{WP_URL}/wp-json/wp/v2/categories",
        headers=headers,
        json=data
    )
    if response.status_code in (201, 200):
        cat_id = response.json()['id']
        print(f"   ✅ Categoría creada: {nombre} (ID: {cat_id})")
        return cat_id
    else:
        print(f"   ❌ Error creando categoría: {response.status_code}")
        print(response.text)
        return None


def obtener_o_crear_categoria(nombre):
    """
    Busca si la categoría existe en WordPress. Si no, la crea.

    Args:
        nombre: nombre de la categoría a buscar/crear

    Returns:
        int con el ID de la categoría, o None si no se pudo
    """
    if not nombre:
        print("   ⚠️  Sin categoría, se publica sin categoría")
        return None

    cat_id = categoria_existe(nombre)
    if cat_id:
        print(f"   ℹ️  Categoría ya existe: {nombre} (ID: {cat_id})")
        return cat_id

    return crear_categoria(nombre)


# =============================================================================
# SUBIDA DE IMAGENES A WORDPRESS
# =============================================================================

def _clamp(value, min_v, max_v):
    return max(min_v, min(max_v, value))


def _obtener_posicion(base_w, base_h, mark_w, mark_h):
    m = max(0, WATERMARK_MARGIN)
    pos = WATERMARK_POSITION
    if pos == 'bottom_left':
        return m, max(m, base_h - mark_h - m)
    if pos == 'top_right':
        return max(m, base_w - mark_w - m), m
    if pos == 'top_left':
        return m, m
    if pos == 'center':
        return max(0, (base_w - mark_w) // 2), max(0, (base_h - mark_h) // 2)
    return max(m, base_w - mark_w - m), max(m, base_h - mark_h - m)


def _aplicar_watermark(image_bytes):
    if not WATERMARK_ENABLED:
        return image_bytes

    try:
        base = Image.open(io.BytesIO(image_bytes)).convert('RGBA')
    except Exception:
        return image_bytes

    overlay = Image.new('RGBA', base.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    opacity = int(_clamp(WATERMARK_OPACITY, 0.0, 1.0) * 255)

    if WATERMARK_MODE in ('logo', 'both') and WATERMARK_LOGO_PATH:
        try:
            logo = Image.open(WATERMARK_LOGO_PATH).convert('RGBA')
            max_w = max(80, int(base.width * 0.18))
            scale = min(1.0, max_w / max(1, logo.width))
            new_size = (max(1, int(logo.width * scale)), max(1, int(logo.height * scale)))
            logo = logo.resize(new_size)
            alpha = logo.split()[-1].point(lambda a: int(a * _clamp(WATERMARK_OPACITY, 0.0, 1.0)))
            logo.putalpha(alpha)
            lx, ly = _obtener_posicion(base.width, base.height, logo.width, logo.height)
            overlay.alpha_composite(logo, (lx, ly))
        except Exception as e:
            logger.warning("No se pudo aplicar logo watermark: %s", e)

    if WATERMARK_MODE in ('text', 'both') and WATERMARK_TEXT.strip():
        font_size = max(16, int(base.width * 0.03))
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx, ty = _obtener_posicion(base.width, base.height, tw, th)
        draw.text((tx + 1, ty + 1), WATERMARK_TEXT, fill=(0, 0, 0, max(30, opacity // 2)), font=font)
        draw.text((tx, ty), WATERMARK_TEXT, fill=(255, 255, 255, opacity), font=font)

    out = Image.alpha_composite(base, overlay).convert('RGB')
    buff = io.BytesIO()
    out.save(buff, format='JPEG', quality=92, optimize=True)
    return buff.getvalue()


def _obtener_mime_type(content_bytes):
    """
    Detecta el MIME type a partir de los primeros bytes de la imagen.
    Soporta los formatos más comunes: JPEG, PNG, GIF, WebP.
    """
    if content_bytes[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    elif content_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    elif content_bytes[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    elif content_bytes[:4] == b'RIFF' and content_bytes[8:12] == b'WEBP':
        return 'image/webp'
    return 'image/jpeg'  # default


def _nombre_archivo_desde_url(url):
    """Extrae un nombre de archivo razonable de una URL."""
    parsed = urlparse(url)
    nombre = parsed.path.split('/')[-1]
    if not nombre or '.' not in nombre:
        nombre = 'imagen-trh.jpg'
    # Limpiar caracteres raros
    import re
    nombre = re.sub(r'[^\w\-.]', '_', nombre)
    return nombre[:100]


def _path_local_desde_url_temporal(url):
    prefijo = '/static/uploads/tmp/'
    if not isinstance(url, str) or not url.startswith(prefijo):
        return None
    rel = url[len(prefijo):].strip('/')
    if '..' in rel:
        return None
    _, ext = os.path.splitext(rel.lower())
    if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
        return None

    base = os.path.abspath(TEMP_UPLOAD_BASE_DIR)
    path = os.path.abspath(os.path.join(base, rel))
    if os.path.commonpath([base, path]) != base:
        return None
    return path


def _limpiar_fotos_temporales_cluster(cluster_id):
    path = os.path.join(TEMP_UPLOAD_BASE_DIR, f'cluster_{cluster_id}')
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def subir_imagen_a_wordpress(url_imagen_externa):
    """
    Descarga una imagen desde una URL externa y la sube a WordPress como media.

    Flujo:
      1. Descarga la imagen (bytes)
      2. Detecta el MIME type
      3. Arma el nombre del archivo
      4. Envía a /wp-json/wp/v2/media con Content-Type: image/*
      5. Devuelve el attachment_id de WordPress

    Args:
        url_imagen_externa: URL completa de la imagen a subir

    Returns:
        tuple (bool, attachment_id o None, source_url o None)
    """
    print(f"   📷 Preparando imagen: {str(url_imagen_externa)[:80]}...")

    image_url = url_imagen_externa
    local_path = _path_local_desde_url_temporal(url_imagen_externa)

    try:
        if local_path:
            if not os.path.isfile(local_path):
                print(f"   ❌ Foto temporal no encontrada: {local_path}")
                return False, None, None
            with open(local_path, 'rb') as fh:
                image_bytes = fh.read()
            filename = os.path.basename(local_path)
        else:
            # Asegurarnos de que la URL tenga esquema
            if not url_imagen_externa.startswith(('http://', 'https://')):
                image_url = 'http://' + url_imagen_externa
                print(f"   🔧 URL sin esquema, intentando con: {image_url}")

            # Descargar la imagen (sin seguir redirect para obtener el archivo original)
            resp = _request_with_retry("GET", image_url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            image_bytes = resp.content
            filename = _nombre_archivo_desde_url(url_imagen_externa)
    except Exception as e:
        # Si falló con http://, intentar con https:// si empezamos con http://
        if local_path or url_imagen_externa.startswith(('http://', 'https://')):
            print(f"   ❌ Error obteniendo imagen: {e}")
            return False, None, None

        # Intentar con https:// si probamos con http://
        if image_url.startswith('http://'):
            https_url = 'https://' + image_url[7:]
            print(f"   🔧 HTTP falló, intentando HTTPS: {https_url}")
            try:
                resp = _request_with_retry("GET", https_url, timeout=30, allow_redirects=True)
                resp.raise_for_status()
                image_bytes = resp.content
                filename = _nombre_archivo_desde_url(url_imagen_externa)
            except Exception as e2:
                print(f"   ❌ Error descargando imagen (también falló HTTPS): {e2}")
                return False, None, None
        else:
            print(f"   ❌ Error descargando imagen: {e}")
            return False, None, None

    if not image_bytes:
        return False, None, None

    if 'filename' not in locals():
        filename = _nombre_archivo_desde_url(url_imagen_externa)

    if len(image_bytes) > 10 * 1024 * 1024:
        print("   ❌ Imagen demasiado grande (>10MB)")
        return False, None, None

    image_bytes = _aplicar_watermark(image_bytes)
    if WATERMARK_ENABLED:
        filename = f"{os.path.splitext(filename)[0]}.jpg"
    mime_type = _obtener_mime_type(image_bytes)

    print(f"   📤 Subiendo a WP: {filename} ({mime_type}, {len(image_bytes):,} bytes)")

    try:
        # Prepare file for multipart upload
        files = {
            'file': (filename, image_bytes, mime_type)
        }
        
        # Get auth headers (without Content-Type as requests will set it for multipart)
        headers = _get_wp_headers()
        # Remove Content-Type if present to avoid conflicts with multipart boundary
        headers.pop('Content-Type', None)

        resp = _request_with_retry(
            "POST",
            f"{WP_URL}/wp-json/wp/v2/media",
            headers=headers,
            files=files,
            timeout=60
        )

        if resp.status_code in (200, 201):
            data = resp.json()
            attachment_id = data['id']
            print(f"   ✅ Imagen subida: ID {attachment_id}")
            print(f"   URL: {data.get('source_url', '')}")
            return True, attachment_id, data.get('source_url')
        else:
            print(f"   ❌ Error subiendo imagen: {resp.status_code}")
            print(f"   {resp.text[:500]}")
            return False, None, None

    except Exception as e:
        print(f"   ❌ Excepción subiendo imagen: {e}")
        return False, None, None


# =============================================================================
# PUBLICAR EN WORDPRESS
# =============================================================================

def _insertar_fotos_entre_parrafos(articulo_html, fotos_urls):
    if not fotos_urls:
        return articulo_html

    import re

    articulo = (articulo_html or '').strip()
    if not articulo:
        return articulo_html

    # Caso HTML con <p>...</p>
    parrafos_html = re.findall(r'<p\b[^>]*>.*?</p>', articulo, flags=re.IGNORECASE | re.DOTALL)
    if parrafos_html:
        total = len(parrafos_html)
        posiciones = [max(1, total // 3), max(2, (2 * total) // 3)]
        out = []
        for idx, p in enumerate(parrafos_html, start=1):
            out.append(p)
            for foto_idx, pos in enumerate(posiciones[:len(fotos_urls)]):
                if idx == pos:
                    url = fotos_urls[foto_idx]
                    out.append(f'<figure class="wp-block-image size-large"><img src="{url}" alt="" /></figure>')
        return "\n".join(out)

    # Caso texto plano: separar por líneas en blanco y envolver en <p>
    bloques = [b.strip() for b in re.split(r'\n\s*\n', articulo) if b.strip()]
    if not bloques:
        return articulo_html

    total = len(bloques)
    posiciones = [max(1, total // 3), max(2, (2 * total) // 3)]
    out = []
    fotos_insertadas = 0
    for idx, bloque in enumerate(bloques, start=1):
        out.append(f"<p>{bloque}</p>")
        for foto_idx, pos in enumerate(posiciones[:len(fotos_urls)]):
            if idx == pos:
                url = fotos_urls[foto_idx]
                out.append(f'<figure class="wp-block-image size-large"><img src="{url}" alt="" /></figure>')
                fotos_insertadas += 1

    # Fallback: si no se insertaron todas, agregarlas al final
    for url in fotos_urls[fotos_insertadas:]:
        out.append(f'<figure class="wp-block-image size-large"><img src="{url}" alt="" /></figure>')

    return "\n".join(out)


def publicar_en_wordpress(titulo, resumen, contenido, categoria_id=None, featured_media_id=None):
    """
    Envía el artículo a WordPress via REST API.

    Crea un nuevo post con:
    - title: el titulo generado por IA
    - content: el cuerpo del artículo
    - excerpt: el resumen
    - status: "publish" (publicado inmediatamente)
    - categories: la categoría elegida
    - comment_status: "open" (comentarios abiertos)
    - featured_media: la imagen destacada (attachment_id)

    Args:
        titulo: string con el título del artículo
        resumen: string con el lead/resumen
        contenido: string con el cuerpo del artículo
        categoria_id: int o None con el ID de la categoría en WP
        featured_media_id: int o None con el attachment_id de la imagen destacada

    Returns:
        tuple (bool, str): (éxito, url_del_post) — url es None si falló
    """
    # Generar slug automáticamente desde el título
    slug = _normalizar_slug(titulo)

    # Armar el payload del post
    post_data = {
        "title": titulo,
        "content": contenido,
        "excerpt": resumen,
        "status": "publish",
        "slug": slug,
        "comment_status": "open",
    }

    # Si hay categoría, agregarla
    if categoria_id:
        post_data["categories"] = [categoria_id]

    # Si hay imagen destacada, asociarla
    if featured_media_id:
        post_data["featured_media"] = featured_media_id

    headers = _get_wp_headers()
    response = _request_with_retry(
        "POST",
        f"{WP_URL}/wp-json/wp/v2/posts",
        headers=headers,
        json=post_data,
        timeout=30
    )
    if response.status_code == 201:
        data = response.json()
        print(f"   ✅ Publicado correctamente!")
        print(f"   URL: {data.get('link')}")
        return True, data.get('link')
    else:
        print(f"   ❌ Error al publicar: {response.status_code}")
        print(response.text[:500])
        return False, None


# =============================================================================
# FUNCIÓN PRINCIPAL: PUBLICAR UN CLUSTER
# =============================================================================

def publicar_cluster(cluster_id):
    """
    Publica un cluster en WordPress.

    Flujo:
      1. Obtener el cluster de la DB (debe tener contenido_ia)
      2. Parsear el JSON con título, resumen, artículo, categoría
      3. Buscar o crear la categoría en WordPress
      4. Publicar en WP
      5. Actualizar la DB con la URL de WP y marcar como publicado

    Args:
        cluster_id: ID del cluster en clusters_editoriales

    Returns:
        dict con {ok: bool, url_wp: str|None, mensaje: str}
    """
    print(f"\n{'='*80}")
    print(f"📤 PUBLICANDO CLUSTER ID: {cluster_id} EN WORDPRESS")
    print(f"{'='*80}\n")

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
                    fotos_secundarias
                FROM clusters_editoriales
                WHERE id = %s
            """, (cluster_id,))
            cluster = cur.fetchone()

        if not cluster:
            return {"ok": False, "mensaje": f"Cluster {cluster_id} no encontrado"}

        if not cluster.get('contenido_ia'):
            return {
                "ok": False,
                "mensaje": "El cluster no tiene contenido generado por IA. Generalo primero."
            }

        if cluster.get('estado_publicacion') == 'publicado':
            return {
                "ok": False,
                "mensaje": "Este cluster ya fue publicado."
            }

        # Parsear el contenido IA (es un JSON guardado como texto en la DB)
        try:
            contenido = cluster['contenido_ia']
            # Puede venir como dict directo o como string JSON
            if isinstance(contenido, str):
                contenido = json.loads(contenido)
        except (json.JSONDecodeError, TypeError) as e:
            return {
                "ok": False,
                "mensaje": f"Error parseando contenido_ia: {e}"
            }

        _validar_contenido_publicable(contenido)

        titulo = contenido.get('titulo', 'Sin título')
        resumen = contenido.get('resumen', '')
        articulo = contenido.get('articulo', '')
        categoria_nombre = contenido.get('categoria', '')
        foto_principal = cluster.get('foto_principal')
        fotos_secundarias = cluster.get('fotos_secundarias') or []
        if isinstance(fotos_secundarias, str):
            try:
                fotos_secundarias = json.loads(fotos_secundarias)
            except (json.JSONDecodeError, TypeError):
                fotos_secundarias = []
        fotos_secundarias = [u for u in fotos_secundarias if isinstance(u, str) and u.strip()][:2]

        print(f"📋 Artículo a publicar:")
        print(f"   Título: {titulo}")
        print(f"   Categoría: {categoria_nombre}")
        print(f"   Resumen: {resumen[:80]}...")
        print(f"   Foto principal: {foto_principal or 'Sin foto'}")
        print(f"   Fotos secundarias: {len(fotos_secundarias)}")

        # 1. Obtener o crear categoría en WordPress
        cat_id = obtener_o_crear_categoria(categoria_nombre)

        # 2. Subir imagen destacada si hay foto seleccionada
        featured_media_id = None
        if foto_principal:
            exito_img, featured_media_id, _featured_url = subir_imagen_a_wordpress(foto_principal)
            if not exito_img:
                # La imagen falló pero seguimos con la publicación
                print("   ⚠️  Continuando sin imagen destacada")
                featured_media_id = None

        fotos_secundarias_subidas = []
        for foto in fotos_secundarias:
            exito_sec, _sec_id, sec_url = subir_imagen_a_wordpress(foto)
            if exito_sec and sec_url:
                fotos_secundarias_subidas.append(sec_url)

        articulo_final = _insertar_fotos_entre_parrafos(articulo, fotos_secundarias_subidas)

        # 3. Publicar en WordPress (con imagen asociada si hay)
        print("   Publicando en WordPress...")
        exito, url_wp = publicar_en_wordpress(
            titulo, resumen, articulo_final, cat_id, featured_media_id
        )

        if not exito or not url_wp:
            _guardar_error_publicacion(conn, cluster_id, "Falló la publicación en WordPress")
            return {
                "ok": False,
                "mensaje": "Falló la publicación en WordPress. Revisar logs."
            }

        # 3. Actualizar la DB con la URL de WP y marcar como publicado
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE clusters_editoriales
                SET
                    url_wp = %s,
                    estado_publicacion = 'publicado',
                    ultima_publicacion = NOW(),
                    veces_publicado = veces_publicado + 1,
                    actualizado_en = NOW()
                WHERE id = %s
            """, (url_wp, cluster_id))
        conn.commit()

        _limpiar_fotos_temporales_cluster(cluster_id)

        print(f"\n✅ Cluster {cluster_id} publicado exitosamente!")
        print(f"   URL WordPress: {url_wp}")
        return {"ok": True, "url_wp": url_wp}

    except Exception as e:
        conn.rollback()
        try:
            _guardar_error_publicacion(conn, cluster_id, str(e))
        except Exception:
            pass
        logger.error("❌ Error general publicando cluster %s: %s", cluster_id, e)
        return {"ok": False, "mensaje": str(e)}
    finally:
        conn.close()


# =============================================================================
# MAIN — ejecución directa
# =============================================================================

if __name__ == "__main__":
    """
    Uso directo: python publicapress.py [cluster_id]

    Sin argumentos: busca clusters con estado_publicacion = 'generado'
                    y publica el primero.

    Con argumentos:  python publicapress.py 42
                    publica el cluster 42 específicamente.
    """
    import sys

    print("🚀 Iniciando publicapress.py — Publicación en WordPress")

    # 1. Probar conexión con WP antes de hacer nada
    if not test_wordpress_auth():
        print("❌ Deteniendo script por fallo de autenticación.")
        sys.exit(1)

    # 2. Buscar cluster a publicar
    cluster_id = None

    if len(sys.argv) > 1:
        # Argumento: ID del cluster
        cluster_id = int(sys.argv[1])
        print(f"📌 Modo manual: cluster {cluster_id}")
    else:
        # Buscar automáticamente el primer cluster listo
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM clusters_editoriales
                    WHERE estado_publicacion = 'generado'
                    ORDER BY actualizado_en DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                if row:
                    cluster_id = row['id']
                    print(f"📌 Modo automático: primer cluster generado = {cluster_id}")
        finally:
            conn.close()

    if not cluster_id:
        print("No hay clusters listos para publicar (estado = 'generado').")
        sys.exit(0)

    # 3. Publicar
    resultado = publicar_cluster(cluster_id)

    if resultado["ok"]:
        print(f"\n✅ Done. WordPress: {resultado['url_wp']}")
    else:
        print(f"\n❌ Error: {resultado.get('mensaje')}")