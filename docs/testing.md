# Testing

| Suite | Command | Needs |
|---|---|---|
| Backend lint/types | `cd backend && .venv/bin/ruff check . && .venv/bin/mypy app` | - |
| Backend unit | `cd backend && .venv/bin/pytest tests/unit` | - |
| Backend integration (DB, Redis, storage, Celery, authorization matrix, security probes, performance budget) | `cd backend && .venv/bin/pytest tests/integration` | dev stack |
| Frontend lint/types/unit (incl. contrast and axe) | `cd frontend && npx eslint . && npx tsc -b && npx vitest run` | - |
| End-to-end (real browser, full stack) | `cd frontend && E2E_PASSWORD=... E2E_TOTP_SECRETS='{...}' E2E_BASE_URL=... npx playwright test` | stack + demo data |
| Everything | `./scripts/verify.sh` | dev stack |

E2E credentials are those printed by `python -m app.cli load-demo-data` (synthetic accounts,
development only); they are never committed.

## Results recorded on 31 Oct 2026

* Backend: **276 passed** (unit 45; integration 231 including a 153-case role × endpoint
  authorization matrix, injection/XSS/IDOR/mass-assignment probes, model-migration drift).
* Frontend unit: **116 passed** (components, auth flow, guards, register/detail flows, 68 WCAG
  contrast checks, jsdom axe).
* E2E (Chromium desktop + mobile, against the **production TLS configuration**): **12 passed**:
  CSP, sign-in errors, MFA, KPI drill-down, permission-based navigation and API refusal, full
  DEO → DM → Officer → DM lifecycle across two browser sessions, stored-XSS inertness, PDF
  report download, axe WCAG 2.1 AA on 15 pages in standard and high-contrast modes, 320 px reflow.
* Performance (5,000 synthetic grievances, sequential): p95 ≤ 87 ms for list, search,
  dashboard and performance endpoints (budget 0.8-1.0 s).
* Recovery drill: see `operations.md`.
* Malware scanning: EICAR test file detected by ClamAV through the application scanner.

Not done: load testing with concurrent users at district scale, penetration testing,
screen-reader testing with real assistive technology users.
