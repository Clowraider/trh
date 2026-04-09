import os
from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = ["DB_PASSWORD", "OPENROUTER_API_KEY"]
for var in REQUIRED_VARS:
    if not os.getenv(var):
        raise ValueError(f"La variable de entorno {var} no está definida")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "192.168.0.53"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "trh_noticias"),
    "user": os.getenv("DB_USER", "trh_user"),
    "password": os.getenv("DB_PASSWORD")
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
CARPETA_IMAGENES = os.getenv("CARPETA_IMAGENES", "C:/proyectos/trh/imagenes")