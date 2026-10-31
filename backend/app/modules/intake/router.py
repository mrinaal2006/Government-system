from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.auth import DbDep, require
from app.api.common import Page, paging
from app.core.config import Environment, get_settings
from app.core.errors import NotFoundError
from app.core.request_meta import RequestMeta
from app.modules.administration.models import GrievanceSource
from app.modules.grievances.models import ImportBatch
from app.modules.iam.service import CurrentUser
from app.modules.intake import service
from app.modules.intake.adapters import KNOWN_COLUMNS, REQUIRED_COLUMNS

router = APIRouter(prefix="/intake", tags=["intake"])
Importer = Annotated[CurrentUser, Depends(require("grievance.import"))]


class BatchOut(BaseModel):
    id: uuid.UUID
    source_code: str
    adapter: str
    filename: str
    status: str
    total_rows: int
    created_count: int
    duplicate_count: int
    failed_count: int
    errors: list[Any]
    created_at: datetime
    completed_at: datetime | None


def _out(db: DbDep, b: ImportBatch) -> BatchOut:
    code = db.execute(select(GrievanceSource.code).where(GrievanceSource.id == b.source_id)).scalar_one()
    return BatchOut(
        id=b.id,
        source_code=code,
        adapter=b.adapter,
        filename=b.filename,
        status=b.status,
        total_rows=b.total_rows,
        created_count=b.created_count,
        duplicate_count=b.duplicate_count,
        failed_count=b.failed_count,
        errors=b.errors,
        created_at=b.created_at,
        completed_at=b.completed_at,
    )


@router.get("/adapters")
def adapters(cu: Importer, db: DbDep) -> dict[str, Any]:
    sources = db.execute(
        select(GrievanceSource).where(GrievanceSource.is_active.is_(True)).order_by(GrievanceSource.name_en)
    ).scalars()
    return {
        "file_import": {
            "required_columns": sorted(REQUIRED_COLUMNS),
            "optional_columns": sorted(KNOWN_COLUMNS - REQUIRED_COLUMNS),
            "formats": ["csv (UTF-8)", "xlsx"],
            "max_rows": 20000,
        },
        "development_adapter_available": get_settings().app_env == Environment.DEVELOPMENT,
        "live_integrations": [],
        "sources": [{"code": s.code, "name": s.name_en, "integration_mode": s.integration_mode} for s in sources],
    }


@router.post("/imports", response_model=BatchOut, status_code=202)
async def upload(
    request: Request,
    cu: Importer,
    db: DbDep,
    source_code: Annotated[str, Form(max_length=50)],
    file: Annotated[UploadFile, File()],
) -> BatchOut:
    from starlette.concurrency import run_in_threadpool

    data = await file.read(20 * 1024 * 1024 + 1)
    b = await run_in_threadpool(
        service.create_batch,
        db,
        cu,
        source_code,
        file.filename or "import",
        data,
        RequestMeta.from_request(request),
    )
    db.commit()
    try:
        from app.worker.tasks import process_import

        process_import.delay(str(b.id))
    except Exception:  # noqa: BLE001 - processed by the periodic sweep if the queue is down
        logging.getLogger("app.queue").warning("enqueue_failed", extra={"task": "process_import"})
    return _out(db, b)


class DevRun(BaseModel):
    source_code: str
    count: int = Field(default=5, ge=1, le=50)


@router.post("/development-adapter/run", response_model=BatchOut)
def run_dev(body: DevRun, request: Request, cu: Importer, db: DbDep) -> BatchOut:
    return _out(
        db,
        service.run_development_adapter(db, cu, body.source_code, body.count, RequestMeta.from_request(request)),
    )


@router.get("/imports", response_model=Page[BatchOut])
def list_batches(cu: Importer, db: DbDep, pg: Annotated[tuple[int, int], Depends(paging)]) -> Page[BatchOut]:
    stmt = select(ImportBatch)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(ImportBatch.created_at.desc()).limit(pg[0]).offset(pg[1])).scalars()
    return Page(items=[_out(db, b) for b in rows], total=total, limit=pg[0], offset=pg[1])


@router.get("/imports/{batch_id}", response_model=BatchOut)
def get_batch(batch_id: uuid.UUID, cu: Importer, db: DbDep) -> BatchOut:
    b = db.get(ImportBatch, batch_id)
    if b is None:
        raise NotFoundError()
    return _out(db, b)
