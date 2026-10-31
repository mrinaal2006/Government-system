# Phase reports: Phases 2-10

Phase 1 is reported in [phase-1-report.md](phase-1-report.md). Phases 2-10 were delivered
together on 31 Oct 2026 at the request of the project owner (rather than with a review gate
between phases); every phase was nevertheless tested before the next was built on it.

## 1. Implemented functionality

| Phase | Delivered |
|---|---|
| 2 Auth, MFA, RBAC, audit | Argon2id passwords and policy; server-side sessions (hashed tokens, HttpOnly/SameSite=Strict/Secure cookies, absolute + idle expiry, rotation, revocation); CSRF; TOTP MFA with enrolment, QR code, replay protection, mandatory for privileged roles; rate limiting (fail-closed) and lockout; suspicious sign-in detection with notification; permission catalogue for the 9 roles; district/subdivision/block/department/assigned/own scopes as SQL predicates; user administration; append-only hash-chained audit log with verification; bootstrap CLI for the first Super Administrator |
| 3 UI, dashboard, notifications | Sign-in/MFA/password screens; permission-aware navigation and guards; user bar; notification centre with unread count; command dashboard (7 KPIs linking to records, weekly/monthly trends, block and category distribution, emerging clusters, important unresolved grievances, department performance, recent actions); tables, filters in URL, pagination, dialogs, tabs, charts with data tables |
| 4 Grievances, intake | Registration with location derivation and consistency checks; immutable references; state machine (assign, start, submit, verify/return, close, reopen) with optimistic locking and separation of duties; escalation; notes and investigation records; attachments (type/magic checks, size limit, ClamAV, private S3 storage); links and duplicates; external references; CSV/XLSX import with provenance, duplicate-file and duplicate-record prevention; labelled development adapter |
| 5 AI | Keyword-rule category and department suggestions; location extraction from official names; extractive summaries; trigram + complainant-hash duplicate candidates; clusters; versioned risk scoring; full metadata per output; officer review (accept/edit/reject) as the only path to change a grievance |
| 6 GIS, alerts | GeoJSON layers with scoped counts and role-based precision; verified boundary dataset registration and GeoJSON import (invalid geometry rejected); six early-warning indicators with reasons, evidence, recommended actions, de-duplication and an action workflow requiring reasons |
| 7 Performance | Configurable SLA policies (none pre-loaded); due times; warning and breach events; automatic escalation with notifications; department/block metrics; daily snapshots |
| 8 Reports | Asynchronous PDF/XLSX reports (register, department, block, executive summary) under the requester's scope; PII only on explicit request with permission; formula-injection protection; 7-day expiry; audited downloads |
| 9 Testing | Authorization matrix, security probes, performance budget, E2E across roles, accessibility in both themes, recovery drill |
| 10 Production | TLS nginx profile with HSTS, production compose override, Prometheus metrics/rules, encrypted backup and restore scripts, deployment/operations/security documentation |

## 2. Architecture decisions

ADR 0006 (Garage object storage), 0007 (deterministic explainable intelligence),
0008 (server-side sessions). Others: scope enforcement in SQL with 404 for out-of-scope
records; append-only tables enforced by database grants and triggers rather than code alone;
background work in Celery with a periodic sweep for lost messages; demo data as a
development-only, clearly labelled loader that uses the real service layer.

## 3-4. Files created / modified

Created: backend modules `iam`, `audit`, `grievances`, `intake`, `intelligence`,
`early_warning`, `geography/router`, `performance`, `dashboard`, `reports`, `notifications`,
`administration/router`, `core/security|ratelimit|metrics|request_meta`, `infra/storage|malware`,
`api/auth|common`, `cli`, `demo`, `backup`; migrations 0003-0006; integration tests
`test_auth`, `test_grievance_workflow`, `test_authorization_matrix`; frontend auth provider,
API hooks, location picker, 9 new design-system components, 17 pages, tests and E2E suites;
`infra/garage`, `infra/monitoring`, `infra/nginx/tls.conf`, `docker-compose.prod.yml`;
scripts `alembic-dev`, `backup`, `restore`, `gen-selfsigned-cert`; docs listed in README.
Modified: Phase 1 config, compose files, nginx config (Host header fix), system router
(storage readiness, metrics), navigation and routing, verify script.

