# Architecture

## Overview

DG-IMEWS is a **modular monolith** with an independently deployable background
worker. One FastAPI application exposes `/api/v1`; one Celery worker image runs
background jobs; both share one codebase and one PostgreSQL/PostGIS database.
See [ADR 0001](adr/0001-modular-monolith.md).

```
            Browser (React SPA, same-origin)
                         │  HTTP (HTTPS in Phase 10)
                ┌────────▼────────┐   edge network
                │  nginx (web)    │   static SPA + security headers + /api proxy
                └────────┬────────┘   + per-IP rate limit
                         │ /api/*
                ┌────────▼────────┐                 ┌───────────────────┐
                │ FastAPI (api)   │── enqueue ──►   │ Celery (worker)   │
                │ gunicorn+uvicorn│                 │ AI, imports, SLA, │
                └──┬──────────┬───┘                 │ reports (later)   │
                   │          │                     └──┬─────────────┬──┘
      data network │ (internal: no route outside)      │             │
          ┌────────▼───┐  ┌───▼──────┐                 │             │
          │ PostgreSQL │  │  Redis   │◄────────────────┘             │
          │ + PostGIS  │◄─┤ cache,   │                               │
          └────────────┘  │ broker   │◄──────────────────────────────┘
                          └──────────┘
   Private S3-compatible object storage is added with attachments in Phase 4.
```

* Only `web` publishes a port. `db`, `redis`, `api` and `worker` sit on an
  `internal: true` network (verified: the web container cannot resolve `db`).
* The browser only talks to its own origin. No API host, key or secret is compiled
  into the frontend bundle.

## Modules and boundaries

Backend code lives in `backend/app/modules/<module>/`. Each module owns its models,
service layer, schemas and router, and owns one PostgreSQL schema. **Rules:**

1. A module writes only to tables in the schema it owns.
2. Other modules call its **service functions**, never its tables directly.
   Read-only reporting modules (dashboard, reports) may read through documented
   query functions or database views.
3. Routers are thin: validate input (Pydantic), check authorisation, call a service.
4. Cross-module foreign keys are allowed (for referential integrity); cross-module
   writes are not.

| # | Module (package) | Responsibility | Owns schema | Phase |
|---|---|---|---|---|
| A | Identity & Access (`iam`) | users, roles, permissions, scope assignments, sessions, MFA | `iam` | 2 |
| B | Grievance Management (`grievances`) | lifecycle, assignment, status history, comments, attachments, relationships | `grievance`, `citizen` (personal data, separately grantable) | 4 |
| C | Intake & Source Adapters (`intake`) | adapter interface per source, CSV/XLSX import, external references, duplicate-import prevention | `grievance` (via service) | 4 |
| D | AI Intelligence (`intelligence`) | versioned, explainable classification/extraction/similarity/clustering; human review | `intel` | 5 |
| E | Geographic Intelligence (`geography`) | administrative geography reference data; PostGIS hotspot queries | `ref` (geography tables) | 1, 6 |
| F | Early Warning (`early_warning`) | configurable versioned risk rules, alerts with reasons and actions | `intel` | 6 |
| G | Department Performance (`performance`) | SLA policies/events, escalations, snapshots | `perf` | 7 |
| H | DM Command Dashboard (`dashboard`) | read-only aggregates; every KPI links to a filtered record query | — | 3 |
| I | Reports & Analytics (`reports`) | async report jobs (PDF/XLSX), restricted exports | `governance` | 8 |
| J | Notifications (`notifications`) | notification centre, delivery channels | `governance` | 3 |
| K | Audit & Security (`audit`) | append-only audit log, security events | `audit` | 2 |
| L | Administrative Configuration (`administration`) | departments, issue categories, source channels, system configuration | `ref` (org tables), `governance` | 1, 3 |
| — | System (`system`) | health checks, deployment metadata | — | 1 |

## Cross-cutting concerns (implemented in Phase 1)

| Concern | Where | Behaviour |
|---|---|---|
| Configuration | `app/core/config.py` | Environment variables / Docker secret files only. Staging/production refuse short or placeholder secrets, `*` hosts/origins, DEBUG logging, missing district identity. |
| Error handling | `app/core/errors.py` | One envelope `{"error": {code, message, request_id, details}}`. Validation errors never echo submitted values; 500s never expose exception text. |
| Logging | `app/core/logging.py` | JSON lines with `request_id`; values under sensitive key names (password, token, aadhaar, mobile, email, address…) are redacted. Access log records path only, never query strings. |
| Request correlation | `app/core/middleware.py`, nginx | nginx generates `$request_id`, the API accepts it only if it matches a safe pattern, returns it as `X-Request-ID` and in error bodies. |
| Security headers | API middleware + nginx snippet | nosniff, frame DENY, strict CSP (API: `default-src 'none'`; UI: self-only, no inline), no-store on API, HSTS in production. |
| Host validation | `TrustedHostMiddleware` | Requests with unexpected `Host` are rejected (400). |
| Health | `/api/v1/health/live`, `/health/ready` | Liveness has no dependencies; readiness checks DB, PostGIS, migration head and Redis, returning only status/latency/reason codes. |

## Authorisation model (designed now, built in Phase 2)

* Every protected endpoint declares a permission (e.g. `grievance.assign`) and is
  checked server-side by a FastAPI dependency; resource-level checks then apply the
  user's **scope assignments** (district / subdivision / block / department /
  assigned-only) as SQL predicates in the service query, so out-of-scope rows are
  never loaded.
* Sensitive fields (citizen PII in schema `citizen`) require a separate permission;
  responses omit or mask them otherwise.
* Super Administrator manages users and configuration but does **not** implicitly
  hold `citizen.read`.
* Auditor role: read-only permissions only; enforced in the permission catalogue and
  by tests that assert every write endpoint rejects it.
* Frontend navigation visibility is cosmetic. It is never a control.

## AI boundary (Phase 5)

AI services produce **suggestions** stored in `intel.*` with model id/version,
confidence, evidence and input reference. They have no code path that changes
grievance status: the grievance service exposes no "close/reject" operation to the
intelligence module, and a test will assert this. Officers accept/edit/reject
suggestions; each decision is audited.

## Frontend structure

```
frontend/src/
  app/            router (route table + handles), providers (React Query, a11y prefs)
  design-system/  accessible components (Button, Alert, Panel, FormFields, DataTable,
                  Breadcrumbs, StatusBadge, Loading/Empty/Error states) + token tests
  layout/         AppShell, GovHeader, AccessibilityControls, Sidebar, Footer, SkipLink,
                  navigation.ts (single source for nav + module routes)
  lib/            api client (same-origin, error envelope → ApiError), hooks, formatting
  pages/          SystemStatus (live), Dashboard + module placeholders (no data), etc.
  styles/         Tailwind v4 + theme.css (semantic tokens, high-contrast mode)
```
