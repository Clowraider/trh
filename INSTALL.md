# Instalación en servidor limpio (VPS o Proxmox)

## Requisitos previos
- Ubuntu 24 LTS
- Docker instalado
- Portainer instalado (opcional)

---

## 1 — Instalar Git

```bash
apt-get install git -y
```

## 2 — Crear estructura de carpetas

```bash
mkdir -p /root/docker/trh/postgres
mkdir -p /root/docker/trh/codigo
mkdir -p /root/docker/trh/imagenes
mkdir -p /root/docker/trh/logs
```

## 3 — Clonar repositorio

```bash
git config --global credential.helper store
cd /root/docker/trh/codigo
git clone https://github.com/Clowraider/trh.git .
```

Usuario: Clowraider
Contraseña: token de GitHub (Settings → Developer settings → Tokens → classic → repo)

## 4 — Construir imágenes Docker

```bash
# imagen del scraper
cd /root/docker/trh/codigo/scraper
docker build -t trh-scraper .

# imagen del backend
cd /root/docker/trh/codigo/backend
docker build -t trh-backend .

# imagen del frontend
cd /root/docker/trh/codigo/frontend
docker build -t trh-frontend .
```

## 5 — Crear stack en Portainer

Portainer → Stacks → Add stack → pegar yaml:

```yaml
services:
  db:
    image: postgres:16
    restart: always
    shm_size: 128mb
    environment:
      POSTGRES_DB: trh_noticias
      POSTGRES_USER: trh_user
      POSTGRES_PASSWORD: cambiar_esto
    volumes:
      - /root/docker/trh/postgres:/var/lib/postgresql/data
    ports:
      - 5432:5432

  adminer:
    image: adminer
    restart: always
    ports:
      - 8085:8080

  scraper:
    image: trh-scraper
    restart: always
    volumes:
      - /root/docker/trh/codigo:/app
      - /root/docker/trh/imagenes:/root/docker/trh/imagenes
    depends_on:
      - db

  backend:
    image: trh-backend
    restart: always
    volumes:
      - /root/docker/trh/codigo/backend:/app
      - /root/docker/trh/imagenes:/root/docker/trh/imagenes
    ports:
      - 8001:8000
    depends_on:
      - db

  frontend:
    image: trh-frontend
    restart: always
    ports:
      - 8004:8000
```

Clic en **Deploy the stack**.

## 6 — Configurar variables de entorno en Portainer

Después de crear el stack, agregar las variables en cada contenedor:

### Backend (trh2-backend-1)
- Edit → Environment → Add variable:
  - `API_KEY` = tu_api_key_real
  - `DB_HOST` = db
  - `DB_PORT` = 5432
  - `DB_NAME` = trh_noticias
  - `DB_USER` = trh_user
  - `DB_PASSWORD` = cambiar_esto
  - `CARPETA_IMAGENES` = /root/docker/trh/imagenes

### Frontend (trh2-frontend-1)
- Edit → Environment → Add variable:
  - `API_KEY` = tu_api_key_real
  - `API_BASE_URL` = http://192.168.0.53:8001
  - `ADMIN_PASSWORD` = admin123
  - `SECRET_KEY` = tu_secret_key_largo

### Scraper (trh2-scraper-1)
- Edit → Environment → Add variable:
  - `DB_HOST` = db
  - `DB_PORT` = 5432
  - `DB_NAME` = trh_noticias
  - `DB_USER` = trh_user
  - `DB_PASSWORD` = cambiar_esto
  - `OPENROUTER_API_KEY` = tu_api_key_openrouter
  - `CARPETA_IMAGENES` = /root/docker/trh/imagenes

**Importante:** Después de agregar variables, reiniciar el contenedor.

## 7 — Inicializar la base de datos

```bash
docker exec -it trh2-scraper-1 python3 /app/scraper/db.py
```

Verificar en Adminer (http://IP:8085) que se crearon las tablas:
- noticias, categorias, noticias_categorias, contenido

Credenciales Adminer:
```
Sistema:    PostgreSQL
Servidor:   db
Usuario:    trh_user
Contraseña: cambiar_esto
Base datos: trh_noticias
```

## 8 — Verificar que el scraper funciona

```bash
docker exec -it trh2-scraper-1 python3 /app/scraper/collector.py
```

## 9 — Configurar cron en el servidor

```bash
crontab -e
```

Agregar al final:

```
*/5 * * * * docker exec trh2-scraper-1 python3 /app/scraper/collector.py >> /root/docker/trh/logs/collector.log 2>&1
*/5 * * * * sleep 60 && docker exec trh2-scraper-1 python3 /app/scraper/extractor_collector.py >> /root/docker/trh/logs/extractor.log 2>&1
*/5 * * * * sleep 120 && docker exec trh2-scraper-1 python3 /app/scraper/resumidor.py >> /root/docker/trh/logs/resumidor.log 2>&1
```

Guardar: Ctrl+X → Y → Enter

Verificar: `crontab -l`

## 10 — Verificar la API

```bash
curl -H "Authorization: TU_API_KEY" http://localhost:8001/noticias
```

Debe devolver JSON con noticias.

---

## Actualizar código

```bash
cd /root/docker/trh/codigo
git pull
# si no baja cambios:
git fetch origin && git reset --hard origin/main
```

Si cambió Dockerfile o requirements.txt reconstruir imagen:

```bash
# scraper
cd /root/docker/trh/codigo/scraper
docker build --no-cache -t trh-scraper .

# backend
cd /root/docker/trh/codigo/backend
docker build --no-cache -t trh-backend .

# frontend
cd /root/docker/trh/codigo/frontend
docker build --no-cache -t trh-frontend .
```

Luego en Portainer: **Update the stack**.

---

## Comandos útiles

```bash
# ver contenedores corriendo
docker ps

# ver cron configurado
crontab -l

# correr scripts manualmente
docker exec -it trh2-scraper-1 python3 /app/scraper/collector.py
docker exec -it trh2-scraper-1 python3 /app/scraper/extractor_collector.py
docker exec -it trh2-scraper-1 python3 /app/scraper/resumidor.py

# ver logs
cat /root/docker/trh/logs/collector.log
cat /root/docker/trh/logs/extractor.log
cat /root/docker/trh/logs/resumidor.log

# entrar a un contenedor
docker exec -it trh2-scraper-1 bash
docker exec -it trh2-backend-1 bash
```

---

## Notas importantes

- Cron corre en el vps, NO dentro de los contenedores
- Las imágenes se guardan en /root/docker/trh/imagenes/
- Para moderar noticias usar el panel de admin: http://192.168.0.53:8004/admin03-login
- La API requiere header Authorization con la API key
- El extractor solo procesa noticias con estado 'aprobado'
- El resumidor solo procesa noticias con estado 'completo' y sin resumen_ia