## 5. Database changes

Migration 0003 (7 schemas, 38 tables, triggers, grants), 0004 (roles, permissions,
provisional risk model v1), 0005-0006 (narrow DELETE grants for recomputed link tables).
All migrations downgrade and upgrade cleanly; a test asserts the ORM matches them exactly.

## 6. API endpoints

92 operations, listed in [api.md](api.md) (generated from the OpenAPI schema).

## 7. Key commands executed

`docker compose ... up -d`, `./scripts/build-images.sh`, `alembic upgrade/downgrade`,
`python -m app.cli load-demo-data`, `pytest`, `vitest`, `playwright test` (dev HTTP and
production HTTPS), `./scripts/backup.sh`, `docker volume rm` (disaster simulation),
`./scripts/restore.sh`, `openssl s_client`, Prometheus API queries.

## 8-9. Tests and actual results

See [testing.md](testing.md). Final run: backend **276 passed**, frontend unit **116 passed**,
E2E **12 passed** against the production TLS configuration, ruff/mypy-strict/ESLint/tsc clean.
Performance p95 ≤ 87 ms on 5,000 grievances. Recovery drill: complete restore in 24 s with
identical counts, valid audit chain and byte-identical attachment. ClamAV detected EICAR.

Defects found by these tests and fixed: `rowcount` unreliable for `INSERT … ON CONFLICT`
(caused double escalation), invalid `GROUP BY` constant in the executive summary, missing
DELETE grants for alert/cluster refresh, blank Compose booleans, nginx dropping the port from
`Host` (broke the login origin check), MFA page redirecting before honouring the return path,
logout cache race, restore failing as non-superuser and leaving services stopped, demo data
spiking the resolution trend, clipped chart labels.

## 10. Known limitations

* No live government integrations (none authorised); file import only.
* Intelligence is rule-based; no ML model, no accuracy claim.
* English interface only; Hindi and other official languages pending.
* ClamAV signature updates need outbound access to `database.clamav.net` or a mirror
  (unavailable in the build sandbox; the bundled signatures were used for testing).
* Data retention/deletion not automated (needs an approved retention schedule); key-rotation
  re-encryption is manual.
* Concurrency load testing, penetration testing and assistive-technology user testing not done.
* ESLint 9 (end-of-life) until plugins support ESLint 10.

## 11. Security considerations

See [security.md](security.md). The provisional role-permission mapping and risk model must
be approved by the district administration before live use.

## 12. Outstanding issues

Decisions required from the administration: final role permissions; MFA method and device
policy; password/lockout/session parameters; official SLA timelines with their orders; risk
model approval; retention schedule; district identity and emblem usage; source of verified
LGD codes and boundaries; authorisation and documentation for any live integration.

## 13. Acceptance checklist

- [x] Backend-enforced RBAC and scopes, verified by a role × endpoint matrix
- [x] MFA for privileged roles; secure sessions; CSRF; lockout; audit
- [x] Complete grievance lifecycle with immutable history and separation of duties
- [x] AI suggestions stored with full metadata, applied only by officer review
- [x] GIS and early warning with explainable reasons, no invented geography
- [x] SLA monitoring and automatic escalation without punitive action
- [x] Reports with scope and PII controls
- [x] All KPIs from live queries, each linked to its records
- [x] WCAG 2.1 AA automated checks pass (axe, contrast, reflow); no conformance claimed
- [x] TLS production profile, monitoring, backup and verified restore
- [x] No fabricated operational data, integrations or accuracy figures

## 14. Prerequisites for go-live

Independent security audit and accessibility audit; production certificate; verified master
data import; approval of permissions, SLA policies and risk model; operations staff trained on
the runbook; scheduled backups with an off-host copy and a first restore drill on production
infrastructure.
