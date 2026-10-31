#!/usr/bin/env bash
# Run every Phase 1 check. Requires the dev stack for integration and E2E tests:
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
# Usage: ./scripts/verify.sh [--no-services]   (skip integration + E2E)
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
  step "Backend: integration tests (PostgreSQL/PostGIS, Redis, Celery)"
  (cd backend && .venv/bin/pytest tests/integration -q -p no:warnings)
fi

step "Frontend: lint, types, unit tests, production build"
(cd frontend && npx eslint . && npx tsc -b && npx vitest run && npx vite build >/dev/null)

step "Frontend: production bundle hygiene"
if grep -q "Illustrative content only" frontend/dist/assets/*.js; then
  echo "Development-only content found in production bundle" >&2; exit 1
fi
if ls frontend/dist/assets/*.map >/dev/null 2>&1; then
  echo "Source maps found in production bundle" >&2; exit 1
fi
echo "ok"

if [ "$WITH_SERVICES" = 1 ]; then
  step "End-to-end tests (Playwright against the running stack)"
  (cd frontend && npx playwright test)
fi

step "All checks passed"
