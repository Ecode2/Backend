#!/usr/bin/env bash
# ===========================================================================
# Bookverse VPS provisioning (Debian 12 / Ubuntu). Idempotent: safe to re-run.
# Provisions Postgres, Redis, MinIO, Nginx, the Python venv, systemd units and
# the Nginx site. Never destructively recreates an existing database.
# ===========================================================================
set -euo pipefail

APP_USER="bookverse"
APP_HOME="/opt/bookverse"
APP_DIR="${APP_HOME}/app"            # repository checkout lives here
VENV_DIR="${APP_HOME}/venv"
ENV_FILE="${APP_HOME}/.env"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # Backend/
MINIO_USER="minio-user"
MINIO_DATA="/var/lib/minio"

log()  { echo -e "\033[1;34m[install]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }

require_root() { [ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)."; exit 1; }; }
require_root

# --- 1. System packages ----------------------------------------------------
log "Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
  postgresql postgresql-contrib redis-server nginx \
  python3-venv python3-dev build-essential libpq-dev git curl \
  certbot python3-certbot-nginx \
  libxml2-dev libxslt1-dev zlib1g-dev libjpeg-dev

# --- 2. App user + directories ---------------------------------------------
if ! id "${APP_USER}" >/dev/null 2>&1; then
  log "Creating system user ${APP_USER}"
  adduser --system --group --home "${APP_HOME}" "${APP_USER}"
fi
mkdir -p "${APP_HOME}"
# Sync the repo into APP_DIR (rsync if available; else copy).
mkdir -p "${APP_DIR}"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude venv --exclude db.sqlite3 "${REPO_DIR}/" "${APP_DIR}/"
else
  cp -r "${REPO_DIR}/." "${APP_DIR}/"
fi
chown -R "${APP_USER}:${APP_USER}" "${APP_HOME}"

# --- 3. .env ----------------------------------------------------------------
if [ ! -f "${ENV_FILE}" ]; then
  log "Seeding ${ENV_FILE} from .env.example — FILL THIS IN before continuing."
  cp "${APP_DIR}/.env.example" "${ENV_FILE}"
  chown "${APP_USER}:${APP_USER}" "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
  warn "Edit ${ENV_FILE} (secrets, DB password, MinIO creds) then re-run."
  # Stop here on the very first run. Continuing would provision Postgres and
  # MinIO with the placeholder credentials from .env.example; because the rest
  # of the script is idempotent it would then *skip* recreating them, leaving
  # the real passwords in .env permanently out of sync with the services.
  exit 1
fi
# shellcheck disable=SC1090
set -a; source "${ENV_FILE}"; set +a

# --- 4. Services: enable + start -------------------------------------------
log "Enabling Postgres, Redis, Nginx..."
systemctl enable --now postgresql
systemctl enable --now redis-server
systemctl enable --now nginx

# --- 5. Postgres role + database --------------------------------------------
PG_DB="${POSTGRES_DB:-bookverse}"
PG_USER="${POSTGRES_USER:-bookverse}"
PG_PASS="${POSTGRES_PASSWORD:-bookverse}"
PG_PASS_SQL="${PG_PASS//\'/\'\'}"   # escape single quotes for the SQL literal

# Django connects via DATABASE_URL but the role is provisioned from
# POSTGRES_PASSWORD; if the two disagree every connection fails with
# "password authentication failed" no matter how often you re-run this.
if [[ "${DATABASE_URL:-}" =~ ^[a-z+]+://[^:/]+:([^@]*)@ ]]; then
  if [ "${BASH_REMATCH[1]}" != "${PG_PASS}" ]; then
    warn "DATABASE_URL's password does not match POSTGRES_PASSWORD in ${ENV_FILE}."
    warn "Django uses DATABASE_URL; this role is provisioned from POSTGRES_PASSWORD."
    warn "Make them identical, then re-run."
  fi
fi

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${PG_USER}'" | grep -q 1; then
  log "Creating Postgres role ${PG_USER}"
  sudo -u postgres psql -c "CREATE ROLE ${PG_USER} LOGIN PASSWORD '${PG_PASS_SQL}';"
else
  # Reconcile on every run. The role usually outlives ${ENV_FILE} (a previous
  # run may have created it from the .env.example placeholders), and since we
  # skip creation when it exists the two would otherwise never converge.
  log "Syncing Postgres role ${PG_USER} password with ${ENV_FILE}"
  sudo -u postgres psql -c "ALTER ROLE ${PG_USER} WITH LOGIN PASSWORD '${PG_PASS_SQL}';"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${PG_DB}'" | grep -q 1; then
  log "Creating Postgres database ${PG_DB}"
  sudo -u postgres psql -c "CREATE DATABASE ${PG_DB} OWNER ${PG_USER};"
fi

# --- 6. MinIO ---------------------------------------------------------------
if [ ! -x /usr/local/bin/minio ]; then
  log "Installing MinIO server + client..."
  ARCH="$(dpkg --print-architecture)"; [ "${ARCH}" = "armhf" ] && ARCH="arm"
  curl -fsSL "https://dl.min.io/server/minio/release/linux-${ARCH}/minio" -o /usr/local/bin/minio
  curl -fsSL "https://dl.min.io/client/mc/release/linux-${ARCH}/mc" -o /usr/local/bin/mc
  chmod +x /usr/local/bin/minio /usr/local/bin/mc
fi
id "${MINIO_USER}" >/dev/null 2>&1 || adduser --system --group --no-create-home "${MINIO_USER}"
mkdir -p "${MINIO_DATA}"
chown -R "${MINIO_USER}:${MINIO_USER}" "${MINIO_DATA}"
# Regenerated every run (same reason as the Postgres role above): .env is the
# single source of truth, so editing credentials there must actually reach the
# running service instead of being ignored because the file already exists.
MINIO_TMP="$(mktemp)"
cat > "${MINIO_TMP}" <<EOF
MINIO_VOLUMES="${MINIO_DATA}"
MINIO_ADDRESS=":9000"
MINIO_CONSOLE_ADDRESS=":9001"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-bookverse}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-changemechangeme}"
EOF
MINIO_CREDS_CHANGED=0
if ! cmp -s "${MINIO_TMP}" /etc/default/minio; then
  log "Writing /etc/default/minio from ${ENV_FILE}"
  install -m 600 "${MINIO_TMP}" /etc/default/minio
  MINIO_CREDS_CHANGED=1
fi
rm -f "${MINIO_TMP}"

install -m 644 "${APP_DIR}/deploy/systemd/minio.service" /etc/systemd/system/minio.service
systemctl daemon-reload
systemctl enable --now minio
if [ "${MINIO_CREDS_CHANGED}" -eq 1 ]; then
  log "MinIO config changed — restarting"
  systemctl restart minio
fi
sleep 3
# Create the bucket via mc (idempotent).
mc alias set bvlocal "http://127.0.0.1:9000" "${MINIO_ROOT_USER:-bookverse}" "${MINIO_ROOT_PASSWORD:-changemechangeme}" >/dev/null 2>&1 || true
mc mb --ignore-existing "bvlocal/${AWS_STORAGE_BUCKET_NAME:-bookverse}" >/dev/null 2>&1 || true

# --- 7. Python venv + deps --------------------------------------------------
# Django 5.2 LTS supports Python 3.10-3.14, so the distro python3 is fine on
# both Ubuntu 24.04 (3.12) and 26.04 (3.14). Every pinned dependency ships a
# prebuilt wheel for those versions -- if pip starts compiling from source,
# a pin has drifted ahead of (or behind) its wheel coverage.
log "Using $(python3 --version) at $(command -v python3)"
if [ ! -d "${VENV_DIR}" ]; then
  log "Creating venv at ${VENV_DIR}"
  sudo -u "${APP_USER}" python3 -m venv "${VENV_DIR}"
fi
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --upgrade pip
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --prefer-binary -r "${APP_DIR}/requirements.txt"

# --- 8. Migrate + collectstatic --------------------------------------------
log "Running migrations and collectstatic..."
cd "${APP_DIR}"
sudo -u "${APP_USER}" --preserve-env=PATH bash -c "set -a; source ${ENV_FILE}; set +a; ${VENV_DIR}/bin/python manage.py migrate --noinput"
sudo -u "${APP_USER}" --preserve-env=PATH bash -c "set -a; source ${ENV_FILE}; set +a; ${VENV_DIR}/bin/python manage.py collectstatic --noinput"

# --- 9. systemd unit for the app -------------------------------------------
log "Installing bookverse.service..."
install -m 644 "${APP_DIR}/deploy/systemd/bookverse.service" /etc/systemd/system/bookverse.service
systemctl daemon-reload
systemctl enable --now bookverse.service

# --- 10. Nginx site ---------------------------------------------------------
log "Installing Nginx site..."
install -m 644 "${APP_DIR}/deploy/nginx/bookverse.conf" /etc/nginx/sites-available/bookverse.conf
ln -sf /etc/nginx/sites-available/bookverse.conf /etc/nginx/sites-enabled/bookverse.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# --- Next steps -------------------------------------------------------------
cat <<EOF

\033[1;32m[install] Done.\033[0m Next steps:
  1. Edit ${ENV_FILE} with real secrets, then: sudo systemctl restart bookverse
  2. TLS:   sudo certbot --nginx -d bookverse.api.ecode2.com
  3. TTS (default provider is NVIDIA): get a free API key from
       build.nvidia.com ("Get API Key" on any model page) and set
       NVIDIA_API_KEY in ${ENV_FILE}. To use a different NVIDIA TTS model,
       copy that model's "function-id" into NVIDIA_TTS_FUNCTION_ID and set
       TTS_DEFAULT_VOICE to one of its voices.
       (Or set TTS_PROVIDER=google/piper/dummy for the other backends.)
  4. Verify: sudo bash ${APP_DIR}/deploy/restart.sh
EOF
