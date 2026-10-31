"""Background tasks. Each opens its own transaction."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.db.session import get_session_factory
from app.worker.celery_app import celery_app

logger = logging.getLogger("app.worker")


def _tx() -> Any:
    return get_session_factory().begin()


@celery_app.task(name="system.ping")
def ping() -> dict[str, str]:
    """Round-trip check used to verify the broker, worker and result backend."""
    return {"status": "pong", "at": datetime.now(UTC).isoformat()}


@celery_app.task(name="intel.analyse_grievance", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def analyse_grievance(grievance_id: str) -> dict[str, Any]:
    from app.modules.intelligence import service

    with _tx() as db:
        return service.analyse(db, uuid.UUID(grievance_id))


@celery_app.task(name="intake.process_import")
def process_import(batch_id: str) -> str:
    from app.modules.intake import service

    with _tx() as db:
        status = service.process_batch(db, uuid.UUID(batch_id)).status
    # Queue analysis for every grievance the batch created.
    with _tx() as db:
        from app.modules.grievances.models import Grievance

        ids = list(db.execute(select(Grievance.id).where(Grievance.import_batch_id == uuid.UUID(batch_id))).scalars())
    for gid in ids:
        analyse_grievance.delay(str(gid))
    return status


@celery_app.task(
    name="attachments.scan",
    autoretry_for=(LookupError, RuntimeError),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=8,
)
def scan_attachment(attachment_id: str) -> str:
    """Deferred malware scan (MALWARE_SCAN_MODE=deferred)."""
    from app.modules.grievances import service

    with _tx() as db:
        return service.scan_pending_attachment(db, uuid.UUID(attachment_id))


@celery_app.task(name="reports.generate")
def generate_report(job_id: str) -> str:
    from app.modules.reports import service

    with _tx() as db:
        return service.generate(db, uuid.UUID(job_id)).status


@celery_app.task(name="sla.scan")
def sla_scan() -> dict[str, int]:
    from app.modules.performance import service

    with _tx() as db:
        return service.scan_sla(db)


@celery_app.task(name="intel.recompute")
def recompute_intelligence() -> dict[str, int]:
    from app.modules.intelligence import service

    with _tx() as db:
        clusters = service.compute_clusters(db)
        assessed = service.assess_all_open(db)
    return {"clusters": clusters, "assessed": assessed}


@celery_app.task(name="alerts.evaluate")
def evaluate_alerts() -> dict[str, int]:
    from app.modules.early_warning import service

    recompute_intelligence()
    with _tx() as db:
        return service.evaluate(db)


@celery_app.task(name="perf.snapshot")
def performance_snapshot() -> int:
    from app.modules.performance import service

    with _tx() as db:
        return service.take_snapshots(db)


@celery_app.task(name="system.sweep")
def sweep() -> dict[str, int]:
    """Pick up imports, reports and attachment scans whose queue message was lost."""
    from app.modules.grievances.models import GrievanceAttachment, ImportBatch
    from app.modules.reports.models import ReportJob

    cutoff = datetime.now(UTC) - timedelta(minutes=2)
    with _tx() as db:
        imports = list(
            db.execute(
                select(ImportBatch.id).where(ImportBatch.status == "queued", ImportBatch.created_at < cutoff)
            ).scalars()
        )
        reports = list(
            db.execute(
                select(ReportJob.id).where(ReportJob.status == "queued", ReportJob.created_at < cutoff)
            ).scalars()
        )
    with _tx() as db:
        pending = list(
            db.execute(
                select(GrievanceAttachment.id).where(
                    GrievanceAttachment.scan_status == "pending", GrievanceAttachment.uploaded_at < cutoff
                )
            ).scalars()
        )
    for a in pending:
        scan_attachment.delay(str(a))
    for i in imports:
        process_import.delay(str(i))
    for r in reports:
        generate_report.delay(str(r))
    return {"imports": len(imports), "reports": len(reports), "attachment_scans": len(pending)}
