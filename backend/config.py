import os
from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = ["API_KEY", "DB_PASSWORD"]
for var in REQUIRED_VARS:
    if not os.getenv(var):
        raise ValueError(f"La variable de entorno {var} no está definida")

API_KEY = os.getenv("API_KEY")
DB_HOST = os.getenv("DB_HOST", "192.168.0.53")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "trh_noticias")
DB_USER = os.getenv("DB_USER", "trh_user")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DB_CONFIG = {
    "host": DB_HOST,
    "port": DB_PORT,
    "database": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD
}

CORS_ORIGINS = [
    "http://localhost:3000",
    "https://trh.com.ar",
]

CARPETA_IMAGENES = os.getenv("CARPETA_IMAGENES", "/root/docker/trh/imagenes")