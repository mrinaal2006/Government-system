"""Prometheus instrumentation (request counts/latency by route template, not raw path)."""

from __future__ import annotations

import time

from prometheus_client import Counter, Gauge, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUESTS = Counter("dgimews_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram(
    "dgimews_http_request_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


class MetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = {"code": 500}

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, wrapped)
        finally:
            route = scope.get("route")
            template = getattr(route, "path", "unmatched")
            REQUESTS.labels(scope.get("method", ""), template, str(status["code"])).inc()
            LATENCY.labels(scope.get("method", ""), template).observe(time.perf_counter() - start)


COMPONENT_UP = Gauge("dgimews_component_up", "1 if the dependency is usable", ["component"])
QUEUE_LENGTH = Gauge("dgimews_celery_queue_length", "Tasks waiting in the Celery queue")
OPEN_GRIEVANCES = Gauge("dgimews_grievances_open", "Open grievances")
OVERDUE_GRIEVANCES = Gauge("dgimews_grievances_overdue", "Open grievances past their due time")
ACTIVE_ALERTS = Gauge("dgimews_alerts_active", "Active early-warning alerts", ["level"])
FAILED_JOBS = Gauge("dgimews_report_jobs_failed_24h", "Report jobs failed in the last 24 hours")


def refresh_gauges() -> None:
    """Point-in-time gauges computed at scrape time (cheap aggregate queries)."""
    from sqlalchemy import func, select, text

    from app.core.config import get_settings
    from app.db.session import get_engine, get_session_factory
    from app.infra.redis import get_redis
    from app.modules.system import service

    settings = get_settings()
    for r in [
        *service.check_database(get_engine(), settings.health_check_timeout_seconds),
        service.check_redis(get_redis()),
        service.check_storage(),
    ]:
        COMPONENT_UP.labels(r.name).set(1 if r.ok else 0)
    try:
        import redis as redis_lib

        broker = redis_lib.Redis.from_url(settings.celery_broker_url, socket_timeout=2)
        QUEUE_LENGTH.set(int(broker.llen("celery")))  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 - reported through dgimews_component_up
        QUEUE_LENGTH.set(-1)
    try:
        with get_session_factory()() as db:
            from app.modules.grievances.models import OPEN_STATUSES, Grievance

            OPEN_GRIEVANCES.set(
                db.execute(
                    select(func.count()).select_from(Grievance).where(Grievance.status.in_(OPEN_STATUSES))
                ).scalar_one()
            )
            OVERDUE_GRIEVANCES.set(
                db.execute(
                    select(func.count())
                    .select_from(Grievance)
                    .where(Grievance.status.in_(OPEN_STATUSES), Grievance.due_at < func.now())
                ).scalar_one()
            )
            for level in ("watch", "high", "critical"):
                ACTIVE_ALERTS.labels(level).set(
                    db.execute(
                        text(
                            "SELECT count(*) FROM intel.early_warning_alerts WHERE level = :l AND status IN "
                            "('open','acknowledged','investigating','escalated')"
                        ),
                        {"l": level},
                    ).scalar_one()
                )
            FAILED_JOBS.set(
                db.execute(
                    text(
                        "SELECT count(*) FROM governance.report_jobs WHERE status = 'failed' "
                        "AND created_at > now() - interval '24 hours'"
                    )
                ).scalar_one()
            )
    except Exception:  # noqa: BLE001 - database outage is also visible via component_up
        import logging

        logging.getLogger("app.metrics").warning("metric_gauges_unavailable")
