import os
import importlib
import psycopg2
from psycopg2.extras import RealDictCursor

from datetime import datetime, timedelta

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

DIAS_ANALISIS = 7

TOP_KEYWORDS = 5

LONGITUD_MAX_TEXTO = 12000

# =================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# =================================================
# CARGAR SPACY
# =================================================

logger.info("🧠 Cargando modelo spaCy...")

spacy = importlib.import_module("spacy")
nlp = spacy.load("es_core_news_md")

logger.info("✅ spaCy cargado")

# =================================================
# YAKE
# =================================================

yake = importlib.import_module("yake")

kw_extractor = yake.KeywordExtractor(
    lan="es",
    n=2,
    dedupLim=0.85,
    top=TOP_KEYWORDS
)

# =================================================


def validar_configuracion() -> None:
    if not DB_CONFIG.get("password"):
        raise RuntimeError("Falta variable de entorno requerida: DB_PASSWORD")


def get_connection():
    validar_configuracion()
    return psycopg2.connect(
        **DB_CONFIG,
        cursor_factory=RealDictCursor
    )


# =================================================
# OBTENER NOTICIAS
# =================================================

def limpiar_keywords_antiguas(conn):
    """
    Elimina keywords de noticias fuera de ventana de análisis para evitar crecimiento infinito.
    """
    cur = conn.cursor()
    cur.execute(f"""
        DELETE FROM noticias_keywords nk
        USING noticias_historico nh
        WHERE nk.noticia_id = nh.id
          AND (
              nh.fecha_publicacion IS NULL
              OR nh.fecha_publicacion < CURRENT_DATE - INTERVAL '{DIAS_ANALISIS} days'
          )
    """)
    eliminadas = cur.rowcount
    conn.commit()
    cur.close()

    if eliminadas > 0:
        logger.info(f"🧹 Keywords antiguas eliminadas: {eliminadas}")


def obtener_noticias(conn):

    cur = conn.cursor()

    cur.execute(f"""
        SELECT
            id,
            titulo,
            texto_completo,
            fecha_extraccion,
            analizado_en
        FROM noticias_historico

        WHERE fecha_publicacion IS NOT NULL
          AND fecha_publicacion >= CURRENT_DATE - INTERVAL '{DIAS_ANALISIS} days'
          AND (
              analizado_en IS NULL
              OR analizado_en < fecha_extraccion
              OR NOT EXISTS (
                  SELECT 1
                  FROM noticias_keywords nk
                  WHERE nk.noticia_id = noticias_historico.id
              )
          )

        ORDER BY fecha_publicacion DESC, id DESC
    """)

    noticias = cur.fetchall()

    cur.close()

    return noticias


# =================================================
# LIMPIAR EXISTENTES
# =================================================

def limpiar_keywords_noticia(conn, noticia_id):

    cur = conn.cursor()

    cur.execute("""
        DELETE FROM noticias_keywords
        WHERE noticia_id = %s
    """, (noticia_id,))

    cur.close()


# =================================================
# GUARDAR KEYWORD
# =================================================

def guardar_keyword(
    conn,
    noticia_id,
    tipo,
    valor,
    score=None
):

    if not valor:
        return

    valor = valor.strip()

    valor_normalizado = valor.lower().strip()

    # =================================================
    # FILTROS
    # =================================================

    if len(valor) < 3:
        return

    # evitar palabras sueltas cortas
    if len(valor.split()) == 1 and len(valor) < 5:
        return

    # evitar basura típica
    basura = [
        'habló',
        'dijo',
        'señaló',
        'comentó',
        'explicó',
        'unirte al canal de whatsapp de diario',
        'estar siempre informado',
        'diario panorama'
    ]

    if any(
        b in valor_normalizado
        for b in basura
    ):
        return

    cur = conn.cursor()

    cur.execute("""
        INSERT INTO noticias_keywords
        (
            noticia_id,
            tipo,
            valor,
            valor_normalizado,
            score
        )
        VALUES (%s, %s, %s, %s, %s)

        ON CONFLICT DO NOTHING
    """, (
        noticia_id,
        tipo,
        valor,
        valor_normalizado,
        score
    ))

    cur.close()


# =================================================
# EXTRAER KEYWORDS YAKE
# =================================================

def extraer_keywords(texto):

    resultados = kw_extractor.extract_keywords(texto)

    keywords = []

    for keyword, score in resultados:

        if len(keyword) < 4:
            continue

        # evitar una sola palabra rara
        if len(keyword.split()) == 1 and len(keyword) < 6:
            continue

        keywords.append({
            'valor': keyword,
            'score': float(score)
        })

    return keywords


# =================================================
# EXTRAER ENTIDADES
# =================================================

