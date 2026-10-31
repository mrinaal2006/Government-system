#!/usr/bin/env bash
# Runs ONCE, as the PostgreSQL superuser, when the data volume is first initialised
# (docker-entrypoint-initdb.d). Re-running is safe: every statement is idempotent.
#
# Creates two least-privilege login roles:
#   DB_MIGRATOR_USER - owns the application database and schemas; used only by Alembic.
#   DB_APP_USER      - runtime role for API/workers; receives DML grants from migrations,
#                      cannot create, alter or drop objects.
# Installs extensions that require superuser: postgis, pgcrypto, pg_trgm, citext.
set -euo pipefail

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${DB_MIGRATOR_USER:?DB_MIGRATOR_USER is required}"
: "${DB_MIGRATOR_PASSWORD:?DB_MIGRATOR_PASSWORD is required}"
: "${DB_APP_USER:?DB_APP_USER is required}"
: "${DB_APP_PASSWORD:?DB_APP_PASSWORD is required}"
CREATE_TEST_DB="${DB_CREATE_TEST_DATABASE:-false}"

psql_super() {
  psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$POSTGRES_USER" "$@"
}

# Passwords are passed as psql variables and quoted by psql (:'var'), never
# interpolated into SQL text by the shell.
psql_super --dbname postgres \
  -v migrator="$DB_MIGRATOR_USER" -v migrator_pw="$DB_MIGRATOR_PASSWORD" \
  -v app="$DB_APP_USER" -v app_pw="$DB_APP_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :'migrator')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migrator') \gexec
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :'app')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app') \gexec
ALTER ROLE :"migrator" PASSWORD :'migrator_pw';
ALTER ROLE :"app" PASSWORD :'app_pw';
ALTER ROLE :"app" SET statement_timeout = '30s';
ALTER ROLE :"app" SET idle_in_transaction_session_timeout = '60s';
SQL

prepare_database() {
  local db="$1"
  psql_super --dbname postgres -v db="$db" -v migrator="$DB_MIGRATOR_USER" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER %I ENCODING ''UTF8'' TEMPLATE template0', :'db', :'migrator')
 WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db') \gexec
ALTER DATABASE :"db" OWNER TO :"migrator";
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
ALTER DATABASE :"db" SET timezone TO 'UTC';
SQL
  psql_super --dbname "$db" -v db="$db" -v migrator="$DB_MIGRATOR_USER" -v app="$DB_APP_USER" <<'SQL'
GRANT CONNECT, TEMPORARY ON DATABASE :"db" TO :"app";
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;
-- Nobody but the migrator may create objects in public (alembic_version lives there).
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO :"migrator";
GRANT USAGE ON SCHEMA public TO :"app";
GRANT SELECT ON public.spatial_ref_sys TO :"app";
SQL
  echo "Prepared database ${db}"
}

prepare_database "$POSTGRES_DB"
if [ "$CREATE_TEST_DB" = "true" ]; then
  prepare_database "${POSTGRES_DB}_test"
fi
