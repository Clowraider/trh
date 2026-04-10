from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
import os

from config import API_KEY, CORS_ORIGINS, CARPETA_IMAGENES
from database import get_connection
from models import Noticia, RespuestaNoticias

app = FastAPI(title="TRH Noticias API", docs_url=None, redoc_url=None)

# CORS — solo permite pedidos desde los origenes configurados en config.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# sirve las imagenes como archivos estaticos
# GET /imagenes/nombre.jpg → devuelve la imagen guardada en CARPETA_IMAGENES
if os.path.exists(CARPETA_IMAGENES):
    app.mount("/imagenes", StaticFiles(directory=CARPETA_IMAGENES), name="imagenes")

# mecanismo de verificacion de la API key
# el cliente debe enviar el header: Authorization: Bearer TU_API_KEY
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

def verificar_api_key(api_key: str = Depends(api_key_header)):
    key = api_key.replace("Bearer ", "") if api_key else ""
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="API key invalida")
    return key


@app.get("/categorias")
def obtener_categorias(
    _: str = Depends(verificar_api_key)
):
    """Devuelve todas las categorías disponibles."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre FROM categorias ORDER BY nombre")
    categorias = [{"id": r["id"], "nombre": r["nombre"]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return categorias


@app.get("/noticias", response_model=RespuestaNoticias)
def obtener_noticias(
    limite: int = Query(default=10, le=50),
    desde_id: int = Query(default=None),
    categoria: str = Query(default=None),
    categoria_id: int = Query(default=None),
    _: str = Depends(verificar_api_key)
):
    conn = get_connection()
    cur = conn.cursor()
    
    # Determinar si hay filtro por categoría
    tiene_categoria = categoria and categoria.strip()
    
    # Base de la consulta - sin joins a tablas de categorías
    base_from = """
        FROM noticias n
        JOIN contenido c ON c.noticia_id = n.id
        WHERE n.estado = 'completo'
        AND c.resumen_ia IS NOT NULL
        AND c.resumen_ia != ''
    """
    
    # Agregar filtro de categoría si corresponde usando EXISTS
    if tiene_categoria:
        base_from += """
        AND EXISTS (
            SELECT 1 FROM noticias_categorias nc
            JOIN categorias cat ON cat.id = nc.categoria_id
            WHERE nc.noticia_id = n.id 
            AND LOWER(cat.nombre) = LOWER(%s)
        )"""
    
    # Filtro por categoria_id
    if categoria_id:
        base_from += " AND EXISTS (SELECT 1 FROM noticias_categorias nc WHERE nc.noticia_id = n.id AND nc.categoria_id = %s)"
    
    # Paginación por cursor
    if desde_id:
        if tiene_categoria:
            cur.execute(f"""
                SELECT n.id, n.titulo, n.fuente, n.link as link_original,
                       n.fecha_publicacion as fecha,
                       c.imagen_url, c.resumen, c.resumen_ia
                {base_from}
                AND n.id < %s
                ORDER BY n.id DESC
                LIMIT %s
            """, (categoria.strip(), desde_id, limite + 1))
        elif categoria_id:
            cur.execute(f"""
                SELECT n.id, n.titulo, n.fuente, n.link as link_original,
                       n.fecha_publicacion as fecha,
                       c.imagen_url, c.resumen, c.resumen_ia
                {base_from}
                AND n.id < %s
                ORDER BY n.id DESC
                LIMIT %s
            """, (categoria_id, desde_id, limite + 1))
        else:
            cur.execute(f"""
                SELECT n.id, n.titulo, n.fuente, n.link as link_original,
                       n.fecha_publicacion as fecha,
                       c.imagen_url, c.resumen, c.resumen_ia
                {base_from}
                AND n.id < %s
                ORDER BY n.id DESC
                LIMIT %s
            """, (desde_id, limite + 1))
    else:
        if tiene_categoria:
            cur.execute(f"""
                SELECT n.id, n.titulo, n.fuente, n.link as link_original,
                       n.fecha_publicacion as fecha,
                       c.imagen_url, c.resumen, c.resumen_ia
                {base_from}
                ORDER BY n.id DESC
                LIMIT %s
            """, (categoria.strip(), limite + 1))
        elif categoria_id:
            cur.execute(f"""
                SELECT n.id, n.titulo, n.fuente, n.link as link_original,
                       n.fecha_publicacion as fecha,
                       c.imagen_url, c.resumen, c.resumen_ia
                {base_from}
                ORDER BY n.id DESC
                LIMIT %s
            """, (categoria_id, limite + 1))
        else:
            cur.execute(f"""
                SELECT n.id, n.titulo, n.fuente, n.link as link_original,
                       n.fecha_publicacion as fecha,
                       c.imagen_url, c.resumen, c.resumen_ia
                {base_from}
                ORDER BY n.id DESC
                LIMIT %s
            """, (limite + 1,))

    filas = cur.fetchall()

    # si trajo limite+1 significa que hay mas noticias disponibles
    hay_mas = len(filas) > limite
    if hay_mas:
        filas = filas[:limite]

    # para cada noticia busca sus categorias en la tabla noticias_categorias
    noticias = []
    for fila in filas:
        cur.execute("""
            SELECT c.nombre FROM categorias c
            JOIN noticias_categorias nc ON nc.categoria_id = c.id
            WHERE nc.noticia_id = %s
        """, (fila["id"],))
        categorias = [r["nombre"] for r in cur.fetchall()]

        noticias.append(Noticia(
            id=fila["id"],
            titulo=fila["titulo"],
            fuente=fila["fuente"],
            link_original=fila["link_original"],
            fecha=fila["fecha"],
            imagen_url=f"/imagenes/{fila['imagen_url']}" if fila["imagen_url"] else None,
            resumen=fila["resumen"],
            resumen_ia=fila["resumen_ia"],
            categorias=categorias
        ))

    # el cursor para la siguiente pagina es el id de la ultima noticia devuelta
    siguiente_cursor = filas[-1]["id"] if hay_mas and filas else None

    cur.close()
    conn.close()

    return RespuestaNoticias(
        noticias=noticias,
        siguiente_cursor=siguiente_cursor,
        hay_mas=hay_mas
    )


@app.get("/noticias/{noticia_id}", response_model=Noticia)
def obtener_noticia(
    noticia_id: int,
    _: str = Depends(verificar_api_key)
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT n.id, n.titulo, n.fuente, n.link as link_original,
               n.fecha_publicacion as fecha,
               c.imagen_url, c.resumen, c.resumen_ia
        FROM noticias n
        JOIN contenido c ON c.noticia_id = n.id
        WHERE n.id = %s
        AND n.estado = 'completo'
    """, (noticia_id,))

    fila = cur.fetchone()
    if not fila:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")

    cur.execute("""
        SELECT c.nombre FROM categorias c
        JOIN noticias_categorias nc ON nc.categoria_id = c.id
        WHERE nc.noticia_id = %s
    """, (noticia_id,))
    categorias = [r["nombre"] for r in cur.fetchall()]

    cur.close()
    conn.close()

    return Noticia(
        id=fila["id"],
        titulo=fila["titulo"],
        fuente=fila["fuente"],
        link_original=fila["link_original"],
        fecha=fila["fecha"],
        imagen_url=f"/imagenes/{fila['imagen_url']}" if fila["imagen_url"] else None,
        resumen=fila["resumen"],
        resumen_ia=fila["resumen_ia"],
        categorias=categorias
    )


