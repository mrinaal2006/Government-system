# Deploying on Vercel (services)

`vercel.json` deploys two services as one project on one domain:

| Service | Root | Framework | Public path |
|---|---|---|---|
| `backend` | `backend/` | FastAPI (entrypoint `app/asgi.py`, ASGI `app`) | `/api/*` (routes are already under `/api/v1`) |
| `frontend` | `frontend/` | Vite (static SPA) | everything else |

**No service bindings** are configured: the services never call each other server-side.
The browser calls the API on the same origin at `/api/v1/...`, which the `/api/(.*)` rewrite
routes to `backend`. The backend's other dependencies are external systems, not Vercel services.

Security headers that nginx sets in the Docker deployment are set by `vercel.json` for UI
responses; the API sets its own (stricter) headers.

## Architecture (Option B)

```
 Browser ──HTTPS──► Vercel ── /api/* ──► backend (FastAPI functions)
                       └──── /*  ─────► frontend (static Vite build)
                                   │
       managed PostgreSQL+PostGIS ◄┼► managed Redis (TLS) ◄┼► S3-compatible storage
                                   │
                 Worker server (docker-compose.worker.yml)
                 ├─ worker  : imports, reports, AI suggestions, deferred malware scans
                 ├─ beat    : time-limit checks, alert evaluation, daily snapshots, sweeps
                 ├─ clamav  : on a private network, reachable only by the worker
                 └─ migrate : run once before each deploy
```

Vercel functions cannot run long-lived processes and cannot reach clamd privately, so:

* **Uploads are scanned after upload** (`MALWARE_SCAN_MODE=deferred`): the API stores the
  file as `pending`; the worker scans it with ClamAV. Pending files cannot be downloaded;
  infected files are deleted from storage, audited, and the uploader is notified. If the
  scanner is down, scans are retried with back-off and swept every 5 minutes.
* Everything queued (imports, reports, AI analysis) is processed by the worker server.

Verified locally: the worker stack ran in production mode against PostgreSQL, Redis and
storage; an uploaded file was `pending`, refused for download (403), scanned clean by real
ClamAV about 6 seconds later, and then downloaded byte-identical.

## External services

| Need | Suggested |
|---|---|
| PostgreSQL 16 **with PostGIS** | A managed service in an Indian region that supports PostGIS. Create the two roles and extensions once with the SQL in `infra/postgres/init/01-roles-and-extensions.sh` |
| Redis with TLS | Any managed Redis; set `REDIS_TLS=true` |
| S3-compatible private storage | For example a bucket in the Mumbai region; set `STORAGE_*` |
| Worker server | A small Linux VM (2 vCPU / 4 GB is enough to start) with Docker |

Confirm with the district IT cell / NIC which providers are approved for government data.

## Worker server setup

```bash
cp .env.worker.example .env.worker
```

Fill in `.env.worker` with the same database, Redis, storage and encryption-key values as the
Vercel project. Then run migrations once, and start the services:

```bash
docker compose -f docker-compose.worker.yml --env-file .env.worker --profile migrate run --rm migrate
```

```bash
docker compose -f docker-compose.worker.yml --env-file .env.worker up -d --build
```

Re-run the migrate command before every deploy that includes new migrations.

## Vercel environment variables (Project Settings → Environment Variables)

Everything in `docs/configuration.md` applies. Vercel-specific values:

* `APP_ENV=production`, `SESSION_COOKIE_SECURE=true`, `MALWARE_SCANNER=clamav`,
  `MALWARE_SCAN_MODE=deferred`, `REDIS_TLS=true`
* `ALLOWED_HOSTS=<your-domain>,<project>.vercel.app` (also used to accept the sign-in Origin)
* `CLIENT_IP_HEADER=x-real-ip` so rate limits, lockout and suspicious-login detection see the
  real client address (Vercel overwrites this header; do not set it behind other proxies)
* `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`,
  `DATABASE_SSLMODE=verify-full`, and a small pool (`DATABASE_POOL_SIZE=2`,
  `DATABASE_MAX_OVERFLOW=2`) because each function instance has its own pool
* `REDIS_*`, `STORAGE_*`, `DATA_ENCRYPTION_KEY`, `LOOKUP_HMAC_KEY`, `METRICS_TOKEN`,
  `DEPLOYMENT_*`, `GRIEVANCE_REFERENCE_PREFIX`: the same values as `.env.worker`
* `UPLOAD_MAX_BYTES=4000000`: Vercel functions accept request bodies up to 4.5 MB, below the
  default 10 MB attachment limit and the 20 MB import limit (large imports must be split)

## Local test

`vercel dev` runs both services with the same routing. It needs the external services above
(the Docker Compose stack's PostgreSQL, Redis and storage can be used in development).

## Not yet verified

This configuration has not been deployed to Vercel or run with `vercel dev` from the build
environment (no Vercel account was available). Check after the first deployment:
1. `/api/v1/health/ready` returns 200 (path prefix is preserved by the rewrite);
2. deep links such as `/grievances/<id>` load the app (SPA fallback for the static frontend);
3. sign-in works (Host/Origin seen by the function match `ALLOWED_HOSTS`).
