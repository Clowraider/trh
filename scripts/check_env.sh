#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .env ]]; then
	echo "❌ Falta .env (copiá .env.example)"
	exit 1
fi

required=(
	DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD
	OPENROUTER_API_KEY OPENROUTER_URL OPENROUTER_MODEL_PRIMARY OPENROUTER_MODEL_FALLBACK
	WP_URL WP_USERNAME WP_APP_PASSWORD
)

missing=0
for key in "${required[@]}"; do
	if ! grep -q "^${key}=" .env; then
		echo "❌ Falta ${key} en .env"
		missing=1
	fi
done

if [[ "$missing" -eq 1 ]]; then
	exit 1
fi

echo "✅ Variables requeridas presentes en .env"
