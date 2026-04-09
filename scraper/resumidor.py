import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import requests
import time
from db import get_connection
from config import HEADERS

# modelos en orden de prioridad
# modelo primario gratis
MODELO_PRINCIPAL = "qwen/qwen3.6-plus:free"

# modelo secundario Pago y barato, para no parar la pagina
MODELO_RESPALDO  = "deepseek/deepseek-v3.2"

# tu api key de openrouter
from config import HEADERS, OPENROUTER_API_KEY

# pausa entre cada llamada a la IA para no superar límites
PAUSA_SEGUNDOS = 5

# máximo de reintentos por noticia
MAX_REINTENTOS = 3


def obtener_noticias_pendientes():
    # busca noticias que tienen contenido pero sin resumen IA todavía
    # usamos un campo nuevo: resumen_ia en la tabla contenido
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT n.id, n.titulo, c.id as contenido_id, c.texto_completo
        FROM noticias n
        JOIN contenido c ON c.noticia_id = n.id
        WHERE n.estado = 'completo'
        AND (c.resumen_ia IS NULL OR c.resumen_ia = '')
        AND c.texto_completo IS NOT NULL
        AND c.texto_completo != ''
        LIMIT 10
    """)
    filas = cur.fetchall()
    cur.close()
    conn.close()
    return filas


def llamar_openrouter(titulo, texto, modelo):
    # limita el texto a 2000 caracteres para no gastar tokens de más
    texto_corto = texto[:2000] if len(texto) > 2000 else texto

    prompt = f"""Sos redactor de un portal de noticias de Santiago del Estero.
Escribí UN párrafo de 3 oraciones resumiendo esta noticia.

Reglas estrictas:
- Usá oraciones cortas y directas
- No uses frases como: "en el marco de", "cabe destacar", "es importante mencionar", "en este sentido", "a raíz de"
- No empieces con el nombre del medio ni con "La noticia"
- No uses signos de exclamación
- Escribí como si lo contaras a un conocido, no como un comunicado oficial
- Solo el párrafo, sin títulos ni explicaciones extra

Título: {titulo}
Noticia: {texto_corto}"""

    respuesta = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": modelo,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
        },
        timeout=30
    )

    if respuesta.status_code == 200:
        data = respuesta.json()
        texto_resumen = data["choices"][0]["message"]["content"].strip()
        return texto_resumen
    elif respuesta.status_code == 429:
        # limite de peticiones alcanzado
        raise Exception("LIMITE_ALCANZADO")
    else:
        raise Exception(f"Error HTTP {respuesta.status_code}: {respuesta.text[:200]}")


def guardar_resumen(contenido_id, resumen):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE contenido SET resumen_ia = %s WHERE id = %s
        """, (resumen, contenido_id))
        conn.commit()
    except Exception as e:
        print(f"  error guardando resumen: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def correr():
    if not OPENROUTER_API_KEY:
        print("ERROR: falta la variable OPENROUTER_API_KEY")
        return

    print("Iniciando generacion de resumenes con IA...")
    noticias = obtener_noticias_pendientes()
    print(f"Noticias para resumir: {len(noticias)}")

    if len(noticias) == 0:
        print("No hay noticias pendientes de resumen.")
        return

    for noticia_id, titulo, contenido_id, texto in noticias:
        print(f"\nResumiendo: {titulo[:60]}")

        resumen = None
        intentos = 0

        while resumen is None and intentos < MAX_REINTENTOS:
            intentos += 1
            # intento 1 → principal, intento 2 y 3 → respaldo
            modelo = MODELO_PRINCIPAL if intentos == 1 else MODELO_RESPALDO

            try:
                print(f"  intento {intentos} con {modelo}...")
                resumen = llamar_openrouter(titulo, texto, modelo)
                print(f"  OK: {resumen[:80]}...")

            except Exception as e:
               if "LIMITE_ALCANZADO" in str(e):
                    if modelo == MODELO_PRINCIPAL:
                        # limite del gratuito, intenta con el pago
                        print("  Límite del modelo gratuito, cambiando al modelo de respaldo...")
                        continue
                    else:
                        # limite del pago también, parar todo
                        print("  Límite alcanzado en ambos modelos. Parando.")
                        return
            print(f"  error: {e}")
            if intentos < MAX_REINTENTOS:
                print(f"  esperando 10 segundos antes de reintentar...")
                time.sleep(10)

        if resumen:
            guardar_resumen(contenido_id, resumen)
        else:
            print(f"  no se pudo generar resumen después de {MAX_REINTENTOS} intentos")

        print(f"  esperando {PAUSA_SEGUNDOS} segundos...")
        time.sleep(PAUSA_SEGUNDOS)

    print("\nGeneracion de resumenes finalizada.")


correr()