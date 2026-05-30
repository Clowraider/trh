# TRH Panel

## Instalación desde cero

1. Crear entorno y dependencias:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configurar variables:

```bash
cp .env.example .env
# editar .env
```

3. Verificar variables requeridas:

```bash
./scripts/check_env.sh
```

4. Inicializar base de datos (estructura actual):

```bash
./scripts/init_db.sh
```

5. Levantar panel:

```bash
python3 app.py
```

Panel: `http://localhost:5000/`

## Notas

- `estructura.sql` = snapshot actual del esquema.
- `estructura_pre_migrations.sql` = snapshot previo (referencia histórica).
- `migrations/` se conserva por trazabilidad hasta cerrar limpieza final.
