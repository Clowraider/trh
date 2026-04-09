import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_CONFIG


def get_connection():
    # RealDictCursor hace que los resultados vengan como diccionarios
    # en lugar de tuplas, mas facil de convertir a JSON
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)