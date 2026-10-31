# API reference (v1)

Base path: `/api/v1`. The OpenAPI schema is served at `/api/v1/openapi.json` with
Swagger UI at `/api/docs` outside production (`EXPOSE_API_DOCS` overrides).

## Conventions

* JSON only; timestamps are ISO-8601 UTC.
* Every response carries `X-Request-ID`. Quote it when reporting a problem.
* Errors use one envelope:

```json
{"error": {"code": "not_found", "message": "Not Found", "request_id": "6f1c…", "details": []}}
```

Validation errors (`422`, code `validation_error`) list
`{"location": [...], "message": "...", "type": "..."}` per field and never echo the
submitted value.

## Authentication

Sessions are server-side. `POST /auth/login` sets an HttpOnly `dgi_session` cookie
(SameSite=Strict, Secure outside development) and a readable `dgi_csrf` cookie. Every
non-GET request must send the CSRF value in `X-CSRF-Token`. Responses from
`/auth/login`, `/auth/mfa/*` and `/auth/password` carry a `state`:
`authenticated`, `mfa_required`, `mfa_enrollment_required` or
`password_change_required`; only `authenticated` sessions can call protected endpoints
(others get `403 additional_step_required`).

Every protected endpoint checks permissions server-side (see
`backend/app/modules/iam/catalogue.py`) and filters records by the caller's scope in
SQL. Out-of-scope records respond `404`, indistinguishable from missing ones.

### Sign-up

* **Officials** call `POST /auth/signup` (public; `GET /auth/signup/options` says whether it
  is on) with `username`, `full_name`, optional `email` and `password`. The account is
  active at once and the response is a signed-in session, exactly like `/auth/login`. Roles:
  the first account becomes the Super Administrator (while no active one exists); every later account is a Data Entry Operator that sees only the grievances it registered (role `data_entry_operator`, scope `own`). Administrators widen roles
  and areas with the normal user-management endpoints.
* **Citizens** use `/citizen/*`, a separate account type with its own cookies
  (`dgi_csession` HttpOnly, `dgi_ccsrf` echoed in `X-CSRF-Token`). Flow: `register` →
  `verify` (6-digit one-time code) → `login` → `grievances` (file, list, detail). A citizen
  session reaches only the citizen's own grievances, with public status labels, the
  responsible office and the resolution once resolved; no officer names or internal notes.
  The whole prefix returns `404` when the portal is disabled.

## Health and metadata (unauthenticated)

* `GET|HEAD /health/live`: liveness, no dependencies.
* `GET /health/ready`: database, PostGIS, migration head, Redis, object storage; 503 if any is unavailable.
* `GET /system/info`: version and configured deployment identity.
* `GET /system/metrics`: Prometheus metrics; requires `Authorization: Bearer <METRICS_TOKEN>` and is blocked by nginx at the public edge.

## Endpoint index (generated from the OpenAPI schema)

106 operations.

### administration

| Method | Path |
|---|---|
| POST | `/api/v1/admin/boundaries/import` |
| GET | `/api/v1/admin/boundary-datasets` |
| POST | `/api/v1/admin/boundary-datasets` |
| POST | `/api/v1/admin/categories` |
| PATCH | `/api/v1/admin/categories/{obj_id}` |
| GET | `/api/v1/admin/classification-rules` |
| POST | `/api/v1/admin/classification-rules` |
| PATCH | `/api/v1/admin/classification-rules/{obj_id}` |
| POST | `/api/v1/admin/departments` |
| PATCH | `/api/v1/admin/departments/{obj_id}` |
| GET | `/api/v1/admin/risk-models` |
| POST | `/api/v1/admin/risk-models` |
| GET | `/api/v1/admin/sla-policies` |
| POST | `/api/v1/admin/sla-policies` |
| PATCH | `/api/v1/admin/sla-policies/{obj_id}` |
| PATCH | `/api/v1/admin/sources/{obj_id}` |
| POST | `/api/v1/admin/units/{level}` |
| PATCH | `/api/v1/admin/units/{level}/{unit_id}` |

### audit

| Method | Path |
|---|---|
| GET | `/api/v1/audit/logs` |
| GET | `/api/v1/audit/verify` |

### auth

| Method | Path |
|---|---|
| POST | `/api/v1/auth/login` |
| POST | `/api/v1/auth/logout` |
| GET | `/api/v1/auth/me` |
| POST | `/api/v1/auth/mfa/confirm` |
| POST | `/api/v1/auth/mfa/setup` |
| POST | `/api/v1/auth/mfa/verify` |
| POST | `/api/v1/auth/password` |
| POST | `/api/v1/auth/signup` |
| GET | `/api/v1/auth/signup/options` |

### citizen

