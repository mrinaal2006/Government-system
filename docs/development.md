# Development guide

## Prerequisites

Docker with Compose v2, Python 3.12+ with [uv](https://docs.astral.sh/uv/) (or pip),
Node.js 22.

## First run

```bash
./scripts/init-dev-env.sh
```

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Open http://127.0.0.1:8080. API docs (dev only): http://127.0.0.1:58000/api/docs.

The `migrate` service applies migrations before `api` and `worker` start. The dev
override also creates the `dgimews_test` database used by integration tests.

Behind a TLS-inspecting proxy, build with plain `docker build` instead (Compose's
bake builder needs interactive approval for host networking):

```bash
BUILD_NETWORK=host BUILD_HTTPS_PROXY=http://proxy:3128 BUILD_CA_BUNDLE=/path/ca.pem ./scripts/build-images.sh
```

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --no-build
```

## Backend

```bash
cd backend && uv venv .venv && uv pip install --python .venv/bin/python -e '.[dev]'
```

```bash
cd backend && .venv/bin/pytest tests/unit
```

```bash
cd backend && .venv/bin/pytest tests/integration
```

Integration tests read credentials from the root `.env`, connect to the dev ports
on 127.0.0.1 and **always** use `<DATABASE_NAME>_test` (they refuse any other
database), migrating it down and up. Redis DBs 10–12 are used to avoid touching
development data.

New migration (write by hand or autogenerate, then review):

```bash
cd backend && set -a && . ../.env && set +a && DATABASE_HOST=127.0.0.1 DATABASE_PORT=55432 DATABASE_MIGRATION_USER=$DATABASE_MIGRATION_USER .venv/bin/alembic revision --autogenerate -m "describe change"
```

`test_orm_models_match_migrations` fails if models and migrations diverge.

## Frontend

```bash
cd frontend && npm ci
```

```bash
cd frontend && npm run dev
```

```bash
cd frontend && npm test
```

```bash
cd frontend && npm run test:e2e
```

E2E tests run against the full stack at `E2E_BASE_URL` (default
`http://127.0.0.1:8080`) in desktop and mobile Chromium, including axe WCAG 2.1 AA
scans (with colour contrast) in standard and high-contrast modes, and a 320 px
reflow check.

## Everything at once

```bash
./scripts/verify.sh
```

Use `--no-services` to skip the integration and E2E steps.

## Rules that reviews enforce

* No sample/decorative data in production code paths. Development fixtures must be
  labelled `TEST DATA` and live under `tests/`.
* No `dangerouslySetInnerHTML` (lint error). No secrets in `frontend/`.
* Every new protected endpoint (Phase 2+) declares a permission and has a test
  proving an unauthorised role is rejected.
* Every screen handles loading, empty, success and error states.
