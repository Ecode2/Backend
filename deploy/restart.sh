#!/usr/bin/env bash
# ===========================================================================
# Health-checked restart. Self-heals a missing Postgres, refuses to restart the
# app on a bad nginx config, and prints a status summary. Safe to re-run.
# ===========================================================================
set -uo pipefail

ENV_FILE="/opt/bookverse/.env"
APP_DIR="/opt/bookverse/app"
REQUIRED_SERVICES=(postgresql redis-server minio nginx bookverse)

log()  { echo -e "\033[1;34m[restart]\033[0m $*"; }
err()  { echo -e "\033[1;31m[error]\033[0m $*" >&2; }

[ "$(id -u)" -eq 0 ] || { err "Run as root (sudo)."; exit 1; }
[ -f "${ENV_FILE}" ] && { set -a; source "${ENV_FILE}"; set +a; }

# --- 1. Postgres installed? -------------------------------------------------
if ! command -v psql >/dev/null 2>&1 && ! dpkg -s postgresql >/dev/null 2>&1; then
  log "Postgres missing — installing..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y && apt-get install -y postgresql postgresql-contrib
  systemctl enable --now postgresql
  PG_DB="${POSTGRES_DB:-bookverse}"; PG_USER="${POSTGRES_USER:-bookverse}"; PG_PASS="${POSTGRES_PASSWORD:-bookverse}"
  sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${PG_USER}'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE ROLE ${PG_USER} LOGIN PASSWORD '${PG_PASS}';"
  sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${PG_DB}'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE ${PG_DB} OWNER ${PG_USER};"
fi

# --- 2/3. Postgres + Redis + MinIO active? ----------------------------------
for svc in postgresql redis-server minio; do
  if ! systemctl is-active --quiet "${svc}"; then
    log "${svc} inactive — starting..."
    systemctl start "${svc}" || err "could not start ${svc}"
  fi
done

# --- 4. Validate nginx BEFORE touching the app ------------------------------
if ! nginx -t 2>/tmp/nginx-test.log; then
  err "nginx config invalid — aborting (app left running):"
  cat /tmp/nginx-test.log >&2
  exit 2
fi
systemctl reload nginx
log "nginx config valid; reloaded."

# --- 5. Restart the app -----------------------------------------------------
log "Restarting bookverse.service..."
systemctl restart bookverse.service

# --- 6. Summary -------------------------------------------------------------
echo
printf "%-16s %-10s\n" "SERVICE" "STATUS"
printf "%-16s %-10s\n" "-------" "------"
exit_code=0
for svc in "${REQUIRED_SERVICES[@]}"; do
  if systemctl is-active --quiet "${svc}"; then
    printf "%-16s \033[1;32m%-10s\033[0m\n" "${svc}" "active"
  else
    printf "%-16s \033[1;31m%-10s\033[0m\n" "${svc}" "inactive"
    exit_code=1
  fi
done
echo
[ "${exit_code}" -eq 0 ] && log "All services healthy." || err "One or more services are down."
exit "${exit_code}"
