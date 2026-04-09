import psycopg2
from config import DB_CONFIG

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS noticias (
            id               SERIAL PRIMARY KEY,
            titulo           TEXT NOT NULL,
            link             TEXT UNIQUE NOT NULL,
            fuente           TEXT NOT NULL,
            estado           TEXT NOT NULL DEFAULT 'pendiente',
            fecha_publicacion TIMESTAMP,
            creado_en        TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id     SERIAL PRIMARY KEY,
            nombre TEXT UNIQUE NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS noticias_categorias (
            noticia_id  INTEGER REFERENCES noticias(id),
            categoria_id INTEGER REFERENCES categorias(id),
            PRIMARY KEY (noticia_id, categoria_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS contenido (
            id             SERIAL PRIMARY KEY,
            noticia_id     INTEGER UNIQUE REFERENCES noticias(id),
            resumen        TEXT,
            texto_completo TEXT,
            autor          TEXT,
            imagen_url     TEXT,
            resumen_ia     TEXT
        )
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Base de datos lista.")

if __name__ == "__main__":
    init_db()