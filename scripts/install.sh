#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
TEMPLATE_FILE="${PROJECT_ROOT}/.env.example"
ENV_FILE="${PROJECT_ROOT}/.env"
INIT_DB_SCRIPT="${PROJECT_ROOT}/scripts/init_db.sh"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"
VENV_DIR="${PROJECT_ROOT}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
DRY_RUN=0
FORCE=0

usage() {
  cat <<'EOF'
Uso: scripts/install.sh [--dry-run] [--force]

Instala dependencias del sistema (Ubuntu/Debian), prepara .venv con Python 3.11,
instala requirements.txt, descarga es_core_news_md, configura .env desde
.env.example y luego inicializa PostgreSQL.

Opciones:
  --dry-run  No hace cambios: valida archivos y muestra qué haría.
             Omite apt, .venv, pip, modelo spaCy, .env e init_db.
  --force    No pide confirmación si .env ya existe.
  --help     Muestra esta ayuda.
EOF
}

fail() {
  echo "❌ $*" >&2
  exit 1
}

print_blank_line() {
  echo
}

print_header() {
  print_blank_line
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "$1"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

print_subtle() {
  echo "   $*"
}

info() {
  echo "➡️  $*"
}

success() {
  echo "✅ $*"
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

validate_runtime_user() {
  if [[ "$EUID" -eq 0 ]]; then
    fail "No ejecutes este instalador como root. Corrélo con tu usuario normal para evitar archivos del proyecto con permisos de root; el script va a usar sudo solo para apt-get cuando haga falta."
  fi
}

run_as_root() {
  command_exists sudo || fail "Se necesita sudo para instalar paquetes del sistema. Instalá sudo o prepará manualmente las dependencias antes de correr este instalador."
  sudo "$@"
}

apt_package_installed() {
  local package=$1
  dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q "install ok installed"
}

validate_system_commands() {
  command_exists python3.11 || fail "No se encontró 'python3.11' después de instalar dependencias."
  python3.11 -m venv --help >/dev/null 2>&1 || fail "Python 3.11 está presente, pero falta soporte de venv ('python3.11-venv')."
  python3.11 -m pip --version >/dev/null 2>&1 || fail "Python 3.11 está presente, pero falta soporte de pip."
  command_exists psql || fail "No se encontró 'psql' después de instalar dependencias."
  command_exists createdb || fail "No se encontró 'createdb' después de instalar dependencias."
}

ensure_system_dependencies() {
  local missing_packages=()

  if ! command_exists apt-get; then
    fail "Este instalador soporta Ubuntu/Debian y requiere 'apt-get'."
  fi

  if ! command_exists python3.11 || ! python3.11 -m venv --help >/dev/null 2>&1; then
    missing_packages+=(python3.11 python3.11-venv)
  fi

  if ! python3.11 -m pip --version >/dev/null 2>&1; then
    missing_packages+=(python3-pip)
  fi

  if ! command_exists psql || ! command_exists createdb; then
    missing_packages+=(postgresql-client)
  fi

  if [[ ${#missing_packages[@]} -eq 0 ]]; then
    info "Dependencias del sistema ya disponibles."
    validate_system_commands
    return 0
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Dry run activo: instalaría paquetes del sistema con apt-get: ${missing_packages[*]}"
    return 0
  fi

  info "Instalando dependencias del sistema con apt-get: ${missing_packages[*]}"
  run_as_root apt-get update || fail "Falló 'apt-get update'. Revisá conectividad, repositorios y permisos."
  run_as_root apt-get install -y "${missing_packages[@]}" || fail "Falló la instalación de paquetes con apt-get: ${missing_packages[*]}"

  validate_system_commands
  success "Dependencias del sistema listas."
}

ensure_virtualenv() {
  local recreate_venv=0
  local backup_venv="${VENV_DIR}.backup.$(date +%Y%m%d%H%M%S)"

  if [[ -e "$VENV_DIR" && ! -d "$VENV_DIR" ]]; then
    fail "${VENV_DIR} existe pero no es un directorio. Revisalo manualmente antes de continuar."
  fi

  if [[ -d "$VENV_DIR" ]]; then
    if [[ ! -f "${VENV_DIR}/pyvenv.cfg" ]]; then
      fail "${VENV_DIR} existe pero no parece ser un virtualenv válido. No se toca automáticamente por seguridad."
    fi

    if [[ ! -x "$VENV_PYTHON" ]]; then
      recreate_venv=1
    elif ! "$VENV_PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)' >/dev/null 2>&1; then
      recreate_venv=1
    fi
  fi

  if [[ "$recreate_venv" -eq 1 ]]; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      info "Dry run activo: recrearía ${VENV_DIR} con Python 3.11."
      return 0
    fi

    info "${VENV_DIR} existe pero no usa Python 3.11 correctamente. Se va a respaldar antes de recrearlo."
    mv "$VENV_DIR" "$backup_venv"
  fi

  if [[ -d "$VENV_DIR" ]]; then
    info "Reutilizando virtualenv existente en ${VENV_DIR}."
    return 0
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Dry run activo: crearía ${VENV_DIR} con python3.11 -m venv."
    return 0
  fi

  info "Creando virtualenv en ${VENV_DIR} con Python 3.11"
  if ! python3.11 -m venv "$VENV_DIR"; then
    if [[ -d "$backup_venv" && ! -d "$VENV_DIR" ]]; then
      mv "$backup_venv" "$VENV_DIR"
      info "Se restauró el virtualenv anterior después del fallo."
    fi
    fail "No se pudo crear ${VENV_DIR} con Python 3.11."
  fi

  if [[ -d "$backup_venv" ]]; then
    rm -rf "$backup_venv"
  fi
  success "Virtualenv listo en ${VENV_DIR}."
}

install_python_dependencies() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Dry run activo: instalaría requirements.txt en ${VENV_DIR}."
    return 0
  fi

  [[ -x "$VENV_PYTHON" ]] || fail "No se encontró ${VENV_PYTHON}. Falló la creación del virtualenv."

  info "Actualizando pip dentro del virtualenv"
  "$VENV_PYTHON" -m pip install --upgrade pip || fail "Falló la actualización de pip en ${VENV_DIR}."

  info "Instalando dependencias Python desde requirements.txt"
  "$VENV_PYTHON" -m pip install -r "$REQUIREMENTS_FILE" || fail "Falló la instalación de dependencias Python."
  success "Dependencias Python instaladas."
}

ensure_spacy_model() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Dry run activo: descargaría el modelo spaCy es_core_news_md."
    return 0
  fi

  [[ -x "$VENV_PYTHON" ]] || fail "No se encontró ${VENV_PYTHON} para instalar el modelo spaCy."

  if "$VENV_PYTHON" -c 'import importlib.util, sys; raise SystemExit(0 if importlib.util.find_spec("es_core_news_md") else 1)' >/dev/null 2>&1; then
    info "El modelo spaCy es_core_news_md ya está instalado."
    return 0
  fi

  info "Descargando modelo spaCy es_core_news_md"
  "$VENV_PYTHON" -m spacy download es_core_news_md || fail "Falló la descarga del modelo spaCy es_core_news_md."
  success "Modelo spaCy instalado."
}

read_env_value() {
  local file=$1
  local key=$2
  local line

  [[ -f "$file" ]] || return 0

  line=$(grep -m1 "^${key}=" "$file" 2>/dev/null || true)
  [[ -n "$line" ]] || return 0
  printf '%s' "${line#*=}"
}

prompt_text() {
  local key=$1
  local label=$2
  local help_text=$3
  local default=$4
  local answer

  echo
  echo "• ${label}"
  [[ -n "$help_text" ]] && print_subtle "$help_text"
  read -r -p "  Valor [${default}]: " answer
  PROMPT_VALUE=${answer:-$default}
}

prompt_secret() {
  local key=$1
  local label=$2
  local help_text=$3
  local default=$4
  local answer
  local masked_default=""

  if [[ -n "$default" ]]; then
    masked_default="oculto; Enter para conservarlo"
  else
    masked_default="sin valor por defecto"
  fi

  echo
  echo "• ${label}"
  [[ -n "$help_text" ]] && print_subtle "$help_text"
  read -r -s -p "  Valor (${masked_default}): " answer
  print_blank_line
  PROMPT_VALUE=${answer:-$default}
}

confirm_overwrite() {
  local answer

  [[ ! -f "$ENV_FILE" ]] && return 0
  [[ "$FORCE" -eq 1 ]] && return 0

  read -r -p ".env ya existe. ¿Querés regenerarlo y guardar un backup antes? [y/N]: " answer
  case "$answer" in
    y|Y|yes|YES|si|SI|s|S) return 0 ;;
    *) fail "Instalación cancelada para no sobrescribir .env." ;;
  esac
}

backup_env_if_needed() {
  local backup_file

  [[ -f "$ENV_FILE" ]] || return 0

  backup_file="${ENV_FILE}.backup.$(date +%Y%m%d%H%M%S)"
  cp "$ENV_FILE" "$backup_file"
  info "Backup de .env creado en ${backup_file}"
}

validate_prerequisites() {
  [[ -f "$TEMPLATE_FILE" ]] || fail "Falta .env.example en ${PROJECT_ROOT}."
  [[ -f "$INIT_DB_SCRIPT" ]] || fail "Falta scripts/init_db.sh."
  [[ -f "$REQUIREMENTS_FILE" ]] || fail "Falta requirements.txt en ${PROJECT_ROOT}."
  [[ -f "${PROJECT_ROOT}/estructura.sql" ]] || fail "Falta estructura.sql en ${PROJECT_ROOT}."
}

merge_env_file() {
  local output_file=$1
  local line
  local key

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)= ]]; then
      key=${BASH_REMATCH[1]}
      case "$key" in
        DB_HOST) printf 'DB_HOST=%s\n' "$DB_HOST_VALUE" >>"$output_file" ;;
        DB_PORT) printf 'DB_PORT=%s\n' "$DB_PORT_VALUE" >>"$output_file" ;;
        DB_NAME) printf 'DB_NAME=%s\n' "$DB_NAME_VALUE" >>"$output_file" ;;
        DB_USER) printf 'DB_USER=%s\n' "$DB_USER_VALUE" >>"$output_file" ;;
        DB_PASSWORD) printf 'DB_PASSWORD=%s\n' "$DB_PASSWORD_VALUE" >>"$output_file" ;;
        OPENROUTER_API_KEY) printf 'OPENROUTER_API_KEY=%s\n' "$OPENROUTER_API_KEY_VALUE" >>"$output_file" ;;
        WP_URL) printf 'WP_URL=%s\n' "$WP_URL_VALUE" >>"$output_file" ;;
        WP_USERNAME) printf 'WP_USERNAME=%s\n' "$WP_USERNAME_VALUE" >>"$output_file" ;;
        WP_APP_PASSWORD) printf 'WP_APP_PASSWORD=%s\n' "$WP_APP_PASSWORD_VALUE" >>"$output_file" ;;
        OLLAMA_URL) printf 'OLLAMA_URL=%s\n' "$OLLAMA_URL_VALUE" >>"$output_file" ;;
        EMBEDDING_MODEL) printf 'EMBEDDING_MODEL=%s\n' "$EMBEDDING_MODEL_VALUE" >>"$output_file" ;;
        *) printf '%s\n' "$line" >>"$output_file" ;;
      esac
    else
      printf '%s\n' "$line" >>"$output_file"
    fi
  done <"$TEMPLATE_FILE"
}

