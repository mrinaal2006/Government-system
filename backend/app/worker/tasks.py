"""Background tasks. Domain tasks are added by their owning modules in later phases."""

from __future__ import annotations

from datetime import UTC, datetime

from app.worker.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping() -> dict[str, str]:
    """Round-trip check used to verify the broker, worker and result backend."""
    return {"status": "pong", "at": datetime.now(UTC).isoformat()}
