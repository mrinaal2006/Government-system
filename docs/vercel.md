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

## What Vercel does not provide (must exist outside Vercel)

| Need | Why | Options |
|---|---|---|
| PostgreSQL 16 **with PostGIS** | all data | managed Postgres with PostGIS enabled; run `infra/postgres/init/01-roles-and-extensions.sh` equivalents (roles, extensions) once |
| Database migrations | functions must not migrate on start | run `alembic upgrade head` with the migration role from CI or an operator machine before each deploy |
| Redis | sessions rate limits, Celery broker | managed Redis reachable over TLS |
| **Celery worker and beat** | AI analysis, imports, reports, SLA scans and alert evaluation run in the background; Vercel functions cannot host long-running workers | run `celery ... worker` and `celery ... beat` (same backend image) on a VM/container service connected to the same database, Redis and storage. Without them, imports and reports stay "queued" and SLA/alerts are not evaluated |
| S3-compatible private storage | attachments, imports, reports | any S3-compatible service (`STORAGE_*`) |
| ClamAV (`clamd`) | malware scanning is mandatory in production | a reachable clamd (`CLAMAV_HOST`/`CLAMAV_PORT`) over a private network |

## Environment variables (Project Settings → Environment Variables)

Everything in `docs/configuration.md` applies. Vercel-specific values:

* `APP_ENV=production`, `SESSION_COOKIE_SECURE=true`, `MALWARE_SCANNER=clamav`
* `ALLOWED_HOSTS=<your-domain>,<project>.vercel.app` (also used to accept the sign-in Origin)
* `CLIENT_IP_HEADER=x-real-ip` so rate limits, lockout and suspicious-login detection see the
  real client address (Vercel overwrites this header; do not set it behind other proxies)
* `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`,
  `DATABASE_SSLMODE=verify-full`, and a small pool (`DATABASE_POOL_SIZE=2`,
  `DATABASE_MAX_OVERFLOW=2`) because each function instance has its own pool
* `REDIS_*`, `STORAGE_*`, `DATA_ENCRYPTION_KEY`, `LOOKUP_HMAC_KEY`, `METRICS_TOKEN`,
  `DEPLOYMENT_*`, `GRIEVANCE_REFERENCE_PREFIX`
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
