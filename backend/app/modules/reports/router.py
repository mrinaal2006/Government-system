from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.auth import DbDep, require
from app.core.errors import AppError, NotFoundError
from app.core.request_meta import RequestMeta
from app.infra import storage
from app.modules.audit import service as audit
from app.modules.iam.service import CurrentUser
from app.modules.reports.models import ReportJob

router = APIRouter(prefix="/reports", tags=["reports"])
Generator = Annotated[CurrentUser, Depends(require("report.generate"))]
Exporter = Annotated[CurrentUser, Depends(require("report.export"))]


class ReportParams(BaseModel):
    since: datetime | None = None
    until: datetime | None = None
    open_only: bool = False
    category_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    block_id: uuid.UUID | None = None
    include_pii: bool = False


class ReportIn(BaseModel):
    report_type: Literal["grievance_register", "department_performance", "block_summary", "executive_summary"]
    format: Literal["pdf", "xlsx"]
    parameters: ReportParams = Field(default_factory=ReportParams)


def _out(j: ReportJob) -> dict[str, Any]:
    return {
        "id": str(j.id),
        "report_type": j.report_type,
        "format": j.format,
        "status": j.status,
        "parameters": j.parameters,
        "created_at": j.created_at,
        "completed_at": j.completed_at,
        "expires_at": j.expires_at,
        "row_count": j.row_count,
        "filename": j.filename,
        "error": j.error,
    }


@router.post("", status_code=202)
def create(body: ReportIn, request: Request, cu: Generator, db: DbDep) -> dict[str, Any]:
    if body.parameters.include_pii and not cu.has("citizen.read"):
        raise AppError("You are not authorised to include complainant personal data.", code="pii_not_permitted")
    j = ReportJob(
        report_type=body.report_type,
        format=body.format,
        parameters=body.parameters.model_dump(mode="json"),
        requested_by=cu.id,
    )
    db.add(j)
    db.flush()
    audit.record(
        db,
        action="report.requested",
        actor=cu.actor,
        resource_type="report",
        resource_id=j.id,
        details={
            "type": body.report_type,
            "format": body.format,
            "include_pii": body.parameters.include_pii,
        },
        meta=RequestMeta.from_request(request),
    )
    db.commit()
    try:
        from app.worker.tasks import generate_report

        generate_report.delay(str(j.id))
    except Exception:  # noqa: BLE001 - the periodic sweep picks up queued jobs
        logging.getLogger("app.queue").warning("enqueue_failed", extra={"task": "generate_report"})
    return _out(j)


@router.get("")
def list_jobs(cu: Generator, db: DbDep) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ReportJob).where(ReportJob.requested_by == cu.id).order_by(ReportJob.created_at.desc()).limit(50)
    ).scalars()
    return [_out(j) for j in rows]


@router.get("/{job_id}")
def get_job(job_id: uuid.UUID, cu: Generator, db: DbDep) -> dict[str, Any]:
    j = db.get(ReportJob, job_id)
    if j is None or j.requested_by != cu.id:
        raise NotFoundError()
    return _out(j)


@router.get("/{job_id}/download")
def download(job_id: uuid.UUID, request: Request, cu: Exporter, db: DbDep) -> StreamingResponse:
    j = db.get(ReportJob, job_id)
    if j is None or j.requested_by != cu.id or j.status != "completed" or not j.storage_key:
        raise NotFoundError("Report not available.")
    if j.expires_at and j.expires_at < datetime.now(UTC):
        raise AppError("This report has expired. Generate it again.", code="report_expired")
    audit.record(
        db,
        action="report.downloaded",
        actor=cu.actor,
        resource_type="report",
        resource_id=j.id,
        meta=RequestMeta.from_request(request),
    )
    db.commit()
    media = (
        "application/pdf" if j.format == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return StreamingResponse(
        storage.get_stream(j.storage_key),
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{j.filename}"',
            "Cache-Control": "no-store",
        },
    )
