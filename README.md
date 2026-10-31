# DG-IMEWS: District Grievance Intelligence, Monitoring & Early Warning System

A platform for a District Magistrate's office to consolidate public grievances from
multiple channels, manage their resolution with full accountability, monitor department
performance, and detect emerging administrative problems early. AI assists officers with
explainable suggestions; it never closes, rejects or disposes of a grievance.

**Status:** Phases 1-10 implemented and tested. See [docs/phase-reports.md](docs/phase-reports.md).
Before production use: load verified master data, approve the provisional risk model and role
permissions, and commission independent security and accessibility audits.

## Run it locally (with synthetic demo data)

Requires Docker with Compose v2, Python 3 and Node 22 (Node only for the frontend tests).

```bash
./scripts/init-dev-env.sh
```

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

```bash
docker compose exec api python -m app.cli load-demo-data
```

Open **http://localhost:8080** and sign in with an account printed by the last command (for
example `demo.dm`, `demo.officer.water1`, `demo.deo`). Accounts that require MFA print a TOTP
secret to add to any authenticator app, or get the current code with
`docker compose exec api python -m app.cli demo-totp demo.dm`.
All demo records are synthetic and labelled `[DEMO]`; the demo loader refuses to run outside
development. Behind a TLS-inspecting proxy, build with `./scripts/build-images.sh` (see
docs/development.md).

## What it does

| Area | Highlights |
|---|---|
| Identity and access | Argon2id, server-side sessions, CSRF, TOTP MFA, lockout, rate limits, suspicious sign-in alerts, 9 roles, area-based scopes enforced in SQL |
| Grievances | Immutable references, state machine with separation of duties, assignments, notes, scanned attachments, links, duplicates, encrypted complainant data |
| Intake | CSV/XLSX import with provenance and duplicate prevention; adapter interface for future authorised live integrations |
| Intelligence | Rule-based, explainable category/department/location suggestions, summaries, duplicate candidates, clusters, versioned risk scoring, all reviewed by officers |
| Early warning | Six indicators (overdue backlog, repeated reopenings, area concentration, essential services, escalations, volume spikes) with reasons, evidence and recommended actions |
| GIS | PostGIS layers from registered boundary datasets only; precision limited by role |
| Performance | SLA policies, automatic breach escalation, department and block metrics, daily snapshots |
| Dashboard and reports | Live KPIs that open their records, trends, PDF/XLSX reports, deterministic executive summary |
| Operations | Audit hash chain, Prometheus metrics and alerts, encrypted backup/restore (drill passed), TLS production profile |

## Documentation

[Architecture](docs/architecture.md) · [Database](docs/database.md) · [API](docs/api.md) ·
[Configuration](docs/configuration.md) · [Development](docs/development.md) ·
[Testing](docs/testing.md) · [Deployment](docs/deployment.md) · [Operations](docs/operations.md) ·
[Security](docs/security.md) · [Integrations](docs/integrations.md) · [User guide](docs/user-guide.md) ·
[ADRs](docs/adr/) · [Phase reports](docs/phase-reports.md)

## Compliance note

GIGW 3.0, WCAG 2.1 AA, OWASP ASVS, CERT-In directions and the DPDP Act are design
baselines. **No certification or legal compliance is claimed**; that requires independent assessment.
