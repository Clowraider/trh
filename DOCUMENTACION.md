# Documentación del Sistema TRH2

## Descripción General
TRH2 es un sistema de recolección, procesamiento y selección de noticias editoriales proveniente de múltiples fuentes (como Nuevo Diario Web y Sursantiago). El sistema extrae artículos, los almacena en una base de datos PostgreSQL, calcula un score editorial basado en múltiples factores (cantidad de noticias, fuentes, tendencia, actividad reciente, prioridades editoriales, etc.) y muestra los mejores candidatos en un dashboard web.

## Arquitectura
- **Frontend**: Dashboard Flask que sirve una plantilla HTML (`templates/dashboard.html`) mostrando los candidatos.
- **Backend**: 
  - `app.py`: Punto de entrada Flask. Obtiene conexión a la base de datos, llama a `generar_candidatos` y renderiza el dashboard.
  - `seleccionar_publicables.py`: Contiene toda la lógica de negocio: obtención de clusters activos, cálculo de scores, obtención de noticias y keywords, etc.
  - `crawler/nuevodiario_crawler.py` y `crawler/sursantiago_crawler.py`: Módulos de scraping que extraen URLs y artículos de los sitios de noticias, guardándolos en la base de datos.
- **Base de datos**: PostgreSQL con las siguientes tablas principales:
  - `clusters_editoriales`: Agrupa noticias por tema/evento. Campos: id, titulo_representativo, cantidad_noticias, cantidad_fuentes, score, tendencia, primera_noticia, ultima_noticia, estado, veces_publicado, ultima_publicacion.
  - `noticias_historico`: Almacena cada artículo extraído. Campos: id, noticia_hash, hash_contenido, fuente, url_original, titulo, texto_completo, url_imagen, fecha_publicacion.
  - `noticias_keywords`: Relación many-to-many entre noticias y keywords (tipo y valor_normalizado).
  - `keywords_prioridad`: Lista de keywords con peso (puntos) y estado activo.
  - `urls`: Cola de URLs a procesar por los crawlers.

## Flujo del Programa
1. **Inicio** (`app.py`):
   - Se lanza el servidor Flask en `0.0.0.0:5000`.
   - Al acceder a la ruta `/`, se llama a `dashboard()`.
2. **Obtención de candidatos**:
   - `dashboard()` llama a `get_connection()` (de `seleccionar_publicables.py`) para obtener conexión a PostgreSQL.
   - Luego llama a `generar_candidatos(conn)`.
3. **Dentro de `generar_candidatos`**:
   - Llama a `obtener_clusters_activos(conn)`: selecciona clusters cuya `ultima_noticia` sea dentro de las últimas `HORAS_RECIENCIA` (48h) ordenados por `ultima_noticia` DESC.
   - Para cada cluster:
     - Calcula el score editorial mediante `calcular_score_editorial(conn, cluster)`.
     - Obtiene las noticias del cluster (`obtener_noticias_cluster`).
     - Obtiene los keywords del cluster (`obtener_keywords_cluster`).
     - Guarda todo en un dict del cluster y lo agrega a la lista de candidatos.
   - Ordena la lista por `score_editorial` descendente y devuelve los top `MAX_CANDIDATOS` (10).
4. **Cálculo del score editorial** (`calcular_score_editorial`):
   - Puntaje base:
     - +2 por cada noticia (`cantidad_noticias * 2`)
     - +8 por cada fuente (`cantidad_fuentes * 8`)
     - +4 por tendencia (`tendencia * 4`)
   - Actividad reciente:
     - +10 por cada noticia en las últimas 2h
     - +5 por cada noticia en las últimas 6h
     - +2 por cada noticia en las últimas 24h
   - Bonuses:
     - +50 si hay >=5 noticias en 2h (crecimiento explosivo)
     - +40 si hay >=5 fuentes (múltiples medios)
   - Prioridades editoriales:
     - Se obtienen los keywords del cluster y se comparan con `keywords_prioridad` (activos), sumando sus puntos.
   - Penalizaciones:
     - -20 si solo hay 1 fuente (fuente única)
     - -40 si el cluster fue publicado recientemente (< `HORAS_PENALIZACION_PUBLICADO` = 6h)
     - -60 si la última noticia es mayor a 24h (cluster viejo)
   - Bonuses:
     - +25 si la primera noticia es menor a 6h (historia nueva)
   - El score final se redondea a 2 decimales y se devuelve junto con las razones (lista de strings explicativas).
5. **Renderizado**:
   - `app.py` pasa la lista de candidatos a la plantilla `dashboard.html` para su visualización.

## Detalles de la Base de Data
### Tablas

#### clusters_editoriales
- `id` (bigint, PK)
- `titulo_representativo` (text)
- `embedding_centroide` (vector(768))
- `cantidad_noticias` (integer, default 0)
- `cantidad_fuentes` (integer, default 0)
- `primera_noticia` (timestamp without time zone)
- `ultima_noticia` (timestamp without time zone)
- `score` (double precision, default 0)
- `tendencia` (double precision, default 0)
- `estado` (character varying(30), default 'nuevo')
- `veces_publicado` (integer, default 0)
- `ultima_publicacion` (timestamp without time zone)
- `creado_en` (timestamp without time zone, default now())
- `actualizado_en` (timestamp without time zone, default now())

