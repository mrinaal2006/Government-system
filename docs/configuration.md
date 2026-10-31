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
| `CLIENT_IP_HEADER` | unset | Header with the real client IP set by a trusted edge (`x-real-ip` on Vercel). Leave unset behind nginx |
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
| `REDIS_TLS` | `false` | Use `rediss://` with certificate verification (managed Redis) |

## Authentication and sessions

| Variable | Default | Description |
|---|---|---|
| `SESSION_COOKIE_SECURE` | unset | Unset = Secure everywhere except development/test; `false` is refused in production |
| `SESSION_ABSOLUTE_TIMEOUT_MINUTES` / `SESSION_IDLE_TIMEOUT_MINUTES` | `720` / `30` | |
| `LOGIN_RATE_LIMIT_PER_MINUTE` | `10` | Per IP and per username |
| `LOCKOUT_THRESHOLD` / `LOCKOUT_MINUTES` | `5` / `15` | |
| `PASSWORD_MIN_LENGTH` | `12` | |
| `MFA_REQUIRED_ROLES` | `super_admin,district_magistrate,additional_district_magistrate,auditor` | |
| `MFA_ISSUER` | `DG-IMEWS` | Label shown in authenticator apps |
| `OFFICER_SIGNUP_ENABLED` | `true` | Officials may create an account on the sign-up page and are signed in at once: the first account becomes the Super Administrator (while no active one exists); every later account is a Data Entry Operator that sees only the grievances it registered. `false` hides the link and refuses sign-ups |
| `CITIZEN_PORTAL_ENABLED` | unset | Citizen self-service portal. Unset = on in development/test, off elsewhere. Production refuses `true` while `CITIZEN_OTP_PROVIDER=console` |
| `CITIZEN_OTP_PROVIDER` | `console` | How one-time codes reach citizens. `console` (the only provider implemented) writes the code to the API log and, in development/test only, returns it to the browser. A real SMS gateway (for example the government SMS service through NIC) must be integrated before the portal is used in production |

## Data protection, storage and scanning

| Variable | Description |
|---|---|
| `DATA_ENCRYPTION_KEY` | Encrypts complainant data and MFA secrets. Back up separately; loss is unrecoverable |
| `DATA_ENCRYPTION_PREVIOUS_KEYS` | Comma-separated old keys kept readable during rotation |
| `LOOKUP_HMAC_KEY` | Keyed hash for matching mobile numbers without decrypting |
| `STORAGE_ENDPOINT` / `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY` / `STORAGE_BUCKET` / `STORAGE_REGION` / `STORAGE_SECURE` | S3-compatible private storage |
| `UPLOAD_MAX_BYTES` | Attachment size limit (default 10 MB) |
| `MALWARE_SCANNER` | `clamav` (required in production) or `none` (development) |
| `CLAMAV_HOST` / `CLAMAV_PORT` | clamd address |
| `MALWARE_SCAN_MODE` | `inline` (API scans before accepting; default) or `deferred` (worker scans after upload; file unavailable until clean). Use `deferred` on Vercel |
| `GRIEVANCE_REFERENCE_PREFIX` | Reference format `PREFIX/YEAR/NNNNNN` |
| `MAP_TILE_URL` | Optional basemap tile URL; leave unset to draw boundaries only (no third-party requests). If set, also add the tile origin to `img-src` in `infra/nginx/security-headers.conf` |
| `METRICS_TOKEN` | Bearer token for `/api/v1/system/metrics` |
| `GARAGE_RPC_SECRET` / `GARAGE_ADMIN_TOKEN` | Garage storage node secrets (compose only) |

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