write_env_file() {
  local temp_file

  temp_file=$(mktemp "${PROJECT_ROOT}/.env.tmp.XXXXXX")
  trap "rm -f -- '$temp_file'" EXIT

  merge_env_file "$temp_file"
  mv "$temp_file" "$ENV_FILE"
  trap - EXIT

  success ".env generado desde .env.example"
}

prepare_env_file() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Dry run activo: pediría variables y generaría ${ENV_FILE} desde ${TEMPLATE_FILE}."
    return 0
  fi

  local current_db_host current_db_port current_db_name current_db_user current_db_password
  local current_openrouter_key current_wp_url current_wp_username current_wp_app_password
  local current_ollama_url current_embedding_model

  current_db_host=$(read_env_value "$ENV_FILE" "DB_HOST")
  current_db_port=$(read_env_value "$ENV_FILE" "DB_PORT")
  current_db_name=$(read_env_value "$ENV_FILE" "DB_NAME")
  current_db_user=$(read_env_value "$ENV_FILE" "DB_USER")
  current_db_password=$(read_env_value "$ENV_FILE" "DB_PASSWORD")
  current_openrouter_key=$(read_env_value "$ENV_FILE" "OPENROUTER_API_KEY")
  current_wp_url=$(read_env_value "$ENV_FILE" "WP_URL")
  current_wp_username=$(read_env_value "$ENV_FILE" "WP_USERNAME")
  current_wp_app_password=$(read_env_value "$ENV_FILE" "WP_APP_PASSWORD")
  current_ollama_url=$(read_env_value "$ENV_FILE" "OLLAMA_URL")
  current_embedding_model=$(read_env_value "$ENV_FILE" "EMBEDDING_MODEL")

  print_header "📝 Configuración del archivo .env"
  print_subtle "Si ya existe un valor, podés presionar Enter para conservarlo."

  prompt_text "DB_HOST" "DB_HOST" "Host de PostgreSQL (por ejemplo: localhost o el nombre del servicio)." "${current_db_host:-$(read_env_value "$TEMPLATE_FILE" "DB_HOST")}"; DB_HOST_VALUE=$PROMPT_VALUE
  prompt_text "DB_PORT" "DB_PORT" "Puerto de PostgreSQL; normalmente 5432." "${current_db_port:-$(read_env_value "$TEMPLATE_FILE" "DB_PORT")}"; DB_PORT_VALUE=$PROMPT_VALUE
  prompt_text "DB_NAME" "DB_NAME" "Nombre de la base de datos que va a usar la app." "${current_db_name:-$(read_env_value "$TEMPLATE_FILE" "DB_NAME")}"; DB_NAME_VALUE=$PROMPT_VALUE
  prompt_text "DB_USER" "DB_USER" "Usuario con permisos para conectarse y crear la base si hace falta." "${current_db_user:-$(read_env_value "$TEMPLATE_FILE" "DB_USER")}"; DB_USER_VALUE=$PROMPT_VALUE
  prompt_secret "DB_PASSWORD" "DB_PASSWORD" "Contraseña del usuario de PostgreSQL indicado arriba." "${current_db_password:-$(read_env_value "$TEMPLATE_FILE" "DB_PASSWORD")}"; DB_PASSWORD_VALUE=$PROMPT_VALUE
  prompt_secret "OPENROUTER_API_KEY" "OPENROUTER_API_KEY" "Clave de OpenRouter para habilitar las integraciones del proyecto." "${current_openrouter_key:-$(read_env_value "$TEMPLATE_FILE" "OPENROUTER_API_KEY")}"; OPENROUTER_API_KEY_VALUE=$PROMPT_VALUE
  prompt_text "WP_URL" "WP_URL" "URL base de tu sitio WordPress, incluyendo https://." "${current_wp_url:-$(read_env_value "$TEMPLATE_FILE" "WP_URL")}"; WP_URL_VALUE=$PROMPT_VALUE
  prompt_text "WP_USERNAME" "WP_USERNAME" "Usuario de WordPress con permisos para la integración." "${current_wp_username:-$(read_env_value "$TEMPLATE_FILE" "WP_USERNAME")}"; WP_USERNAME_VALUE=$PROMPT_VALUE
  prompt_secret "WP_APP_PASSWORD" "WP_APP_PASSWORD" "Contraseña de aplicación de WordPress. Se crea en Usuarios > Perfil > Application Passwords y se pega tal como la muestra WordPress." "${current_wp_app_password:-$(read_env_value "$TEMPLATE_FILE" "WP_APP_PASSWORD")}"; WP_APP_PASSWORD_VALUE=$PROMPT_VALUE
  prompt_text "OLLAMA_URL" "OLLAMA_URL" "URL del servicio de Ollama si lo usás local o remotamente." "${current_ollama_url:-$(read_env_value "$TEMPLATE_FILE" "OLLAMA_URL")}"; OLLAMA_URL_VALUE=$PROMPT_VALUE
  prompt_text "EMBEDDING_MODEL" "EMBEDDING_MODEL" "Nombre del modelo de embeddings configurado para el proyecto." "${current_embedding_model:-$(read_env_value "$TEMPLATE_FILE" "EMBEDDING_MODEL")}"; EMBEDDING_MODEL_VALUE=$PROMPT_VALUE

  confirm_overwrite
  backup_env_if_needed
  write_env_file
}

