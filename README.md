# DG-IMEWS: District Grievance Intelligence, Monitoring & Early Warning System

A platform for a District Magistrate's office to consolidate public grievances from
multiple channels, monitor resolution and department performance, and surface
emerging administrative risks early. AI assists authorised officers; it never
closes, rejects or disposes of a grievance.

**Status: Phase 1 (foundation) complete.** See [docs/phase-1-report.md](docs/phase-1-report.md).
There is no authentication yet (Phase 2), so do not expose this deployment beyond a
trusted development network.

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, React Router, TanStack Query |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.0, Pydantic 2, Alembic |
| Data | PostgreSQL 16 + PostGIS 3.4, Redis 7.4 |
| Background | Celery 5 (Redis broker) |
| Edge | nginx (unprivileged), strict CSP |
| Tests | Pytest, Vitest + Testing Library + axe-core, Playwright + axe |

## Quick start (development)

```bash
./scripts/init-dev-env.sh
```

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Then open http://127.0.0.1:8080 and check **System status**. Run every check with:

```bash
./scripts/verify.sh
```

## Repository layout

```
backend/                 FastAPI modular monolith + Celery worker
  app/core/              config, logging, errors, middleware
  app/db/                declarative base, conventions, sessions
  app/modules/<module>/  12 domain modules + system (see docs/architecture.md)
  app/worker/            Celery app and tasks
  alembic/               migrations
  tests/unit|integration pytest suites
frontend/                React application
  src/design-system/     accessible component library + contrast tests
  src/layout/            government application shell
  e2e/                   Playwright tests (full stack)
infra/nginx/             web tier config + Dockerfile
infra/postgres/init/     superuser init: roles, extensions
scripts/                 init-dev-env, build-images, verify
docs/                    architecture, database, configuration, API, ADRs, reports
```

## Documentation

* [Architecture and module boundaries](docs/architecture.md)
* [Database design](docs/database.md)
* [Configuration reference](docs/configuration.md)
* [Development guide](docs/development.md)
* [API reference](docs/api.md)
* [Architecture decision records](docs/adr/)

## Compliance note

The design uses GIGW 3.0, WCAG 2.1 AA, OWASP ASVS, CERT-In directions and the DPDP
Act as baselines. **No certification or legal compliance is claimed**: that
requires independent assessment.
