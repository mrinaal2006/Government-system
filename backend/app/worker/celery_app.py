"""Celery application for background processing (AI jobs, imports, reports, SLA scans).

Run: ``celery -A app.worker.celery_app worker --loglevel=INFO``
"""

from __future__ import annotations

from celery import Celery
from celery.signals import setup_logging

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()

celery_app = Celery(
    "dgimews",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend_url,
    include=["app.worker.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],  # never pickle: tasks must not deserialize arbitrary objects
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=600,
    task_soft_time_limit=540,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,
)


@setup_logging.connect
def _configure_worker_logging(**_: object) -> None:
    configure_logging(settings)


app = celery_app
