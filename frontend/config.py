import os
from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = ["API_KEY", "ADMIN_PASSWORD", "SECRET_KEY"]
for var in REQUIRED_VARS:
    if not os.getenv(var):
        raise ValueError(f"La variable de entorno {var} no está definida")

API_KEY = os.getenv("API_KEY")
API_BASE_URL = os.getenv("API_BASE_URL", "http://192.168.0.53:8001")
IMAGEN_BASE_URL = os.getenv("IMAGEN_BASE_URL", f"{API_BASE_URL}/imagenes")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_COOKIE_NAME = "trh_admin_session"
ADMIN_COOKIE_DURATION_HOURS = 24
SECRET_KEY = os.getenv("SECRET_KEY")

ADMIN_MAX_ATTEMPTS = int(os.getenv("ADMIN_MAX_ATTEMPTS", "3"))
ADMIN_LOCKOUT_MINUTES = int(os.getenv("ADMIN_LOCKOUT_MINUTES", "15"))
ADMIN_LOG_FILE = os.getenv("ADMIN_LOG_FILE", "/app/logs/login_fallidos.log")