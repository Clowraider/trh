"""
Funciones helper para SEO y generación de meta tags.
Contiene utilidades para formatear URLs, generar meta tags y schema.org.
"""
import json
import re
from typing import Optional


def formatear_slug(titulo: str) -> str:
    """
    Convierte un título en un slug URL limpio y amigable para SEO.
    
    Proceso:
    1. Convierte a minúsculas
    2. Reemplaza espacios con guiones
    3. Elimina caracteres no alfanuméricos (excepto guiones)
    4. Elimina acentos y caracteres especiales del español
    
    Ejemplo: "Niña de 3 años atropellada" -> "nina-de-3-anos-atropellada"
    
    Args:
        titulo: El título de la noticia a convertir
        
    Returns:
        Slug formateado para URL
    """
    if not titulo:
        return ""
    
    # Convertir a minúsculas
    slug = titulo.lower()
    
    # Reemplazar espacios con guiones
    slug = slug.replace(" ", "-")
    
    # Eliminar caracteres especiales (dejar solo letras, números y guiones)
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    
    # Eliminar acentos del español
    slug = slug.replace("á", "a")
    slug = slug.replace("é", "e")
    slug = slug.replace("í", "i")
    slug = slug.replace("ó", "o")
    slug = slug.replace("ú", "u")
    slug = slug.replace("ñ", "n")
    
    # Eliminar guiones重复idos
    while "--" in slug:
        slug = slug.replace("--", "-")
    
    # Eliminar guiones al inicio y final
    slug = slug.strip("-")
    
    return slug


def generar_meta_tags_home(dominio: str) -> dict:
    """
    Genera los meta tags para la página de inicio (homepage).
    
    Args:
        dominio: El dominio del sitio (ej: trh.com.ar)
        
    Returns:
        Diccionario con todos los meta tags y placeholders para base.html
    """
    url_base = f"https://{dominio}"
    
    return {
        # Título de la página
        "PAGE_TITLE": "TRH Noticias - Santiago del Estero",
        
        # Meta description (150-160 caracteres optimal)
        "META_DESCRIPTION": "TRH Noticias de Santiago del Estero. Últimas noticias locales, Río Hondo, diario panorama, vision santiagueña y más.",
        
        # Canonical URL
        "CANONICAL_URL": url_base,
        
        # Open Graph
        "OG_TITLE": "TRH Noticias - Santiago del Estero",
        "OG_DESCRIPTION": "Últimas noticias de Santiago del Estero, Argentina. Stay informed with local news.",
        "OG_IMAGE": f"{url_base}/static/images/og-default.jpg",
        "OG_URL": url_base,
        "OG_TYPE": "website",
        
        # Twitter Card
        "TWITTER_TITLE": "TRH Noticias - Santiago del Estero",
        "TWITTER_DESCRIPTION": "Últimas noticias de Santiago del Estero, Argentina.",
        "TWITTER_IMAGE": f"{url_base}/static/images/og-default.jpg",
        
        # Schema.org para homepage (Organization)
        "SCHEMA_JSON": json.dumps({
            "@context": "https://schema.org",
            "@type": "NewsMediaOrganization",
            "name": "TRH Noticias",
            "url": url_base,
            "description": "Portal de noticias de Santiago del Estero, Argentina",
            "areaServed": {
                "@type": "State",
                "name": "Santiago del Estero"
            },
            "sameAs": []
        }, ensure_ascii=False)
    }


