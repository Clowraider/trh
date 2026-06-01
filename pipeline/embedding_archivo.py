import os
import time

import psycopg2
import requests


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

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.getenv("EMBEDDING_MODEL", "qwen3-embedding:4b")
DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))
BATCH_LIMIT = int(os.getenv("EMBEDDING_BATCH_LIMIT", "1000"))
COMMIT_EVERY = int(os.getenv("EMBEDDING_COMMIT_EVERY", "100"))
EMBEDDING_RETRIES = int(os.getenv("EMBEDDING_RETRIES", "3"))
RETRY_BACKOFF_SECONDS = float(os.getenv("EMBEDDING_RETRY_BACKOFF_SECONDS", "1.5"))

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "trh")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")


def validar_configuracion() -> None:
    faltantes = []
    if not DB_PASSWORD:
        faltantes.append("DB_PASSWORD")

    if faltantes:
        raise RuntimeError(
            "Faltan variables de entorno requeridas: " + ", ".join(faltantes)
        )


def get_embedding(text: str):
    for intento in range(1, EMBEDDING_RETRIES + 1):
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/embed",
                json={"model": MODEL, "input": text},
                timeout=60,
            )
            response.raise_for_status()
            embedding = response.json()["embeddings"][0]

            if len(embedding) < DIMENSION:
                print(
                    f"❌ Embedding inválido: esperado >= {DIMENSION}, recibido {len(embedding)}"
                )
                return None

            return embedding[:DIMENSION]
        except Exception as e:
            if intento < EMBEDDING_RETRIES:
                espera = RETRY_BACKOFF_SECONDS * intento
                print(
                    f"⚠️  Error al generar embedding (intento {intento}/{EMBEDDING_RETRIES}): {e}. Reintento en {espera:.1f}s..."
                )
                time.sleep(espera)
            else:
                print(
                    f"❌ Error al generar embedding tras {EMBEDDING_RETRIES} intentos: {e}"
                )
                return None


def crear_texto_para_embedding(noticia):
    """Embedding usando solo título + texto completo"""
    partes = []

    if noticia.get("titulo"):
        partes.append(noticia["titulo"].strip())

    if noticia.get("texto_completo"):
        partes.append(noticia["texto_completo"][:450])

    return ". ".join([p for p in partes if p])


def main():
    validar_configuracion()

    with psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    ) as conn:
        with conn.cursor() as cur:
            print("🚀 Iniciando generación de embeddings...")

            cur.execute(
                """
                SELECT id, titulo, texto_completo
                FROM noticias_historico
                WHERE embedding IS NULL
                ORDER BY fecha_extraccion DESC
                LIMIT %s;
                """,
                (BATCH_LIMIT,),
            )

            noticias = cur.fetchall()
            procesadas = 0
            pendientes_commit = 0

            for noticia_id, titulo, texto_completo in noticias:
                texto = crear_texto_para_embedding(
                    {"titulo": titulo, "texto_completo": texto_completo}
                )

                if not texto or len(texto) < 15:
                    print(f"⚠️  Noticia {noticia_id} sin texto suficiente")
                    continue

                embedding = get_embedding(texto)

                if embedding:
                    cur.execute(
                        """
                        UPDATE noticias_historico
                        SET embedding = %s,
                            procesado = FALSE,
                            cluster_asignado_en = NULL
                        WHERE id = %s
                        """,
                        (embedding, noticia_id),
                    )
                    procesadas += 1
                    pendientes_commit += 1
                    print(
                        f"✅ Noticia {noticia_id} → Embedding generado ({len(embedding)} dims)"
                    )

                    if pendientes_commit >= COMMIT_EVERY:
                        conn.commit()
                        print(f"💾 Commit parcial aplicado ({procesadas} procesadas)")
                        pendientes_commit = 0

            if pendientes_commit > 0:
                conn.commit()
                print(f"💾 Commit final aplicado ({procesadas} procesadas)")

            print(f"\n🎉 Finalizado. Se procesaron {procesadas} noticias.")


if __name__ == "__main__":
    main()