#### noticias_historico
- `id` (integer, PK, default from sequence)
- `noticia_hash` (character varying(64), not null)
- `hash_contenido` (character varying(64))
- `fuente` (character varying(100), not null)
- `url_original` (text, not null)
- `titulo` (text, not null)
- `texto_completo` (text)
- `url_imagen` (text)
- `fecha_publicacion` (timestamp without time zone)
- `fecha_extraccion` (timestamp without time zone, default CURRENT_TIMESTAMP)
- `embedding` (vector(768))
- `cluster_asignado_en` (timestamp without time zone)
- `procesado` (boolean, default false)
- `metadata` (jsonb)
- `creado_en` (timestamp without time zone, default CURRENT_TIMESTAMP)
- `publicado_en_cluster` (boolean, default false)
- `score_individual` (double precision, default 0)
- `relevancia_local` (double precision, default 0)
- `duplicado` (boolean, default false)
- `analizado_en` (timestamp without time zone)
- `cluster_id` (bigint)

#### noticias_keywords
- `id` (bigint, PK)
- `noticia_id` (bigint, not null)
- `tipo` (character varying(30), not null)
- `valor` (text, not null)
- `score` (double precision)
- `creado_en` (timestamp without time zone, default now())
- `valor_normalizado` (text)

#### keywords_prioridad
- `id` (bigint, PK)
- `keyword` (text, not null)
- `tipo` (character varying(30))
- `puntos` (integer, default 0, not null)
- `activo` (boolean, default true)
- `creado_en` (timestamp without time zone, default now())

#### publicaciones
- `id` (bigint, PK)
- `cluster_id` (bigint)
- `wordpress_post_id` (bigint)
- `tipo` (character varying(30))
- `titulo` (text)
- `score_publicado` (double precision)
- `cantidad_noticias` (integer)
- `publicada_en` (timestamp without time zone, default now())
- `url_wordpress` (text)

#### urls
- `id` (integer, PK)
- `url` (text, not null)
- `estado` (integer, default 0)
- `fecha_creacion` (timestamp without time zone, default CURRENT_TIMESTAMP)
- `fecha_procesado` (timestamp without time zone)
- `fuente` (character varying(100))

## Cómo funcionan los crawlers (ej: nuevodiario_crawler.py)
- Obtienen una conexión a la misma base de datos.
- Tienen una lista de agentes de usuario para evitar bloqueos.
- Excluyen ciertos paths y extensiones (admin, imágenes, etc.).
- Procesan páginas: extraen enlaces y los guardan en la tabla `urls` (evitando duplicados).
- Detectan artículos probables (presencia de h1.titulo-nota y varios párrafos).
- Extraen título, fecha y texto del artículo.
- Generan hashes para detección de duplicados (por contenido y por url+titulo).
- Si no es duplicado, insertan o actualizan la noticia en `noticias_historico`.
- Registran logs de actividad.

## Requisitos
- Python 3.11+
- Dependencias listadas en `requirements.txt` (incluye `spacy` y modelo `es_core_news_md`).
- Variables de entorno definidas en `.env` (ver `.env.example`).

### Instalación rápida
```bash
python3 -m venv trh
source trh/bin/activate
pip install -r requirements.txt
python -m spacy download es_core_news_md
```

### Variables de entorno para `embedding_archivo.py`
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD` (requerida)
- `OLLAMA_URL`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMENSION`
- `EMBEDDING_BATCH_LIMIT`
- `EMBEDDING_COMMIT_EVERY` (cada cuántas noticias confirmar transacción)
- `EMBEDDING_RETRIES` (reintentos ante fallo transitorio)
- `EMBEDDING_RETRY_BACKOFF_SECONDS` (espera incremental entre reintentos)

## Notas de Operación
- El sistema asume que la base de datos ya está poblada con estructuras de tablas (se puede crear mediante migraciones externas).
- Los crawlers pueden ejecutarse de forma periódica (por ejemplo, mediante cron) para alimentar la cola de URLs.
- El dashboard se actualiza en tiempo real al cargar la página (consulta en vivo a la BD).

## Pipeline de preprocesamiento (`proceso.py`)
- Ejecuta crawlers en paralelo:
  - `crawler/elliberal_crawler.py`
  - `crawler/panorama_crawler.py`
  - `crawler/nuevodiario_crawler.py`
  - `crawler/termasdigital_crawler.py`
  - `crawler/sursantiago_crawler.py`
- Luego corre en secuencia:
  - `embedding_archivo.py`
  - `cluster_noticias.py`
  - `extraer_keywords_ner.py`
- Protección anti-solapamiento para cron:
  - 1 ejecución activa máxima
  - cola máxima de espera: 1
  - si llega una tercera ejecución, se cancela.

## Criterios de recencia (7 días)
- `cluster_noticias.py` procesa solo noticias sin cluster con `fecha_publicacion` de los últimos 7 días.
- Clusters sin noticias con `fecha_publicacion` reciente (>7 días) se eliminan automáticamente.
- `extraer_keywords_ner.py` analiza noticias de 7 días por `fecha_publicacion` y limpia `noticias_keywords` antiguas para evitar crecimiento infinito.
- Para tendencia horaria en clustering, se usa `fecha_publicacion` + hora de `fecha_extraccion` como aproximación.

## Posibles Mejoras
- Agregar cache de consultas frecuentes.
- Implementar un sistema de colas (Redis/RabbitMQ) para los crawlers.
- Añadir autenticación al dashboard.
- Exportar reportes en PDF/CSV.