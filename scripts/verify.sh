#!/usr/bin/env bash
# Run every automated check. Integration and E2E steps need the dev stack:
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
# E2E additionally needs demo data and E2E_PASSWORD / E2E_TOTP_SECRETS (see docs/testing.md).
# Usage: ./scripts/verify.sh [--no-services]
set -euo pipefail
cd "$(dirname "$0")/.."
WITH_SERVICES=1
[ "${1:-}" = "--no-services" ] && WITH_SERVICES=0
step() { printf '\n==> %s\n' "$*"; }

step "Backend: lint, format, types"
(cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy app)
step "Backend: unit tests"
(cd backend && .venv/bin/pytest tests/unit -q -p no:warnings)
if [ "$WITH_SERVICES" = 1 ]; then
  step "Backend: integration, authorization matrix, security and performance tests"
  (cd backend && .venv/bin/pytest tests/integration -q -p no:warnings)
fi
step "Frontend: lint, types, unit tests, production build"
(cd frontend && npx eslint . && npx tsc -b && npx vitest run && npx vite build >/dev/null)
step "Frontend: production bundle hygiene"
if grep -q "Illustrative content only" frontend/dist/assets/*.js; then echo "Dev-only content in bundle" >&2; exit 1; fi
if ls frontend/dist/assets/*.map >/dev/null 2>&1; then echo "Source maps in bundle" >&2; exit 1; fi
echo ok
if [ "$WITH_SERVICES" = 1 ] && [ -n "${E2E_PASSWORD:-}" ]; then
  step "End-to-end tests (Playwright against the running stack)"
  (cd frontend && npx playwright test)
elif [ "$WITH_SERVICES" = 1 ]; then
  echo "Skipping E2E: set E2E_PASSWORD and E2E_TOTP_SECRETS (docs/testing.md)."
fi
step "All checks passed"
