from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import httpx
import os
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

from config import API_KEY, API_BASE_URL, IMAGEN_BASE_URL, ADMIN_PASSWORD, ADMIN_COOKIE_NAME, ADMIN_COOKIE_DURATION_HOURS, SECRET_KEY, ADMIN_MAX_ATTEMPTS, ADMIN_LOCKOUT_MINUTES, ADMIN_LOG_FILE, DOMINIO
from utils import generar_meta_tags_home, generar_meta_tags_noticia, formatear_slug, inyectar_meta_tags

app = FastAPI(title="TRH Noticias - Frontend")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

login_attempts: dict = {}


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def log_failed_login(ip: str, password: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"{timestamp} | IP: {ip} | Password: {password}\n"
    try:
        os.makedirs(os.path.dirname(ADMIN_LOG_FILE), exist_ok=True)
        with open(ADMIN_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        import sys
        print(f"[LOG ERROR] Failed to write login log: {e}", file=sys.stderr)


def is_ip_blocked(ip: str) -> bool:
    if ip not in login_attempts:
        return False
    attempts_data = login_attempts[ip]
    if attempts_data["count"] >= ADMIN_MAX_ATTEMPTS:
        locked_time = attempts_data["locked_at"]
        if datetime.now() < locked_time + timedelta(minutes=ADMIN_LOCKOUT_MINUTES):
            return True
        del login_attempts[ip]
    return False


def render_template(filename, **context):
    path = os.path.join(BASE_DIR, "templates", filename)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    for key, value in context.items():
        content = content.replace(f"{{{{ {key} }}}}", str(value))
        content = content.replace(f"{{{{ {key}.id }}}}", str(value.get("id", "") if isinstance(value, dict) else ""))
    
    return content


async def obtener_noticias(desde_id=None, limite=10, categoria=None, categoria_id=None):
    url = f"{API_BASE_URL}/noticias"
    params = {"limite": limite + 1}
    if desde_id:
        params["desde_id"] = desde_id
    if categoria:
        params["categoria"] = categoria
    if categoria_id:
        params["categoria_id"] = categoria_id
    
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


# Cache para mapa de categorías (nombre -> id)
categorias_cache = {}


@app.on_event("startup")
async def startup():
    """Cargar categorías al iniciar."""
    global categorias_cache
    try:
        categorias = await obtener_categorias()
        categorias_cache = {cat["nombre"]: cat["id"] for cat in categorias}
    except Exception as e:
        print(f"[STARTUP] Error cargando categorías: {e}")


async def obtener_categorias():
    """Obtiene todas las categorías del backend."""
    global categorias_cache
    url = f"{API_BASE_URL}/categorias"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        categorias = response.json()
        # Crear mapa: nombre -> id e id -> nombre
        categorias_cache = {cat["nombre"]: cat["id"] for cat in categorias}
        return categorias


def get_categoria_link(nombre_cat):
    """Genera enlace de categoría con formato /categoria/{id}-{slug}."""
    if nombre_cat in categorias_cache:
        cat_id = categorias_cache[nombre_cat]
        slug = formatear_slug(nombre_cat)
        return f"/categoria/{cat_id}-{slug}"
    # Fallback si no hay cache
    slug = formatear_slug(nombre_cat)
    return f"/categoria/{slug}"


def format_noticia_card(noticia, api_base, next_cursor=None, hay_mas=False):
    img_url = ""
    if noticia.get("imagen_url"):
        img_path = noticia["imagen_url"]
        if img_path.startswith("/imagenes/"):
            img_path = img_path.replace("/imagenes/", "")
        img_url = f"{api_base}/{img_path}"
    
    # Categorías como hipervínculos
    categorias_html = ""
    if noticia.get("categorias"):
        cats_links = []
        for cat in noticia["categorias"]:
            cats_links.append(f'<a href="{get_categoria_link(cat)}" class="categoria-tag">{cat}</a>')
        categorias_html = f'<div class="noticias-categorias">{"".join(cats_links)}</div>'
    
    resumen = noticia.get("resumen_ia", "")
    fuente = noticia.get("fuente", "")
    fecha = str(noticia.get("fecha", ""))[:10] if noticia.get("fecha") else ""
    titulo = noticia.get("titulo", "")
    noticia_id = noticia.get("id", "")
    slug = formatear_slug(titulo)
    link_interno = f"/noticia/{noticia_id}-{slug}"
    
    img_html = f'<img src="{img_url}" alt="{titulo}" class="noticia-imagen" loading="lazy">' if img_url else '<div class="noticia-imagen-placeholder"><span>📰</span></div>'
    
    card = f'''
<article class="noticia-card">
    {img_html}
    <div class="noticia-contenido">
        <h2 class="noticia-titulo">
            <a href="{link_interno}">{titulo}</a>
        </h2>
        {categorias_html}
        <p class="noticia-resumen">{resumen}</p>
        <div class="noticia-meta">
            <span class="noticia-fuente">{fuente}</span>
            <span class="noticia-fecha">{fecha}</span>
        </div>
    </div>
</article>'''
    
    return card


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        data = await obtener_noticias(limite=10)
        noticias = data.get("noticias", [])
        hay_mas = data.get("hay_mas", False)
        next_cursor = data.get("siguiente_cursor")
        
        path = os.path.join(BASE_DIR, "templates", "base.html")
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        
        path_index = os.path.join(BASE_DIR, "templates", "index.html")
        with open(path_index, "r", encoding="utf-8") as f:
            index_html = f.read()
        
        cards_html = "".join([format_noticia_card(n, IMAGEN_BASE_URL) for n in noticias])
        
        # El último card hace de sentinel para scroll infinito
        if hay_mas and next_cursor and cards_html:
            # Agregar atributos HTMX al último card
            cards_html = cards_html + f'''
<div hx-get="/noticias-scroll?desde_id={next_cursor}" 
     hx-trigger="revealed once" 
     hx-swap="afterend"
     class="sentinel-loader"
     style="height:1px;">
</div>'''
        
        content = index_html.replace("<!-- NOTICIAS -->", cards_html)
        html = html.replace("<!-- CONTENT -->", content)
        
        # Inyectar meta tags para homepage
        meta_tags = generar_meta_tags_home(DOMINIO)
        html = inyectar_meta_tags(html, meta_tags)
        
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<h1>Error: {e}</h1><p>Backend: {API_BASE_URL}</p>")


@app.get("/noticias-scroll", response_class=HTMLResponse)
async def noticias_scroll(request: Request, desde_id: int, categoria: str = None, categoria_id: int = None):
    try:
        data = await obtener_noticias(desde_id=desde_id, limite=10, categoria=categoria, categoria_id=categoria_id)
        noticias = data.get("noticias", [])
        hay_mas = data.get("hay_mas", False)
        next_cursor = data.get("siguiente_cursor")
        
        cards_html = "".join([format_noticia_card(n, IMAGEN_BASE_URL) for n in noticias])
        
        # Agregar sentinel al final si hay más noticias
        # Incluir la categoría en la URL del sentinel si aplica
        sentinel_url = f"/noticias-scroll?desde_id={next_cursor}"
        if categoria:
            sentinel_url += f"&categoria={categoria}"
        if categoria_id:
            sentinel_url += f"&categoria_id={categoria_id}"
        
        if hay_mas and next_cursor and cards_html:
            cards_html = cards_html + f'''
<div hx-get="{sentinel_url}" 
     hx-trigger="revealed once" 
     hx-swap="afterend"
     class="sentinel-loader"
     style="height:1px;">
</div>'''
        
        return HTMLResponse(cards_html)
    except Exception:
        return HTMLResponse("")


@app.get("/contacto", response_class=HTMLResponse)
def contacto(request: Request):
    path = os.path.join(BASE_DIR, "templates", "base.html")
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    
    path_contacto = os.path.join(BASE_DIR, "templates", "contacto.html")
    with open(path_contacto, "r", encoding="utf-8") as f:
        contacto_html = f.read()
    
    html = html.replace("<!-- CONTENT -->", contacto_html)
    html = html.replace("<title>TRH Noticias</title>", "<title>TRH Noticias - Contacto</title>")
    
    return HTMLResponse(html)


@app.get("/categoria/{id_slug}", response_class=HTMLResponse)
async def categoria(request: Request, id_slug: str):
    """
    Página de categoría: muestra noticias filtradas por categoría.
    URL: /categoria/1-policiales, /categoria/1-la-mas-visto, etc.
    """
    import re
    match = re.match(r'^(\d+)-', id_slug)
    if not match:
        return HTMLResponse("<h1>Categoría no encontrada</h1>", status_code=404)
    
    categoria_id = int(match.group(1))
    
    try:
        # Obtener noticias de esa categoría por ID
        data = await obtener_noticias(limite=10, categoria_id=categoria_id)
        noticias = data.get("noticias", [])
        hay_mas = data.get("hay_mas", False)
        next_cursor = data.get("siguiente_cursor")
        
        # Obtener nombre de la categoría desde las noticias
        nombre_categoria = ""
        if noticias and noticias[0].get("categorias"):
            nombre_categoria = noticias[0]["categorias"][0]
        
        # Cargar plantillas
        path = os.path.join(BASE_DIR, "templates", "base.html")
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        
        path_categoria = os.path.join(BASE_DIR, "templates", "categoria.html")
        with open(path_categoria, "r", encoding="utf-8") as f:
            categoria_html = f.read()
        
        # Generar cards con nuevo formato de enlaces
        cards_html = "".join([format_noticia_card(n, IMAGEN_BASE_URL) for n in noticias])
        
        # Agregar sentinel al final si hay más noticias
        sentinel_url = f"/noticias-scroll?desde_id={next_cursor}&categoria={categoria_id}"
        if hay_mas and next_cursor and cards_html:
            cards_html = cards_html + f'''
<div hx-get="{sentinel_url}" 
     hx-trigger="revealed once" 
     hx-swap="afterend"
     class="sentinel-loader"
     style="height:1px;">
</div>'''
        
        # Reemplazar contenido
        categoria_html = categoria_html.replace("<!-- NOTICIAS_CATEGORIA -->", cards_html)
        html = html.replace("<!-- CONTENT -->", categoria_html)
        
        # Título de la página
        titulo_pagina = f"Noticias de {nombre_categoria} - TRH Noticias" if nombre_categoria else "Noticias - TRH Noticias"
        html = html.replace("{{ PAGE_TITLE }}", titulo_pagina)
        
        # Meta tags para SEO de categoría
        meta_tags = {
            "PAGE_TITLE": titulo_pagina,
            "META_DESCRIPTION": f"Últimas noticias de {nombre_categoria.capitalize()} en TRH Noticias. Stay informed with the latest {nombre_categoria} news.",
            "CANONICAL_URL": f"https://{DOMINIO}/categoria/{nombre_categoria}",
            "OG_TITLE": titulo_pagina,
            "OG_DESCRIPTION": f"Noticias de {nombre_categoria.capitalize()}",
            "OG_IMAGE": f"https://{DOMINIO}/static/images/og-default.jpg",
            "OG_URL": f"https://{DOMINIO}/categoria/{nombre_categoria}",
            "OG_TYPE": "website",
            "TWITTER_TITLE": titulo_pagina,
            "TWITTER_DESCRIPTION": f"Noticias de {nombre_categoria.capitalize()}",
            "TWITTER_IMAGE": f"https://{DOMINIO}/static/images/og-default.jpg",
            "SCHEMA_JSON": "{}"
        }
        html = inyectar_meta_tags(html, meta_tags)
        
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<h1>Error: {e}</h1>")


async def obtener_noticia_por_id(noticia_id: int):
    """Obtiene una noticia individual por su ID."""
    url = f"{API_BASE_URL}/noticias/{noticia_id}"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


@app.get("/noticia/{id_slug}", response_class=HTMLResponse)
async def noticia_individual(request: Request, id_slug: str):
    """
    Página individual de noticia: /noticia/{id}-{slug}
    El ID se usa para buscar en la DB, el slug es solo decorativo para SEO.
    """
    # Extraer el ID del path - el ID es el primer grupo de dígitos al inicio
    # Ejemplo: "123-nina-de-3-anos-atropellada" -> ID = 123
    import re
    match = re.match(r'^(\d+)', id_slug)
    if not match:
        return HTMLResponse("<h1>Noticia no encontrada</h1>", status_code=404)
    
    try:
        noticia_id = int(match.group(1))
    except ValueError:
        return HTMLResponse("<h1>Noticia no encontrada</h1>", status_code=404)
    
    try:
        # Obtener noticia del backend
        noticia = await obtener_noticia_por_id(noticia_id)
        
        # Cargar plantilla base
        path = os.path.join(BASE_DIR, "templates", "base.html")
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        
        # Cargar plantilla de noticia individual
        path_noticia = os.path.join(BASE_DIR, "templates", "noticia.html")
        with open(path_noticia, "r", encoding="utf-8") as f:
            noticia_html = f.read()
        
        # Preparar datos de la noticia
        titulo = noticia.get("titulo", "")
        categorias = noticia.get("categorias", [])
        fuente = noticia.get("fuente", "")
        fecha = str(noticia.get("fecha", ""))[:10] if noticia.get("fecha") else ""
        resumen = noticia.get("resumen", "")
        resumen_ia = noticia.get("resumen_ia", "")
        link_original = noticia.get("link_original", "")
        
        # Procesar imagen
        img_url = ""
        if noticia.get("imagen_url"):
            img_path = noticia["imagen_url"]
            if img_path.startswith("/imagenes/"):
                img_path = img_path.replace("/imagenes/", "")
            img_url = f"{IMAGEN_BASE_URL}/{img_path}"
        
        # Generar HTML de categorías
        categorias_html = ""
        if categorias:
            cats = "".join([f'<span class="categoria-tag">{cat}</span>' for cat in categorias])
            categorias_html = f'<div class="noticias-categorias">{cats}</div>'
        
        # Generar HTML de imagen
        img_html = f'<img src="{img_url}" alt="{titulo}" class="noticia-imagen" loading="lazy">' if img_url else '<div class="noticia-imagen-placeholder"><span>📰</span></div>'
        
        # Reemplazar placeholders en la plantilla de noticia
        noticia_html = noticia_html.replace("<!-- NOTICIA_TITULO -->", f"<h2 class=\"noticia-titulo\">{titulo}</h2>")
        noticia_html = noticia_html.replace("<!-- NOTICIA_TITULO_TEXTO -->", titulo)
        noticia_html = noticia_html.replace("<!-- NOTICIA_IMAGEN -->", img_html)
        noticia_html = noticia_html.replace("<!-- NOTICIA_CATEGORIAS -->", categorias_html)
        noticia_html = noticia_html.replace("<!-- NOTICIA_FUENTE -->", fuente)
        noticia_html = noticia_html.replace("<!-- NOTICIA_FECHA -->", fecha)
        noticia_html = noticia_html.replace("<!-- NOTICIA_RESUMEN_IA -->", f"<p>{resumen_ia}</p>" if resumen_ia else "")
        noticia_html = noticia_html.replace("<!-- NOTICIA_RESUMEN -->", f"<p>{resumen}</p>" if resumen else "")
        noticia_html = noticia_html.replace("<!-- NOTICIA_LINK_ORIGINAL -->", link_original)
        noticia_html = noticia_html.replace("<!-- NOTICIA_FUENTE_LINK -->", fuente)
        
        # Insertar contenido en base.html
        html = html.replace("<!-- CONTENT -->", noticia_html)
        
        # Generar e inyectar meta tags SEO
        meta_tags = generar_meta_tags_noticia(noticia, DOMINIO, IMAGEN_BASE_URL)
        html = inyectar_meta_tags(html, meta_tags)
        
        return HTMLResponse(html)
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return HTMLResponse("<h1>Noticia no encontrada</h1>", status_code=404)
        return HTMLResponse(f"<h1>Error: {e}</h1>", status_code=500)
    except Exception as e:
        return HTMLResponse(f"<h1>Error al cargar la noticia: {e}</h1>", status_code=500)


def verify_admin_session(request: Request) -> bool:
    cookie_value = request.cookies.get(ADMIN_COOKIE_NAME)
    if not cookie_value:
        return False
    try:
        payload = jwt.decode(cookie_value, SECRET_KEY, algorithms=["HS256"])
        return payload.get("admin") == True
    except JWTError:
        return False


async def obtener_noticias_pendientes():
    url = f"{API_BASE_URL}/admin/noticias-pendientes"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


async def accion_noticia(noticia_id: int, accion: str):
    url = f"{API_BASE_URL}/admin/noticias/{noticia_id}/accion"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, params={"accion": accion}, headers=headers)
        response.raise_for_status()
        return response.json()


@app.get("/admin03", response_class=HTMLResponse)
async def admin(request: Request):
    return await admin_get(request)


async def admin_get(request: Request):
    if not verify_admin_session(request):
        return RedirectResponse(url="/admin03-login")
    
    try:
        noticias = await obtener_noticias_pendientes()

        path = os.path.join(BASE_DIR, "templates", "base.html")
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        cantidad = len(noticias)
        
        if not noticias:
            content = f'<div class="noticias-container"><p>No hay noticias pendientes.</p></div>'
        else:
            cards_html = ""
            for n in noticias:
                cards_html += f'''
<article class="noticia-card">
    <div class="admin-botones">
        <form method="POST" action="/admin03/accion" style="display:inline;">
            <input type="hidden" name="noticia_id" value="{n["id"]}">
            <input type="hidden" name="accion" value="aprobar">
            <button type="submit" class="btn-aprobar">Aprobar</button>
        </form>
        <form method="POST" action="/admin03/accion" style="display:inline;">
            <input type="hidden" name="noticia_id" value="{n["id"]}">
            <input type="hidden" name="accion" value="rechazar">
            <button type="submit" class="btn-rechazar">Rechazar</button>
        </form>
    </div>
    <h2 class="noticia-titulo">{n["titulo"]}</h2>
    <div class="noticia-meta">
        <span class="noticia-fuente">{n.get("fuente", "")}</span>
    </div>
    <a href="{n["link"]}" target="_blank" rel="noopener" class="noticia-link">Ver origen</a>
</article>'''

            content = f'''
<div class="admin-header">
    <h2>{cantidad} noticia{"s" if cantidad != 1 else ""} pendiente{"s" if cantidad != 1 else ""}</h2>
    <div class="admin-header-buttons">
        <a href="/admin03-logout" class="btn-cerrar">Cerrar sesión</a>
        <a href="/" class="btn-volver">Volver al inicio</a>
    </div>
</div>
<div class="noticias-container">{cards_html}</div>'''

        html = html.replace("<!-- CONTENT -->", content)
        html = html.replace("<title>TRH Noticias</title>", "<title>TRH Noticias - Admin</title>")

        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<h1>Error: {e}</h1>")


@app.post("/admin03/accion", response_class=HTMLResponse)
async def admin_accion(request: Request):
    if not verify_admin_session(request):
        return RedirectResponse(url="/admin03-login")
    
    form = await request.form()
    noticia_id = int(form.get("noticia_id"))
    accion = form.get("accion")

    await accion_noticia(noticia_id, accion)

    return await admin_get(request)


@app.get("/admin03-login", response_class=HTMLResponse)
def admin_login(request: Request):
    if verify_admin_session(request):
        return RedirectResponse(url="/admin03")
    
    path = os.path.join(BASE_DIR, "templates", "base.html")
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    content = '''
<div class="login-container">
    <h2>Panel de Administración</h2>
    <form method="POST" action="/admin03-verify">
        <input type="password" name="password" placeholder="Contraseña" required>
        <button type="submit" class="btn-login">Ingresar</button>
    </form>
</div>'''

    html = html.replace("<!-- CONTENT -->", content)
    html = html.replace("<title>TRH Noticias</title>", "<title>TRH Noticias - Login Admin</title>")

    return HTMLResponse(html)


@app.post("/admin03-verify", response_class=HTMLResponse)
async def admin_verify(request: Request):
    client_ip = get_client_ip(request)
    
    if is_ip_blocked(client_ip):
        path = os.path.join(BASE_DIR, "templates", "base.html")
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        content = '''
<div class="login-container">
    <h2>Panel de Administración</h2>
    <p class="error">Demasiados intentos fallidos. Intenta de nuevo en 15 minutos.</p>
</div>'''

        html = html.replace("<!-- CONTENT -->", content)
        html = html.replace("<title>TRH Noticias</title>", "<title>TRH Noticias - Login Bloqueado</title>")

        return HTMLResponse(html)
    
    form = await request.form()
    password = form.get("password")

    if password != ADMIN_PASSWORD:
        log_failed_login(client_ip, password)
        
        if client_ip not in login_attempts:
            login_attempts[client_ip] = {"count": 0, "locked_at": None}
        login_attempts[client_ip]["count"] += 1
        
        if login_attempts[client_ip]["count"] >= ADMIN_MAX_ATTEMPTS:
            login_attempts[client_ip]["locked_at"] = datetime.now()
        
        path = os.path.join(BASE_DIR, "templates", "base.html")
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        remaining = ADMIN_MAX_ATTEMPTS - login_attempts[client_ip]["count"]
        content = f'''
<div class="login-container">
    <h2>Panel de Administración</h2>
    <form method="POST" action="/admin03-verify">
        <input type="password" name="password" placeholder="Contraseña" required>
        <button type="submit" class="btn-login">Ingresar</button>
    </form>
    <p class="error">Contraseña incorrecta. Intentos restantes: {remaining}</p>
</div>'''

        html = html.replace("<!-- CONTENT -->", content)
        html = html.replace("<title>TRH Noticias</title>", "<title>TRH Noticias - Login Admin</title>")

        return HTMLResponse(html)

    if client_ip in login_attempts:
        del login_attempts[client_ip]
    
    expires = datetime.now(timezone.utc) + timedelta(hours=ADMIN_COOKIE_DURATION_HOURS)
    token = jwt.encode({"admin": True, "exp": expires}, SECRET_KEY, algorithm="HS256")

    response = RedirectResponse(url="/admin03", status_code=303)
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=token,
        expires=datetime.now(timezone.utc) + timedelta(hours=ADMIN_COOKIE_DURATION_HOURS),
        httponly=True,
        samesite="lax"
    )
    return response


@app.get("/admin03-logout")
def admin_logout():
    response = RedirectResponse(url="/admin03-login")
    response.delete_cookie(ADMIN_COOKIE_NAME)
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)