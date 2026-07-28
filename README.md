# TRH Panel

Pipeline para extraer noticias, agruparlas por similitud, asistir la revisión editorial en un panel web y publicar artículos con IA en WordPress.

> **Guía para operadores y editores.** Si vas a desarrollar o mantener el código, empezá por [`docs/repo-layout.md`](docs/repo-layout.md).

---

## ¿Qué hace TRH en una frase?

Recoge noticias de distintos sitios, detecta cuáles hablan del mismo tema, les saca palabras clave, presenta esos grupos en un panel para que un editor elija y, desde ahí, genera un artículo unificado con IA y lo publica en WordPress.

---

## Flujo de datos completo

Este es el camino que recorre una noticia desde que aparece en un sitio fuente hasta que se convierte en un artículo publicado.

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Sitios web    │────▶│   Crawlers      │────▶│   noticias_     │
│   de fuentes    │     │   (uno por      │     │   historico     │
│                 │     │   fuente)       │     │   (tabla DB)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  clusters_      │◀────│  Clustering     │◀────│  Embeddings     │
│  editoriales    │     │  (similitud)    │     │  (vectoriza)    │
│  (tabla DB)     │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Keywords /     │────▶│  Panel web      │────▶│  Artículo con   │
│  entidades      │     │  (app.py)       │     │  IA             │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │  WordPress      │
                                                │  (publicación)  │
                                                └─────────────────┘
