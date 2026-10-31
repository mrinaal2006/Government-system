# Phase 1 completion report: Foundation

Date: 2026-10-31. Starting point: empty directory (no existing project to preserve).

## 1. Implemented functionality

* Repository structure for a modular monolith: 12 domain module packages plus
  `system`, each with a documented responsibility and schema ownership.
* Backend foundation: environment configuration with production safety checks,
  structured JSON logging with redaction, request-ID correlation, a single error
  envelope, security headers, trusted-host validation, and API versioning under
  `/api/v1`.
* PostgreSQL 16 + PostGIS 3.4 with least-privilege roles, Alembic migrations, the
  administrative geography and organisation reference schema, and geometry
  provenance enforcement.
* Redis (password-protected, dangerous commands disabled) and a Celery worker with
  a JSON-only round-trip task.
* Health endpoints: liveness, readiness (DB, PostGIS, migration head, Redis) and
  deployment metadata.
* Docker Compose stack: db, redis, migrate (one-shot), api, worker, web (nginx).
  Internal data network, read-only containers, dropped capabilities, non-root users.
* Government design system and application shell: official header with configured
  (never invented) identity, non-production banner, accessibility controls (text
  size, high contrast), skip link, sidebar navigation, breadcrumbs, footer, route
  focus management, accessible form fields, data table, alerts, badges, and
  loading/empty/error states. Live system status page. Honest placeholders (no data)
  for modules in later phases.

## 2. Architecture decisions

See `docs/adr/`: 0001 modular monolith; 0002 synchronous SQLAlchemy/psycopg 3;
0003 separate migration/runtime DB roles; 0004 mandatory geometry provenance;
0005 frontend stack and version pinning. Further decisions:
* Enumerations are `varchar` + CHECK constraints, not PG ENUMs.
* `updated_at` is maintained by a DB trigger.
* Only the seven specified source channels are seeded (all `not_configured`); no
  geography, departments or categories are pre-loaded.
* Blocks link to the district; subdivision links are optional because block and
  revenue hierarchies don't nest uniformly (documented assumption).

## 3. Files created

All files are new (no pre-existing project).
* Root: `README.md`, `.env.example`, `.gitignore`, `.dockerignore`, `docker-compose.yml`, `docker-compose.dev.yml`
* `backend/`: `pyproject.toml`, `Dockerfile`, `.dockerignore`, `README.md`, `alembic.ini`,
  `alembic/{env.py,script.py.mako}`, `alembic/versions/20261031_0001_reference_foundation.py`,
  `alembic/versions/20261031_0002_seed_source_channels.py`,
  `app/{__init__,main,asgi}.py`, `app/api/{deps.py,v1/router.py}`,
  `app/core/{config,logging,errors,middleware,request_context}.py`,
  `app/db/{base,session,models}.py`, `app/infra/redis.py`,
  `app/worker/{celery_app,tasks}.py`, `app/modules/*/__init__.py` (13),
  `app/modules/geography/models.py`, `app/modules/administration/models.py`,
  `app/modules/system/{router,service,schemas}.py`,
  `tests/conftest.py`, `tests/unit/{test_config,test_api_foundation,test_logging_and_worker}.py`,
  `tests/integration/{conftest,test_database,test_services}.py`
* `frontend/`: `package.json`, `package-lock.json`, `index.html`, `vite.config.ts`, `tsconfig*.json`,
  `eslint.config.js`, `playwright.config.ts`, `public/favicon.svg`, `e2e/shell.spec.ts`,
  `src/main.tsx`, `src/app/{routes,providers}.tsx`, `src/styles/{index,theme}.css`,
  `src/design-system/*` (10 components + `tokens.test.ts`, `components.test.tsx`),
  `src/layout/*` (AppShell, GovHeader, AccessibilityControls, Sidebar, Footer, SkipLink,
  navigation + tests), `src/lib/{api/client,api/system,a11y/preferences,format}.ts(x)` + test,
  `src/pages/*` (SystemStatus, Dashboard, ModulePlaceholder, Accessibility, NotFound,
  DesignSystem [dev-only]) + test, `src/test/{setup.ts,render.tsx}`
* `infra/`: `postgres/init/01-roles-and-extensions.sh`, `nginx/{default.conf,security-headers.conf,Dockerfile}`,
  `build/no-extra-ca.pem` (empty placeholder)
* `scripts/`: `init-dev-env.sh`, `build-images.sh`, `verify.sh`
* `docs/`: `architecture.md`, `database.md`, `configuration.md`, `development.md`, `api.md`,
  `adr/0001`–`0005`, this report

## 4. Files modified

None outside this phase.

## 5. Database changes

* Init script (superuser, first start): roles `dgimews_migrator` and `dgimews_app`;
  extensions `postgis`, `pgcrypto`, `pg_trgm`, `citext`; `public` locked down;
  optional `dgimews_test` database.
* Migration `0001_reference_foundation`: schema `ref`; trigger function; tables
  `boundary_datasets`, `districts`, `subdivisions`, `blocks`, `municipalities`,
  `gram_panchayats`, `villages`, `wards`, `departments`, `issue_categories`,
  `grievance_sources`, with FKs, CHECKs, partial unique indexes, GiST and trigram
  GIN indexes, `updated_at` triggers and runtime-role grants.
* Migration `0002_seed_source_channels`: seven source channels, `not_configured`.
* Both migrations downgrade cleanly (tested).

## 6. API endpoints created

