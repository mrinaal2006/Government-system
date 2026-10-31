# ADR 0001: Modular monolith with separately deployable workers

**Status:** Accepted (Phase 1)

**Context.** Twelve functional modules, one district-level deployment, a small
operations team, and strong needs for transactional consistency (assignment,
status history, audit) across modules.

**Decision.** One FastAPI application and one Celery worker image built from the
same codebase. Modules are packages under `app/modules/` with their own PostgreSQL
schema, service layer and router. Modules interact through service functions, not
each other's tables.

**Consequences.** Single deployment and single transaction boundary; no network
calls between modules; clear seams for extraction later if load or ownership ever
demands it. The trade-off is that boundaries are enforced by convention and review
rather than by the network, so they are documented in `docs/architecture.md`.