```

### Pasos en orden

1. **Crawlers** (`crawler/sites/*_crawler.py`) — Entran a cada sitio fuente, extraen títulos, texto, fecha, imagen y guardan todo en `noticias_historico`.
2. **Embeddings** (`pipeline/embedding_archivo.py`) — Convierte el contenido de cada noticia en un vector numérico y lo guarda en una columna `pgvector`.
3. **Clustering** (`pipeline/cluster_noticias.py`) — Compara vectores y agrupa noticias que tratan el mismo tema en un solo registro de `clusters_editoriales`.
4. **Keywords y entidades** (`pipeline/extraer_keywords_ner.py`) — Detecta personas, organizaciones, lugares y frases clave del grupo.
5. **Selección** (`pipeline/seleccionar_publicables.py`) — Decide qué clusters son candidatos a publicar según reglas de ventana de tiempo y penalización.
6. **Panel editorial** (`app.py`) — El editor revisa, elige, edita y aprueba.
7. **Generación con IA** (`trh/publication/publicador.py`) — Escribe un artículo unificado con título, resumen, cuerpo y categoría.
8. **Publicación** (`trh/publication/publicapress.py`) — Sube el artículo, imágenes y categoría a WordPress.

> Para ver el detalle del orquestador que une las primeras etapas, leé [`docs/proceso.md`](docs/proceso.md).

---

## Estados de un cluster

Un cluster pasa por estos estados a medida que avanza el flujo:

```
      ┌─────────────┐
      │   NUEVO     │  (creado por cluster_noticias.py)
      └──────┬──────┘
             │
             ▼
      ┌─────────────┐
      │  PENDIENTE  │  (listo para revisión editorial)
      └──────┬──────┘
             │
      ┌──────┴──────┐
      │             │
      ▼             ▼
┌─────────┐   ┌─────────────┐
│GENERADO │   │   RECHAZADO │
│  (IA)   │   │  (descartado)│
└────┬────┘   └─────────────┘
     │
     ▼
┌─────────────┐
│  PUBLICADO  │  (ya en WordPress)
└─────────────┘
```

- **NUEVO**: recién creado por el clustering.
- **PENDIENTE**: candidato a revisión. El editor lo ve en el panel.
- **GENERADO**: se generó un borrador con IA. El editor puede editar y publicar.
- **RECHAZADO**: el editor decidió descartarlo.
- **PUBLICADO**: ya fue enviado a WordPress.

---

## Instalación oficial

La forma oficial de instalar es con el script remoto:

```bash
curl -fsSL https://raw.githubusercontent.com/Clowraider/trh/main/install.sh | sh
```

Para ver qué haría sin tocar nada:

```bash
curl -fsSL https://raw.githubusercontent.com/Clowraider/trh/main/install.sh | sh -s -- --dry-run
```

### Requisitos previos

Antes de correr el instalador:

- **PostgreSQL con `pgvector`**. Sin esta extensión no funciona la similitud ni el clustering.
- **Usuario normal**, no root. El script usa `sudo` solo cuando necesita paquetes del sistema.
- **API key de OpenRouter** con saldo disponible.
- **WordPress** con URL, usuario y **Application Password** lista.
- **Modelo de embeddings local y estable**. Preferentemente un modelo local, guardado como artefacto crítico: si cambia el modelo, cambian los vectores y se pierde consistencia histórica.

### Instalación manual (si el script no aplica)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download es_core_news_md

cp .env.example .env
# editar .env con tus credenciales

./scripts/check_env.sh
./scripts/init_db.sh
python3 app.py
```

Panel: `http://localhost:5000/`

---

## Operación diaria

### Correr el pipeline

El pipeline principal se ejecuta con:

```bash
python3 proceso.py
```

Hace esto en orden:

1. Ejecuta todos los crawlers en paralelo.
2. Genera embeddings.
3. Agrupa en clusters.
4. Extrae keywords y entidades.

Además gestiona locks para que no se pisen dos ejecuciones, y permite encolar una sola corrida más.

> Ver detalle completo: [`docs/proceso.md`](docs/proceso.md)

### Levantar el panel editorial

```bash
python3 app.py
```

Desde el panel el editor puede:

- Ver clusters pendientes.
- Revisar noticias fuente.
- Generar un borrador con IA.
- Editar título, resumen, cuerpo y categoría.
- Seleccionar fotos principal y secundarias.
- Guardar cambios.
- Publicar en WordPress.

### Cron sugerido

Ejecutar el pipeline cada pocas horas, según la frecuencia de publicación de tus fuentes:

```cron
0 7,10,13,16,19,22 * * * cd /ruta/TRH && /ruta/TRH/.venv/bin/python3 proceso.py >> /ruta/TRH/logs/proceso.log 2>&1
```

Evitá frecuencias agresivas para no saturar sitios pequeños.

---

## Estructura del repo (para operadores)

| Carpeta / archivo | Qué contiene |
|---|---|
| `app.py` | Panel web Flask. |
| `proceso.py` | Orquestador del pipeline de crawlers → embeddings → clusters → keywords. |
| `crawler/sites/` | Un archivo por cada sitio fuente. Acá se agregan nuevos medios. |
| `pipeline/` | Procesamiento de datos: embeddings, clustering, keywords, selección. |
| `trh/publication/` | Generación de artículos con IA y publicación en WordPress. |
| `trh/editorial/` | Control editorial y selección asistida por IA. |
| `prompts/` | Prompts y reglas que usa la IA. |
| `templates/` | Pantallas del panel. |
| `scripts/` | Utilidades de entorno, inicialización y wrappers. |
| `deploy/` | Ejemplos de systemd y nginx. |
| `docs/` | Documentación del sistema. |

---

## Documentación específica

- [`docs/proceso.md`](docs/proceso.md) — Cómo funciona el pipeline principal (`proceso.py`).
- [`docs/repo-layout.md`](docs/repo-layout.md) — Cómo está organizado el código (para desarrolladores).

Próximos documentos planificados:

- `docs/cluster_noticias.md` — Cómo agrupa noticias.
- `docs/embedding_archivo.md` — Cómo se generan los embeddings.
- `docs/extraer_keywords_ner.md` — Cómo se extraen keywords y entidades.
- `docs/seleccionar_publicables.md` — Cómo se eligen los clusters publicables.
- `docs/panel.md` — Flujo del panel editorial.
- `docs/publicacion.md` — Cómo se genera y publica un artículo.

---

## Pruebas

Antes de cambios sensibles, corré:

```bash
python -m pytest -q
```

---

## Producción (mínimo recomendado)

### 1) Pipeline con cron

Programar `proceso.py` en horarios definidos según la frecuencia de tus fuentes.

### 2) Panel como servicio (`systemd`)

Ejemplo base en `deploy/trh-panel.service`.

### 3) Reverse proxy (`nginx`)

Recomendado para exponer el panel en 80/443 mientras `app.py` escucha en localhost.

Archivos listos para copiar en `deploy/`:

- `deploy/trh-panel.service`
- `deploy/nginx-trh.conf`
- `deploy/README.md`

---

## Troubleshooting básico

### Error con embeddings / similitud

- Verificar que `pgvector` esté instalado en PostgreSQL.
- Reejecutar `./scripts/init_db.sh`.

### Fallos por credenciales o variables faltantes

- Ejecutar `./scripts/check_env.sh`.
- Confirmar `.env` completo (DB, OpenRouter, WordPress).

### El pipeline no corre

- Revisar `logs/proceso.log`.
- Verificar que no haya un lock viejo atascado (`scripts/` limpia locks si se ejecuta correctamente, pero un corte abrupto puede dejar uno). En ese caso, ver los archivos de lock en `/tmp` o donde esté configurado.

### Saturación de sitios fuente

- No aumentar la frecuencia de `proceso.py` sin necesidad.
- Mantener horarios razonables y monitorear tiempos/respuestas.

### Problemas de publicación en WordPress

- Verificar `WP_URL`, `WP_USERNAME` y `WP_APP_PASSWORD`.
- Confirmar que el usuario de WordPress tenga permisos para crear posts y categorías.
- Revisar logs del panel para ver el error exacto de la API REST.

---

## Versión

- Estado actual del proyecto: **v1.1.0**