run_db_init() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Dry run activo: se omite la inicialización de la base."
    return 0
  fi

  print_header "🗄️ Inicialización de base de datos"
  info "Ejecutando scripts/init_db.sh"
  if ! (
    cd "$PROJECT_ROOT"
    bash "$INIT_DB_SCRIPT"
  ); then
    fail "Falló la inicialización de la base de datos. Revisá la conexión y tus credenciales."
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run)
        DRY_RUN=1
        ;;
      --force)
        FORCE=1
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        fail "Opción no reconocida: $1"
        ;;
    esac
    shift
  done
}

main() {
  parse_args "$@"
  validate_runtime_user
  validate_prerequisites

  print_header "🛠️ Instalador del proyecto TRH"
  print_subtle "Este asistente va a:"
  print_subtle "1) preparar dependencias del sistema en Ubuntu/Debian"
  print_subtle "2) crear o reutilizar .venv con Python 3.11"
  print_subtle "3) instalar requirements.txt y el modelo de spaCy"
  print_subtle "4) generar .env a partir de .env.example"
  print_subtle "5) delegar la inicialización de PostgreSQL a scripts/init_db.sh"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    print_blank_line
    echo "🧪 Modo dry-run activado"
    print_subtle "Solo se validan archivos y se muestran acciones planeadas."
    print_subtle "No se modifican paquetes, .venv, .env ni la base de datos."
  fi

  print_blank_line
  echo "ℹ️  Sobre WP_APP_PASSWORD"
  print_subtle "Es una contraseña de aplicación de WordPress, distinta de tu clave habitual."
  print_subtle "La obtenés en WordPress desde Usuarios > Perfil > Application Passwords."
  print_subtle "Creá una nueva, copiá el valor generado y pegalo cuando el instalador lo pida."

  print_header "🔧 Preparando entorno"
  ensure_system_dependencies
  ensure_virtualenv
  install_python_dependencies
  ensure_spacy_model
  prepare_env_file
  run_db_init

  success "Instalación finalizada."
}

main "$@"
