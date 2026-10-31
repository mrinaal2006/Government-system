#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh into the running stack.
#
#   BACKUP_PASSPHRASE=... ./scripts/restore.sh backups/dgimews-YYYYmmddTHHMMSSZ
#
# The target stack must use the same DATA_ENCRYPTION_KEY and LOOKUP_HMAC_KEY as the
# source, and its database roles must exist (created by the PostgreSQL init script).
# Application services are stopped during the restore and started afterwards.
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="${1:?usage: restore.sh <backup-dir>}"
: "${BACKUP_PASSPHRASE:?Set BACKUP_PASSPHRASE}"
COMPOSE=(docker compose ${COMPOSE_FILES:-})
set -a; . ./.env; set +a
DB="${DATABASE_NAME:-dgimews}"

(cd "$DIR" && sha256sum -c manifest.sha256)
dec() { openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass env:BACKUP_PASSPHRASE -in "$1"; }

# Whatever happens, bring the stack back up so the service is not left stopped.
trap '"${COMPOSE[@]}" up -d --no-build >/dev/null 2>&1 || true' EXIT

echo "Stopping application services..."
"${COMPOSE[@]}" stop api worker beat web >/dev/null
echo "Restoring database $DB..."
"${COMPOSE[@]}" exec -T db psql -v ON_ERROR_STOP=1 -U postgres -d postgres -v db="$DB" -v owner="${DATABASE_MIGRATION_USER:-dgimews_migrator}" <<'SQL'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'db' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS :"db";
CREATE DATABASE :"db" OWNER :"owner" ENCODING 'UTF8' TEMPLATE template0;
SQL
# Re-apply extensions and grants exactly as on first initialisation.
"${COMPOSE[@]}" exec -T db bash -c 'DB_CREATE_TEST_DATABASE=false bash /docker-entrypoint-initdb.d/01-roles-and-extensions.sh' >/dev/null
# Restore as superuser so extensions, object ownership (migration role) and privileges
# (runtime role) are recreated exactly as they were.
dec "$DIR/database.dump.enc" | "${COMPOSE[@]}" exec -T db pg_restore -U postgres -d "$DB" --exit-on-error
# Table privileges and default privileges are part of the dump and are restored with it.
echo "Starting services (migrations run first)..."
"${COMPOSE[@]}" up -d --no-build >/dev/null
for i in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T api python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live',timeout=2).status==200 else 1)" 2>/dev/null; then break; fi
  sleep 2
done
echo "Restoring object storage..."
dec "$DIR/objects.tar.enc" | "${COMPOSE[@]}" exec -T api python -m app.cli import-objects
echo "Restore complete. Verify: readiness, record counts and GET /api/v1/audit/verify."
