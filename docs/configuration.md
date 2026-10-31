# Configuration

All configuration is via environment variables. With Docker secrets, a file named
after the variable (lower-case) under `SECRETS_DIR` (default `/run/secrets`) is
read instead. `.env` is read by Docker Compose only; the application never loads
it implicitly. Create a development `.env` with `./scripts/init-dev-env.sh`
(random secrets, mode 600).

**Staging and production refuse to start** if any secret is shorter than 16
characters or looks like a placeholder, if `ALLOWED_HOSTS`/`CORS_ALLOWED_ORIGINS`
contain `*`, if `LOG_LEVEL=DEBUG`, or if `DEPLOYMENT_DISTRICT_NAME` is unset.

## Application (backend)

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | `development`, `test`, `staging`, `production` |
| `APP_VERSION` | `0.1.0` | Reported by `/system/info` |
| `LOG_LEVEL` | `INFO` | `DEBUG` rejected in staging/production |
| `LOG_FORMAT` | `json` | `json` or `console` |
| `EXPOSE_API_DOCS` | unset | Unset = docs on outside production, off in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,api,testserver` | Comma-separated `Host` header allow-list |
| `CORS_ALLOWED_ORIGINS` | empty | Normally empty: the UI is same-origin via nginx |
| `DEPLOYMENT_DISTRICT_NAME` | unset | Official header; required in staging/production |
| `DEPLOYMENT_DISTRICT_NAME_LOCAL` | unset | District name in local script |
| `DEPLOYMENT_STATE_NAME` / `_LOCAL` | unset | "Government of …" line |
| `HEALTH_CHECK_TIMEOUT_SECONDS` | `3.0` | Per readiness check |

## PostgreSQL

| Variable | Default | Description |
|---|---|---|
| `DATABASE_HOST` / `DATABASE_PORT` / `DATABASE_NAME` | `localhost` / `5432` / `dgimews` | |
| `DATABASE_USER` / `DATABASE_PASSWORD` | `dgimews_app` / — | Runtime role (DML only) |
| `DATABASE_MIGRATION_USER` / `DATABASE_MIGRATION_PASSWORD` | — | Schema owner, used by Alembic only |
| `DATABASE_APP_ROLE` | `dgimews_app` | Role that migrations grant DML to |
| `DATABASE_SSLMODE` | `prefer` | Use `verify-full` when the DB is on another host |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` / `DATABASE_POOL_TIMEOUT_SECONDS` | `10` / `5` / `10` | |
| `DATABASE_STATEMENT_TIMEOUT_MS` | `30000` | Per-connection statement timeout |

## Redis / Celery

| Variable | Default | Description |
|---|---|---|
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` | `localhost` / `6379` / — | |
| `REDIS_CACHE_DB` / `REDIS_BROKER_DB` / `REDIS_RESULT_DB` | `0` / `1` / `2` | Separate logical DBs |

## Compose-only variables (`.env`)

| Variable | Description |
|---|---|
| `POSTGRES_SUPERUSER_PASSWORD` | Superuser for first-time init only; never given to app containers |
| `DATABASE_APP_USER` / `DATABASE_APP_PASSWORD` | Mapped to `DATABASE_USER` / `DATABASE_PASSWORD` |
| `WEB_BIND_ADDRESS` / `WEB_PORT` | Published nginx address (default `127.0.0.1:8080`) |
| `DEV_DB_PORT` / `DEV_REDIS_PORT` / `DEV_API_PORT` | Dev override ports on 127.0.0.1 (55432 / 56379 / 58000) |
| `BUILD_NETWORK`, `BUILD_HTTPS_PROXY`, `BUILD_CA_BUNDLE` | Optional: building behind a TLS-inspecting proxy (CA is a BuildKit secret, not stored in layers) |

## Frontend

The frontend has **no runtime configuration and no secrets**. It calls `/api/v1`
on its own origin. `VITE_DEV_API_PROXY_TARGET` (default `http://127.0.0.1:58000`)
only affects the Vite development server proxy.