def generar_meta_tags_noticia(noticia: dict, dominio: str, imagen_base_url: str) -> dict:
    """
    Genera los meta tags para una página individual de noticia.
    Incluye Open Graph, Twitter Card y Schema.org NewsArticle.
    
    Args:
        noticia: Diccionario con los datos de la noticia (del backend)
        dominio: El dominio del sitio (ej: trh.com.ar)
        imagen_base_url: URL base para las imágenes (ej: http://192.168.0.53:8001)
        
    Returns:
        Diccionario con todos los meta tags y placeholders para base.html
    """
    titulo = noticia.get("titulo", "")
    resumen = noticia.get("resumen", "")
    resumen_ia = noticia.get("resumen_ia", "")
    categorias = noticia.get("categorias", [])
    fuente = noticia.get("fuente", "")
    fecha = noticia.get("fecha", "")
    imagen_url = noticia.get("imagen_url", "")
    id_noticia = noticia.get("id", "")
    
    # Generar slug para la URL
    slug = formatear_slug(titulo)
    url_noticia = f"https://{dominio}/noticia/{id_noticia}-{slug}"
    
    # Procesar imagen
    og_image = ""
    if imagen_url:
        if imagen_url.startswith("/imagenes/"):
            img_path = imagen_url.replace("/imagenes/", "")
        else:
            img_path = imagen_url
        og_image = f"{imagen_base_url}/{img_path}"
    
    # Unir categorías como keywords
    keywords = ", ".join(categorias) if categorias else ""
    
    # Combinar resumen y resumen_ia para articleBody
    article_body = ""
    if resumen_ia:
        article_body = resumen_ia
    elif resumen:
        article_body = resumen
    
    # Limitar descripción para meta tags (150-160 caracteres optimal)
    meta_desc = resumen_ia[:157] + "..." if len(resumen_ia) > 157 else resumen_ia
    if not meta_desc:
        meta_desc = resumen[:157] + "..." if len(resumen) > 157 else resumen
    if not meta_desc:
        meta_desc = f"Noticia de {fuente}"
    
    # Limitar og:description (200 caracteres máximo)
    og_desc = resumen_ia[:197] + "..." if len(resumen_ia) > 197 else resumen_ia
    if not og_desc:
        og_desc = resumen[:197] + "..." if len(resumen) > 197 else resumen
    if not og_desc:
        og_desc = f"Leer más en TRH Noticias - {titulo}"
    
    # Formatear fecha para Schema (ISO 8601)
    fecha_iso = ""
    if fecha:
        if isinstance(fecha, str):
            fecha_iso = fecha.replace(" ", "T")
    
    # Construir Schema.org NewsArticle
    schema_data = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": titulo,
        "articleBody": article_body,
        "image": og_image if og_image else None,
        "datePublished": fecha_iso,
        "sourceOrganization": {
            "@type": "NewsMediaOrganization",
            "name": fuente
        }
    }
    
    if keywords:
        schema_data["keywords"] = keywords
    
    return {
        # Título de la página
        "PAGE_TITLE": f"{titulo} - TRH Noticias",
        
        # Meta description
        "META_DESCRIPTION": meta_desc,
        
        # Canonical URL
        "CANONICAL_URL": url_noticia,
        
        # Open Graph
        "OG_TITLE": titulo,
        "OG_DESCRIPTION": og_desc,
        "OG_IMAGE": og_image if og_image else f"https://{dominio}/static/images/og-default.jpg",
        "OG_URL": url_noticia,
        "OG_TYPE": "article",
        
        # Twitter Card
        "TWITTER_TITLE": titulo,
        "TWITTER_DESCRIPTION": og_desc,
        "TWITTER_IMAGE": og_image if og_image else f"https://{dominio}/static/images/og-default.jpg",
        
        # Schema.org NewsArticle
        "SCHEMA_JSON": json.dumps(schema_data, ensure_ascii=False)
    }


def inyectar_meta_tags(html: str, meta_tags: dict) -> str:
    """
    Inyecta los meta tags en la plantilla base.html.
    
    Args:
        html: Contenido HTML de la página
        meta_tags: Diccionario con los valores de los meta tags
        
    Returns:
        HTML con los meta tags reemplazados
    """
    for key, value in meta_tags.items():
        placeholder = f"{{{{ {key} }}}}"
        html = html.replace(placeholder, str(value))
    
    return html