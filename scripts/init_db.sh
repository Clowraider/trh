#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .env ]]; then
  echo "❌ Falta .env"
  exit 1
fi

DB_HOST=$(grep '^DB_HOST=' .env | cut -d= -f2-)
DB_PORT=$(grep '^DB_PORT=' .env | cut -d= -f2-)
DB_NAME=$(grep '^DB_NAME=' .env | cut -d= -f2-)
DB_USER=$(grep '^DB_USER=' .env | cut -d= -f2-)
DB_PASSWORD=$(grep '^DB_PASSWORD=' .env | cut -d= -f2-)

if [[ -z "${DB_HOST}" || -z "${DB_PORT}" || -z "${DB_NAME}" || -z "${DB_USER}" || -z "${DB_PASSWORD}" ]]; then
  echo "❌ Variables DB incompletas en .env"
  exit 1
fi

if [[ ! -f estructura.sql ]]; then
  echo "❌ Falta estructura.sql"
  exit 1
fi

export PGPASSWORD="$DB_PASSWORD"

DB_EXISTS=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'")
if [[ "$DB_EXISTS" != "1" ]]; then
  echo "📦 Creando base ${DB_NAME}"
  createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"
fi

echo "🧩 Asegurando extensión vector"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "🛠 Aplicando estructura.sql"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f estructura.sql

echo "✅ DB inicializada"
