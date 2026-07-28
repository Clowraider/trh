# Funcionamiento de `proceso.py`

`proceso.py` es el orquestador del pipeline de ingesta y procesamiento. Su trabajo es coordinar las etapas que transforman noticias crudas en clusters listos para revisión editorial.

No procesa datos él mismo: delega cada etapa en scripts especializados de la carpeta `pipeline/`.

---

## ¿Qué hace?

1. Descubre y ejecuta todos los crawlers configurados.
2. Genera embeddings para las noticias nuevas.
3. Agrupa noticias similares en clusters.
4. Extrae keywords y entidades de cada cluster.

Al finalizar, los clusters quedan en la tabla `clusters_editoriales` con estado pendiente, listos para que el editor los revise en el panel.

---

## Flujo interno

```
┌─────────────────────────────────────────────────────────────┐
│                         proceso.py                          │
│                                                             │
│  1. Bloquear ejecución concurrente (lock)                   │
│  2. Descubrir crawlers en crawler/sites/*_crawler.py        │
│  3. Ejecutar crawlers en paralelo                           │
│  4. Ejecutar pipeline/embedding_archivo.py                  │
│  5. Ejecutar pipeline/cluster_noticias.py                   │
│  6. Ejecutar pipeline/extraer_keywords_ner.py               │
│  7. Liberar lock                                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Locks y concurrencia

`proceso.py` usa un mecanismo de lock para evitar que dos ejecuciones se pisen. Esto es importante porque:

- Las etapas leen y escriben en las mismas tablas.
- Si dos corridas generan embeddings o clusters al mismo tiempo, pueden crear duplicados o estados inconsistentes.

Comportamiento:

- Si el lock está libre, la ejecución arranca y toma el lock.
- Si el lock está tomado y no hay otra corrida esperando, la nueva ejecución se encola y espera.
- Si ya hay una corrida esperando, la nueva se descarta con un mensaje. Solo se permite **una corrida en cola** como máximo.

> En caso de que un corte de luz o un kill deje el lock colgado, se puede revisar manualmente en la ruta configurada (típicamente `/tmp/`). El script no borra locks a la fuerza para no romper una ejecución real en curso.

---

## Detalle de cada etapa

### 1. Crawlers (`crawler/sites/*_crawler.py`)

Cada archivo que termine en `_crawler.py` dentro de `crawler/sites/` es un crawler válido. `proceso.py` los descubre automáticamente y los ejecuta en paralelo.

Cada crawler debe:

- Leer su configuración de fuente (URL, selectores, etc.).
- Extraer título, texto, fecha, imagen y URL de cada noticia.
- Guardar los resultados en la tabla `noticias_historico`.

Cómo agregar una fuente nueva:

1. Copiar `crawler/sites/plantilla_crawler.py`.
2. Renombrarlo, por ejemplo `crawler/sites/minuevo_crawler.py`.
3. Adaptar las URLs y selectores.
4. La próxima ejecución de `proceso.py` lo detectará automáticamente.

### 2. Embeddings (`pipeline/embedding_archivo.py`)

Toma las noticias que aún no tienen vector y genera un embedding numérico con el modelo configurado en `.env` (`EMBEDDING_MODEL`).

El embedding se guarda en una columna `pgvector` de PostgreSQL, lo que permite después calcular similitud entre noticias.

Cosas importantes:

- El modelo de embeddings debe ser **local y estable**. Si se cambia, todos los vectores históricos pierden comparabilidad.
- Usa batching para no saturar Ollama u otro servidor de embeddings.
- Tiene reintentos con backoff ante fallos transitorios.

### 3. Clustering (`pipeline/cluster_noticias.py`)

Compara los vectores de las noticias y agrupa las que son similares en un mismo cluster.

Lo que hace, a grandes rasgos:

- Lee noticias sin cluster o con embedding nuevo.
- Calcula distancias entre vectores usando `pgvector`.
- Aplica un umbral de similitud: si dos noticias están lo suficientemente cerca, van al mismo cluster.
- Crea o actualiza registros en `clusters_editoriales`.
- Marca las noticias con el `cluster_id` correspondiente.

El resultado es un grupo de noticias que hablan del mismo hecho, evento o persona.

### 4. Keywords y entidades (`pipeline/extraer_keywords_ner.py`)

Por cada cluster, extrae:

- **Entidades con spaCy NER**:
  - `PER` → `persona`
  - `ORG` → `organizacion`
  - `LOC` → `lugar`
- **Frases clave con YAKE** (`keyword`).

Aplica filtros de ruido:

- Elimina términos basura o promocionales.
- Limita por longitud y cantidad.
- Deduplica por valor normalizado.
- Limpia keywords viejas fuera de la ventana de análisis.

Estas keywords ayudan al editor a entender de qué trata el cluster de un vistazo.

---

## Ejecución manual

```bash
cd /ruta/TRH
source .venv/bin/activate
python3 proceso.py
```

Salida esperada en consola (según logging configurado):

- Crawlers ejecutándose.
- Cantidad de noticias nuevas.
- Progreso de embeddings.
- Clusters creados o actualizados.
- Keywords extraídas.

---

## Ejecución con cron

Ejemplo para correr el pipeline cada 3 horas:

```cron
0 7,10,13,16,19,22 * * * cd /ruta/TRH && /ruta/TRH/.venv/bin/python3 proceso.py >> /ruta/TRH/logs/proceso.log 2>&1
```

Ajustá los horarios según la frecuencia real de publicación de tus fuentes.

---

## Logs y monitoreo

Recomendaciones operativas:

- Redirigir la salida a un archivo de log rotativo (`logs/proceso.log`).
- Revisar periódicamente:
  - Cuántas noticias trajo cada crawler.
  - Si el clustering dejó noticias sueltas.
  - Si `extraer_keywords_ner.py` falló por falta de modelo spaCy.

---

## Errores comunes

### "Otra ejecución ya está en curso"

Significa que el lock está tomado. Esperá a que termine o revisá si quedó colgado.

### "No se encontraron crawlers"

Verificá que exista al menos un archivo `crawler/sites/*_crawler.py`.

### Fallo en embeddings

- Verificar que Ollama (o el servidor de embeddings) esté corriendo.
- Verificar `OLLAMA_URL` y `EMBEDDING_MODEL` en `.env`.
- Verificar que el modelo esté descargado localmente.

### Fallo en clustering

- Verificar que `pgvector` esté instalado en PostgreSQL.
- Verificar que la columna de embedding exista y tenga datos.

### Fallo en keywords

- Verificar que spaCy esté instalado y el modelo `es_core_news_md` descargado:
  ```bash
  python -m spacy download es_core_news_md
  ```

---

## Relación con el resto del sistema

```
proceso.py
    │
    ├──▶ noticias_historico
    │
    ├──▶ clusters_editoriales (estado NUEVO / PENDIENTE)
    │
    └──▶ keywords / entidades
              │
              ▼
         panel (app.py)
              │
              ▼
         generación con IA → publicación en WordPress
```

`proceso.py` se encarga de todo lo que pasa **antes** de que el editor abra el panel. Una vez que el cluster está en estado pendiente, el control pasa al panel editorial (`app.py`).