| Method | Path |
|---|---|
| GET | `/api/v1/citizen/config` |
| GET | `/api/v1/citizen/grievances` |
| POST | `/api/v1/citizen/grievances` |
| GET | `/api/v1/citizen/grievances/{grievance_id}` |
| POST | `/api/v1/citizen/login` |
| POST | `/api/v1/citizen/logout` |
| GET | `/api/v1/citizen/me` |
| POST | `/api/v1/citizen/otp/resend` |
| GET | `/api/v1/citizen/reference/categories` |
| GET | `/api/v1/citizen/reference/units/{level}` |
| POST | `/api/v1/citizen/register` |
| POST | `/api/v1/citizen/verify` |

### dashboard

| Method | Path |
|---|---|
| GET | `/api/v1/dashboard/blocks` |
| GET | `/api/v1/dashboard/categories` |
| GET | `/api/v1/dashboard/clusters` |
| GET | `/api/v1/dashboard/important` |
| GET | `/api/v1/dashboard/recent-actions` |
| GET | `/api/v1/dashboard/summary` |
| GET | `/api/v1/dashboard/trends` |

### early-warning

| Method | Path |
|---|---|
| GET | `/api/v1/alerts` |
| POST | `/api/v1/alerts/evaluate` |
| GET | `/api/v1/alerts/{alert_id}` |
| POST | `/api/v1/alerts/{alert_id}/actions` |

### gis

| Method | Path |
|---|---|
| GET | `/api/v1/gis/config` |
| GET | `/api/v1/gis/layers/{level}` |

### grievances

| Method | Path |
|---|---|
| GET | `/api/v1/grievances` |
| POST | `/api/v1/grievances` |
| GET | `/api/v1/grievances/{grievance_id}` |
| PATCH | `/api/v1/grievances/{grievance_id}` |
| POST | `/api/v1/grievances/{grievance_id}/assign` |
| POST | `/api/v1/grievances/{grievance_id}/attachments` |
| GET | `/api/v1/grievances/{grievance_id}/attachments/{attachment_id}` |
| POST | `/api/v1/grievances/{grievance_id}/comments` |
| POST | `/api/v1/grievances/{grievance_id}/escalate` |
| POST | `/api/v1/grievances/{grievance_id}/external-references` |
| GET | `/api/v1/grievances/{grievance_id}/history` |
| POST | `/api/v1/grievances/{grievance_id}/links` |
| GET | `/api/v1/grievances/{grievance_id}/officers` |
| POST | `/api/v1/grievances/{grievance_id}/transition` |

### iam

| Method | Path |
|---|---|
| GET | `/api/v1/iam/roles` |
| GET | `/api/v1/iam/users` |
| POST | `/api/v1/iam/users` |
| GET | `/api/v1/iam/users/{user_id}` |
| PATCH | `/api/v1/iam/users/{user_id}` |
| POST | `/api/v1/iam/users/{user_id}/mfa/reset` |
| POST | `/api/v1/iam/users/{user_id}/reset-password` |
| PUT | `/api/v1/iam/users/{user_id}/roles` |
| PUT | `/api/v1/iam/users/{user_id}/scopes` |
| POST | `/api/v1/iam/users/{user_id}/unlock` |

### intake

| Method | Path |
|---|---|
| GET | `/api/v1/intake/adapters` |
| POST | `/api/v1/intake/development-adapter/run` |
| GET | `/api/v1/intake/imports` |
| POST | `/api/v1/intake/imports` |
| GET | `/api/v1/intake/imports/{batch_id}` |

### intelligence

| Method | Path |
|---|---|
| GET | `/api/v1/grievances/{grievance_id}/intelligence` |
| POST | `/api/v1/grievances/{grievance_id}/intelligence/run` |
| POST | `/api/v1/intelligence/classifications/{classification_id}/review` |
| GET | `/api/v1/intelligence/clusters` |
| POST | `/api/v1/intelligence/duplicates/{duplicate_id}/review` |

### notifications

| Method | Path |
|---|---|
| GET | `/api/v1/notifications` |
| POST | `/api/v1/notifications/read-all` |
| POST | `/api/v1/notifications/{notification_id}/read` |

### performance

| Method | Path |
|---|---|
| GET | `/api/v1/performance/blocks` |
| GET | `/api/v1/performance/departments` |
| GET | `/api/v1/performance/escalations` |
| GET | `/api/v1/performance/snapshots` |

### reference

| Method | Path |
|---|---|
| GET | `/api/v1/reference/categories` |
| GET | `/api/v1/reference/departments` |
| GET | `/api/v1/reference/sources` |
| GET | `/api/v1/reference/units/{level}` |

### reports

| Method | Path |
|---|---|
| GET | `/api/v1/reports` |
| POST | `/api/v1/reports` |
| GET | `/api/v1/reports/{job_id}` |
| GET | `/api/v1/reports/{job_id}/download` |

### system

| Method | Path |
|---|---|
| GET | `/api/v1/health/live` |
| GET | `/api/v1/health/ready` |
| GET | `/api/v1/system/info` |
