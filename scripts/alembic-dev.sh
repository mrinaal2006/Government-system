#!/usr/bin/env bash
# Run Alembic from the host against the development database (or *_test with --test).
#   ./scripts/alembic-dev.sh [--test] upgrade head
set -euo pipefail
cd "$(dirname "$0")/../backend"
db_suffix=""
if [ "${1:-}" = "--test" ]; then db_suffix="_test"; shift; fi
set -a; . ../.env; set +a
export DATABASE_HOST=127.0.0.1 DATABASE_PORT="${DEV_DB_PORT:-55432}"
export DATABASE_NAME="${DATABASE_NAME:-dgimews}${db_suffix}"
export DATABASE_USER="$DATABASE_APP_USER" DATABASE_PASSWORD="$DATABASE_APP_PASSWORD"
export DATABASE_APP_ROLE="$DATABASE_APP_USER"
exec .venv/bin/alembic "$@"