@app.get("/admin/noticias-pendientes")
def noticias_pendientes(_: str = Depends(verificar_api_key)):
    import logging
    logger = logging.getLogger()
    try:
        conn = get_connection()
        cur = conn.cursor()

        logger.error("DEBUG: Antes de execute")
        cur.execute("""
            SELECT id, titulo, link, fuente
            FROM noticias
            WHERE estado = 'pendiente'
            ORDER BY id ASC
            LIMIT 50
        """)
        logger.error("DEBUG: Despues de execute")

        filas = cur.fetchall()
        logger.error(f"DEBUG: filas = {filas}, len = {len(filas)}")
        
        cur.close()
        conn.close()

        result = [{"id": f["id"], "titulo": f["titulo"], "link": f["link"], "fuente": f["fuente"]} for f in filas]
        logger.error(f"DEBUG: result = {result}")
        return result
    except Exception as e:
        logger.error(f"DEBUG: exception = {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/noticias/{noticia_id}/accion")
def noticia_accion(
    noticia_id: int,
    accion: str = Query(...),
    _: str = Depends(verificar_api_key)
):
    if accion not in ("aprobar", "rechazar"):
        raise HTTPException(status_code=400, detail="Accion invalida")

    nuevo_estado = "aprobado" if accion == "aprobar" else "rechazado"

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE noticias SET estado = %s WHERE id = %s", (nuevo_estado, noticia_id))
    conn.commit()
    cur.close()
    conn.close()

    return {"ok": True, "estado": nuevo_estado}