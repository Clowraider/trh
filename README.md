# TRH Panel

Pipeline para extraer noticias, procesarlas con embeddings/clustering, asistir edición en panel y publicar con IA.

## ¿Para qué sirve?

1. Crawlers: buscan links y extraen noticias.
2. Embeddings: vectorizan contenido para similitud.
3. Clusters: agrupan noticias relacionadas.
4. Keywords: extraen palabras clave.
5. Panel: revisión editorial manual.
6. IA: genera artículo del cluster elegido.
7. Publicación: envía a WordPress.

---

## Requisitos

- Python **3.11**
- PostgreSQL
- Extensión **pgvector** (obligatoria para embeddings/similitud)
- Dependencias Python de `requirements.txt`

> Sin `pgvector`, se degrada el flujo de embeddings y búsqueda de artículos similares.

---

## Instalación desde cero

### Instalación rápida

```bash
curl -fsSL https://raw.githubusercontent.com/Clowraider/trh/main/install.sh | sh
```

Para pasar opciones al instalador interno:

```bash
curl -fsSL https://raw.githubusercontent.com/Clowraider/trh/main/install.sh | sh -s -- --dry-run
```

### Requisitos y preparación

Antes de correr el instalador, asegurate de esto:

- **PostgreSQL disponible**: la app necesita PostgreSQL y la extensión `pgvector` para embeddings y similitud.
- **Usuario normal, no root**: ejecutá el instalador con una cuenta común. `scripts/install.sh` usa `sudo` solo cuando hace falta para paquetes del sistema.
- **OpenRouter con saldo**: necesitás una API key válida y con crédito disponible para que funcionen las integraciones del proyecto.
- **WordPress listo para integración**: vas a necesitar la URL del sitio, el usuario y una **Application Password** de WordPress.
- **Modelo de embeddings local y estable**: definí un modelo local de embeddings en tu idioma.

### Sobre el modelo de embeddings

El modelo de embeddings conviene que sea **local**.

¿Por qué?

- porque **no debe cambiar con el tiempo**;
- porque si cambia el modelo, cambian los vectores y perdés consistencia histórica;
- porque el backup del archivo del modelo vale **oro**: guardalo como un artefacto crítico de tu instalación.

1) Crear entorno e instalar dependencias:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download es_core_news_md
```

2) Configurar variables:

```bash
cp .env.example .env
# editar .env
```

3) Verificar variables requeridas:

```bash
./scripts/check_env.sh
```

4) Inicializar base de datos:

```bash
./scripts/init_db.sh
```

5) Levantar panel:

```bash
python3 app.py
```

Panel: `http://localhost:5000/`

---

## Operación diaria

### Pipeline principal

Se ejecuta con:

```bash
python3 proceso.py
```

`proceso.py` hace:
- Crawlers en paralelo: descubre y ejecuta automáticamente todos los archivos `crawler/sites/*_crawler.py`. Ahí es donde cada instalación agrega sus propios extractores; no van al repo base.
- Como ejemplo y punto de partida se incluye `crawler/sites/plantilla_crawler.py`. Copialo, renombralo y adaptalo a tu sitio.
- Luego, secuencial:
  - `pipeline/embedding_archivo.py`
  - `pipeline/cluster_noticias.py`
  - `pipeline/extraer_keywords_ner.py`

Incluye locks para evitar ejecuciones solapadas y para permitir una sola corrida en cola.

### Panel editorial

```bash
python3 app.py
```

### Publicación con IA

Se realiza desde el flujo del panel sobre el artículo elegido.

---

## Cron sugerido (pipeline)

Ejemplo (ajustar horarios):

```cron
0 7,10,13,16,19,22 * * * cd /ruta/TRH && /ruta/TRH/.venv/bin/python3 proceso.py >> /ruta/TRH/logs/proceso.log 2>&1
```

---

## Pruebas

Hay tests en `tests/`.

Ejecución recomendada antes de cambios sensibles:

```bash
python -m pytest -q
```

---

## Producción (mínimo recomendado)

### 1) Pipeline con cron

Programar `proceso.py` en horarios definidos (según actualización de fuentes), evitando frecuencia excesiva para no saturar sitios pequeños.

### 2) Panel como servicio (`systemd`)

Ejemplo base de unidad:

```ini
[Unit]
Description=TRH Panel
After=network.target

[Service]
User=TU_USUARIO
WorkingDirectory=/ruta/TRH
Environment="PATH=/ruta/TRH/.venv/bin"
ExecStart=/ruta/TRH/.venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### 3) Reverse proxy (`nginx`)

Recomendado para exponer el panel de forma estable (puerto 80/443) y dejar `app.py` sólo en localhost.

Configuración lista para copiar en `deploy/`:
- `deploy/trh-panel.service`
- `deploy/nginx-trh.conf`
- `deploy/README.md`

---

## Extracción de keywords y entidades

Se usa `pipeline/extraer_keywords_ner.py` con enfoque híbrido:

- **YAKE** (`yake`): extracción estadística de frases clave (tipo `keyword`), con `n=2`, deduplicación y top limitado.
- **spaCy NER** (`spacy` + `es_core_news_md`): detección de entidades para:
  - `PER` → `persona`
  - `ORG` → `organizacion`
  - `LOC` → `lugar`

Además se aplican filtros de ruido:
- eliminación de términos basura/promocionales;
- límites por longitud/cantidad;
- deduplicación por valor normalizado;
- limpieza periódica de keywords fuera de ventana de análisis.

---

## Fotos y marca de agua

En el panel de cluster se puede elegir foto principal/secundarias desde las noticias fuente o subir fotos manuales temporales.

- Las fotos temporales se guardan en `static/uploads/tmp/cluster_<id>/`.
- Al publicar correctamente en WordPress, esas fotos temporales locales se borran.
- Las imágenes subidas a WordPress **no se borran**, porque quedan asociadas al post.
- La marca de agua se configura con variables `WATERMARK_*` en `.env`.

---

## Troubleshooting básico

### 1) Error con embeddings / similitud
- Verificar que `pgvector` esté instalado en la DB.
- Reejecutar `./scripts/init_db.sh`.

### 2) Fallos por credenciales o variables faltantes
- Ejecutar `./scripts/check_env.sh`.
- Confirmar `.env` completo (DB, OpenRouter, WordPress).

### 3) Riesgo de saturar sitios fuente
- No aumentar agresivamente frecuencia de corridas.
- Mantener horarios razonables y monitorear tiempos/respuestas.
- Priorizar estabilidad para no consumir ancho de banda de sitios pequeños.

---

## Estructura del repo (actual)

- `crawler/`: crawlers por fuente.
- `pipeline/`: procesamiento (embeddings, clustering, keywords, selección).
- `deploy/`: archivos sugeridos para systemd/nginx.
- `scripts/`: utilidades de entorno, inicialización y wrappers ejecutables.
- `skills/`: skills/protocolos auxiliares del proyecto.
- raíz (`app.py`, `proceso.py`): orchestration entrypoints.
- `trh/editorial/`: reusable editorial-selection and editorial-review modules.
- `trh/publication/`: reusable article-generation and WordPress-publication modules.

> Compatibilidad: los wrappers ejecutables viven en `scripts/` (`scripts/embedding_archivo.py`, `scripts/cluster_noticias.py`, `scripts/extraer_keywords_ner.py`, `scripts/seleccionar_publicables.py`), mientras que otros entrypoints de raíz como `correccion_sur_santiago.py` siguen en su ubicación actual.

## Estructura de esquema

- `estructura.sql`: snapshot actual del esquema (fuente única).

## Versión

- Estado actual del proyecto: **v1.1.0**
