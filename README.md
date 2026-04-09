# TRH - Portal de Noticias de Santiago del Estero

## Problema
El sitio original de WordPress requería horas diarias copiando, pegando y resumiendo artículos de otras fuentes. Un proceso manual que consumía cientos de horas al mes.

## Solución
Sistema automatizado de scraping que:
- Recolecta noticias de fuentes RSS automáticamente
- Panel de administración para aprobar/rechazar artículos
- Al aprobar: genera resumen con IA, descarga imágenes y extrae contenido completo
- Publica automáticamente después de la aprobación

## Ahorro
- **Antes**: ~10 horas/día de trabajo manual
- **Después**: 1 hora (todo automatizado)
- **Resultado**: +100 horas mensuales recuperadas

---

## Descripción
Portal de noticias automáticas de Santiago del Estero, Argentina. Recolecta contenido de fuentes locales y genera resúmenes con IA.

## Características
- Scraping automático vía RSS
- Panel de administración para moderación
- Resúmenes con IA (OpenRouter)
- API REST
- Interfaz web moderna con HTMX

## Tech Stack
- Python 3.12 + FastAPI
- PostgreSQL 16
- Docker + Portainer

## Instalación Rápida (Local)

```bash
# 1. Clonar
git clone https://github.com/Clowraider/trh.git
cd trh

# 2. Configurar variables de entorno
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
cp scraper/.env.example scraper/.env

# 3. Editar .env con tus claves (API keys, passwords)

# 4. Ejecutar
docker-compose up -d
```

## Configuración
El proyecto usa variables de entorno para datos sensibles (API keys, passwords). Ver `.env.example` en cada carpeta.

Ver INSTALL.md para instalación completa en servidor.

## Estructura
```
trh/
├── scraper/      # Recolector de noticias (RSS → DB)
├── backend/      # API REST
├── frontend/     # Interfaz web (HTMX)
├── INSTALL.md    # Guía de instalación en servidor
└── .gitignore
```

## Licencia
MIT

---

# TRH - Santiago del Estero News Portal

## Problem
The original WordPress site required hours daily copying, pasting, and summarizing articles from other sources. A manual process that consumed hundreds of hours per month.

## Solution
Automated scraping system that:
- Automatically collects news from RSS sources
- Admin panel to approve/reject articles
- Upon approval: generates AI summary, downloads images and extracts full content
- Automatically publishes after approval

## Savings
- **Before**: ~10 hours/day of manual work
- **After**: 1 hours (fully automated)
- **Result**: +100 hours per month recovered

---

## Description
Automated news portal for Santiago del Estero, Argentina. Collects content from local sources and generates AI summaries.

## Features
- Automatic RSS scraping
- Admin panel for moderation
- AI summaries (OpenRouter)
- REST API
- Modern HTMX web interface

## Tech Stack
- Python 3.12 + FastAPI
- PostgreSQL 16
- Docker + Portainer

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Clowraider/trh.git
cd trh

# 2. Configure environment variables
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
cp scraper/.env.example scraper/.env

# 3. Edit .env with your keys

# 4. Run
docker-compose up -d
```

See INSTALL.md for server deployment.

## License
MIT