def extraer_entidades(texto):

    doc = nlp(texto)

    entidades = []

    entidades_vistas = set()

    mapa_tipos = {
        'PER': 'persona',
        'ORG': 'organizacion',
        'LOC': 'lugar'
    }

    contador_tipos = {
        'persona': 0,
        'organizacion': 0,
        'lugar': 0
    }

    LIMITES = {
        'persona': 5,
        'organizacion': 3,
        'lugar': 3
    }

    for ent in doc.ents:

        # =================================================
        # IGNORAR MISC
        # =================================================

        if ent.label_ == "MISC":
            continue

        valor = ent.text.strip()

        valor_normalizado = valor.lower().strip()

        # =================================================
        # FILTROS BASURA NER
        # =================================================

        basura_ner = [

            # banners / promos
            'diario panorama',
            'grupo panorama',
            'whatsapp',
            'facebook',
            'instagram',
            'twitter',
            'youtube',

            # basura típica medios
            'último momento',
            'últimas noticias',
            'más información',

            # navegación
            'inicio',
            'policiales',
            'deportes',

            # spam recurrente
            'UNIRTE AL CANAL DE WHATSAPP DE DIARIO',
            'ESTAR SIEMPRE'
        ]

        # =================================================
        # FILTRO TEXTO BASURA
        # =================================================

        if any(
            basura in valor_normalizado
            for basura in basura_ner
        ):
            continue

        # =================================================
        # FILTRO LONGITUD EXCESIVA
        # =================================================

        if len(valor) > 60:
            continue

        # =================================================
        # EVITAR ENTIDADES CON MUCHOS NÚMEROS
        # =================================================

        numeros = sum(c.isdigit() for c in valor)

        if numeros >= 4:
            continue

        # =================================================
        # EVITAR SOLO MAYÚSCULAS
        # =================================================

        if valor.isupper() and len(valor) > 12:
            continue

        # =================================================
        # EVITAR FRASES DEMASIADO LARGAS
        # =================================================

        if len(valor.split()) > 6:
            continue

        # =================================================
        # FILTROS EXISTENTES
        # =================================================

        if len(valor) < 3:
            continue

        clave = (
            valor_normalizado,
            ent.label_
        )

        if clave in entidades_vistas:
            continue

        entidades_vistas.add(clave)

        tipo = mapa_tipos.get(
            ent.label_,
            None
        )

        if not tipo:
            continue

        # =================================================
        # LIMITAR CANTIDAD
        # =================================================

        if contador_tipos[tipo] >= LIMITES[tipo]:
            continue

        contador_tipos[tipo] += 1

        entidades.append({
            'tipo': tipo,
            'valor': valor
        })

    return entidades


# =================================================
# PROCESAR NOTICIA
# =================================================

def marcar_noticia_analizada(conn, noticia_id):
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE noticias_historico
        SET analizado_en = NOW()
        WHERE id = %s
        """,
        (noticia_id,),
    )
    cur.close()


def procesar_noticia(conn, noticia):

    noticia_id = noticia['id']

    titulo = noticia['titulo'] or ""

    texto = noticia['texto_completo'] or ""

    texto_total = f"{titulo}\n\n{texto}"

    texto_total = texto_total[:LONGITUD_MAX_TEXTO]

    logger.info(
        f"📰 Procesando noticia #{noticia_id}"
    )

    # =================================================
    # LIMPIAR EXISTENTES
    # =================================================

    limpiar_keywords_noticia(
        conn,
        noticia_id
    )

    # =================================================
    # YAKE
    # =================================================

    keywords = extraer_keywords(
        texto_total
    )

    for kw in keywords:

        guardar_keyword(
            conn,
            noticia_id,
            'keyword',
            kw['valor'],
            kw['score']
        )

    logger.info(
        f"🔑 Keywords extraídas: {len(keywords)}"
    )

    # =================================================
    # NER
    # =================================================

    entidades = extraer_entidades(
        texto_total
    )

    for ent in entidades:

        guardar_keyword(
            conn,
            noticia_id,
            ent['tipo'],
            ent['valor']
        )

    logger.info(
        f"🧠 Entidades extraídas: {len(entidades)}"
    )

    marcar_noticia_analizada(conn, noticia_id)
    conn.commit()


# =================================================
# MAIN
# =================================================

def main():

    logger.info(
        "🚀 Iniciando extracción "
        "YAKE + NER"
    )

    conn = get_connection()

    try:

        limpiar_keywords_antiguas(conn)

        noticias = obtener_noticias(conn)

        logger.info(
            f"📦 Noticias encontradas: "
            f"{len(noticias)}"
        )

        for noticia in noticias:

            try:

                procesar_noticia(
                    conn,
                    noticia
                )

            except Exception as e:

                conn.rollback()

                logger.exception(
                    f"❌ Error procesando "
                    f"noticia {noticia['id']}: {e}"
                )

    finally:

        conn.close()

    logger.info(
        "🎉 Proceso finalizado"
    )


# =================================================

if __name__ == "__main__":
    main()