`GET|HEAD /api/v1/health/live`, `GET /api/v1/health/ready`, `GET /api/v1/system/info`.
OpenAPI at `/api/v1/openapi.json` and Swagger UI at `/api/docs` (non-production only).

## 7. Commands executed (key)

`dockerd` (started in the sandbox); `docker pull` (postgis 16-3.4, redis 7.4,
nginx-unprivileged 1.28, python 3.13-slim, node 22-slim); `./scripts/init-dev-env.sh`;
`uv venv` + `uv pip install -e '.[dev]'`; `npm install --save-exact …`;
`./scripts/build-images.sh` (with the sandbox proxy/CA); `docker compose -f docker-compose.yml
-f docker-compose.dev.yml up -d --no-build`; `./scripts/verify.sh`; curl smoke tests;
DB stop/start recovery test; production-config refusal test.

## 8–9. Tests executed and actual results

| Suite | Result |
|---|---|
| Ruff lint + format check (backend) | pass |
| mypy `--strict` (41 source files) | pass, no issues |
| Pytest unit (44) | **44 passed** |
| Pytest integration against real PostgreSQL/PostGIS, Redis, Celery (31) | **31 passed** |
| ESLint (incl. jsx-a11y strict) + `tsc -b` | pass |
| Vitest (101: components, shell, a11y prefs, API client, status page, 68 contrast checks, jsdom axe) | **101 passed** |
| Production bundle hygiene (no dev-only content, no source maps) | pass |
| Playwright E2E, desktop + mobile Chromium, full stack via nginx (22) | **21 passed, 1 skipped** (keyboard skip-link test runs on desktop only, by design) |

Manual/scripted verifications on the running stack:
* All six services healthy; migrate exited 0 after applying 0001 → 0002.
* Readiness 200 with all components ok; Celery `system.ping` round trip returned `pong`.
* Web container cannot resolve `db` (data network isolation).
* `.env` request returns 404; SPA deep links return 200; API 404 uses the envelope.
* Database stopped → readiness 503 (`database/postgis/migrations` unavailable, redis ok),
  liveness still 200; database restarted → readiness 200 within ~2 s.
* `APP_ENV=production` with weak secret and no district name → startup refused,
  with each reason listed and without echoing the secret.
* Built images contain no proxy settings or CA material; backend runs as uid 10001.

Defects found by these tests and fixed during the phase: runtime role could not
read `alembic_version` (readiness), routes ignored settings passed to `create_app`,
blank Compose values reported as `""` not `null`, HEAD not allowed on liveness,
high-contrast accent invisible on header, duplicate landmark names, WCAG 2.5.3
label-in-name on text-size buttons, 113 px horizontal overflow at 320 px.

## 10. Known limitations

* No authentication or authorisation yet (Phase 2): all Phase 1 endpoints are public
  by design and expose no confidential data. Do not deploy beyond a trusted network.
* HTTP only; TLS, HSTS and `upgrade-insecure-requests` arrive in Phase 10.
* Object storage (MinIO/S3) not yet provisioned (Phase 4 with attachments).
* ECharts and Leaflet/MapLibre are not yet installed (Phases 3 and 6).
* English UI only; Hindi/local-language interface not yet implemented.
* ESLint 9 is end-of-life (ESLint 10 blocked by plugin peer ranges; dev-only tool).
* nginx resolves the `api` upstream at start; restart `web` if `api` is recreated with a new IP.
* `docker compose build` needs interactive entitlement approval for host networking
  behind a proxy; `scripts/build-images.sh` is the workaround.
* No independent accessibility or security audit has been performed; no compliance is claimed.

## 11. Security considerations

Least-privilege DB roles (no DDL/DELETE for runtime); Redis password via config file
(not process args) with FLUSHALL/FLUSHDB/CONFIG/DEBUG disabled; internal data network;
read-only, non-root containers with all capabilities dropped and `no-new-privileges`;
secrets only via env/Docker secrets with production strength checks; strict CSP and
security headers; no third-party origins; no source maps; validation errors and 500s
never echo input or internals; log redaction; query strings never logged; request IDs
sanitised; readiness exposes no versions or hostnames; Celery JSON-only serialisation.

## 12. Outstanding issues

None blocking. Decisions needed from the district administration before later phases:
official district/state names and local-language names; emblem/logo usage approval;
source of verified boundary data (LGD / state GIS); retention periods for grievance
data; which grievance portals and helpline integrations are authorised, and their
documentation.

## 13. Acceptance checklist

- [x] Architecture explained and documented (docs/architecture.md, ADRs)
- [x] Complete folder structure created
- [x] Initial database schema designed, migrated, tested (up/down, drift, constraints, grants)
- [x] Frontend and backend set up with linting, typing and tests
- [x] PostgreSQL + PostGIS + Redis configured with least privilege
- [x] Docker Compose stack runs healthy end to end
- [x] FastAPI health endpoints with real DB/PostGIS/migration/Redis checks
- [x] Government design system and application shell, accessibility-tested
- [x] All test suites pass (results above)
- [x] No fake data, no fake integrations, no hard-coded credentials

## 14. Next-phase prerequisites (Phase 2: authentication, MFA, RBAC, sessions, audit)

* Approve the role list and the permission catalogue draft (per module, per action).
* Decide the MFA method(s) for privileged users (TOTP recommended; SMS OTP needs an
  approved gateway).
* Confirm the password policy and lockout thresholds (draft from CERT-In / ASVS will be
  proposed rather than assumed).
* Confirm session lifetime and idle timeout for officers.
* Provide the first Super Administrator bootstrap procedure (CLI command, one-time).
