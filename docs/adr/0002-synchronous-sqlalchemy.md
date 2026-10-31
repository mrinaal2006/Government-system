# ADR 0002: Synchronous SQLAlchemy 2.0 with psycopg 3

**Status:** Accepted (Phase 1)

**Context.** The API, Celery workers and Alembic all access the database. Async
SQLAlchemy would require a second driver/code path for Celery (synchronous) and
Alembic.

**Decision.** Use synchronous SQLAlchemy 2.0 with psycopg 3 everywhere. FastAPI
runs sync endpoints and dependencies in its thread pool. Pool size, overflow,
timeouts and statement timeouts are configured explicitly.

**Consequences.** One data-access code path, identical behaviour in API and
workers, simpler transactions and testing. Throughput is bounded by thread pool and
connection pool sizing, which is ample for district-level load; long-running work
belongs in Celery regardless. Revisit only with measured evidence.
