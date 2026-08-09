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
fi
# shellcheck disable=SC1090
set -a; source "${ENV_FILE}"; set +a

# --- 4. Services: enable + start -------------------------------------------
log "Enabling Postgres, Redis, Nginx..."
systemctl enable --now postgresql
systemctl enable --now redis-server
systemctl enable --now nginx

# --- 5. Postgres role + database (skip if present) -------------------------
PG_DB="${POSTGRES_DB:-bookverse}"
PG_USER="${POSTGRES_USER:-bookverse}"
PG_PASS="${POSTGRES_PASSWORD:-bookverse}"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${PG_USER}'" | grep -q 1; then
  log "Creating Postgres role ${PG_USER}"
  sudo -u postgres psql -c "CREATE ROLE ${PG_USER} LOGIN PASSWORD '${PG_PASS}';"
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
if [ ! -f /etc/default/minio ]; then
  cat > /etc/default/minio <<EOF
MINIO_VOLUMES="${MINIO_DATA}"
MINIO_ADDRESS=":9000"
MINIO_CONSOLE_ADDRESS=":9001"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-bookverse}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-changemechangeme}"
EOF
  chmod 600 /etc/default/minio
fi
install -m 644 "${APP_DIR}/deploy/systemd/minio.service" /etc/systemd/system/minio.service
systemctl daemon-reload
systemctl enable --now minio
sleep 3
# Create the bucket via mc (idempotent).
mc alias set bvlocal "http://127.0.0.1:9000" "${MINIO_ROOT_USER:-bookverse}" "${MINIO_ROOT_PASSWORD:-changemechangeme}" >/dev/null 2>&1 || true
mc mb --ignore-existing "bvlocal/${AWS_STORAGE_BUCKET_NAME:-bookverse}" >/dev/null 2>&1 || true

# --- 7. Python venv + deps --------------------------------------------------
if [ ! -d "${VENV_DIR}" ]; then
  log "Creating venv at ${VENV_DIR}"
  sudo -u "${APP_USER}" python3 -m venv "${VENV_DIR}"
fi
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --upgrade pip
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"

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
  3. Google TTS: create a service account with role
       "Cloud Text-to-Speech API User", enable the Text-to-Speech API,
       download the JSON key to /opt/bookverse/gcp-tts.json and set
       GOOGLE_APPLICATION_CREDENTIALS in ${ENV_FILE}.
       (Or set TTS_PROVIDER=piper for a fully local engine.)
  4. Verify: sudo bash ${APP_DIR}/deploy/restart.sh
EOF
