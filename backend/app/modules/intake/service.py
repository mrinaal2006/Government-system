"""Import processing: provenance, duplicate prevention and row-level results."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError
from app.core.request_meta import RequestMeta
from app.infra import storage
from app.modules.administration.models import GrievanceSource, IssueCategory
from app.modules.audit import service as audit
from app.modules.geography.models import Block, Village
from app.modules.grievances import service as gsvc
from app.modules.grievances.models import GrievanceExternalReference, ImportBatch
from app.modules.iam.service import CurrentUser
from app.modules.intake.adapters import (
    AdapterError,
    DevelopmentAdapter,
    ExternalRecord,
    FileImportAdapter,
    SourceAdapter,
)

logger = logging.getLogger("app.intake")


def create_batch(
    db: Session, user: CurrentUser, source_code: str, filename: str, data: bytes, meta: RequestMeta
) -> ImportBatch:
    source = db.execute(select(GrievanceSource).where(GrievanceSource.code == source_code)).scalar_one_or_none()
    if source is None or not source.is_active:
        raise AppError("Unknown or inactive source.", code="unknown_source")
    if len(data) > 20 * 1024 * 1024:
        raise AppError("Import files may be at most 20 MB.", code="file_too_large")
    if not filename.lower().endswith((".csv", ".xlsx")):
        raise AppError("Only .csv and .xlsx files are accepted.", code="file_type_not_allowed")
    digest = hashlib.sha256(data).hexdigest()
    if db.execute(
        select(ImportBatch.id).where(ImportBatch.source_id == source.id, ImportBatch.file_sha256 == digest)
    ).first():
        raise ConflictError("This exact file has already been imported for this source.", code="duplicate_file")
    batch_id = uuid.uuid4()
    key = f"imports/{batch_id}/{gsvc.sanitize_filename(filename)}"
    storage.put_bytes(key, data, "application/octet-stream")
    b = ImportBatch(
        id=batch_id,
        source_id=source.id,
        adapter="file_import",
        filename=gsvc.sanitize_filename(filename),
        file_sha256=digest,
        storage_key=key,
        uploaded_by=user.id,
    )
    db.add(b)
    db.flush()
    audit.record(
        db,
        action="intake.import_uploaded",
        actor=user.actor,
        resource_type="import_batch",
        resource_id=b.id,
        details={"source": source.code, "sha256": digest},
        meta=meta,
    )
    return b


def _resolve(db: Session, rec: ExternalRecord) -> tuple[dict[str, Any], list[str]]:
    warnings = list(rec.warnings)
    out: dict[str, Any] = {}
    if rec.category_code:
        cat = db.execute(
            select(IssueCategory).where(IssueCategory.code == rec.category_code.upper())
        ).scalar_one_or_none()
        if cat:
            if cat.parent_id:
                out["category_id"], out["subcategory_id"] = cat.parent_id, cat.id
            else:
                out["category_id"] = cat.id
        else:
            warnings.append(f"unknown category_code '{rec.category_code[:50]}' left unclassified")
    for level, model, code, name in (
        ("village", Village, rec.village_lgd_code, rec.village_name),
        ("block", Block, rec.block_lgd_code, rec.block_name),
    ):
        unit = None
        if code:
            unit = db.execute(select(model).where(model.lgd_code == code)).scalar_one_or_none()
        elif name:
            hits = db.execute(select(model).where(func.lower(model.name_en) == name.strip().lower())).scalars().all()
            unit = hits[0] if len(hits) == 1 else None
            if len(hits) > 1:
                warnings.append(f"{level} name '{name[:50]}' is ambiguous; not set")
        if unit:
            out[f"{level}_id"] = unit.id
        elif code or name:
            warnings.append(f"{level} '{(code or name or '')[:50]}' not found; not set")
    if out.get("village_id") and out.get("block_id"):
        v = db.get(Village, out["village_id"])
        if v and v.block_id and v.block_id != out["block_id"]:
            warnings.append("village does not belong to the given block; block ignored")
            out.pop("block_id")
    return out, warnings


def process_batch(
    db: Session,
    batch_id: uuid.UUID,
    *,
    adapter: SourceAdapter | None = None,
    user: CurrentUser | None = None,
) -> ImportBatch:
    b = db.get(ImportBatch, batch_id, with_for_update=True)
    if b is None:
        raise AppError("Unknown import batch.")
    if b.status in ("completed", "processing"):
        return b
    b.status = "processing"
    db.flush()
    from app.modules.iam.models import User

    uploader = db.get(User, b.uploaded_by)
    actor = audit.Actor(uploader.id, uploader.username) if uploader else audit.SYSTEM_ACTOR
    errors: list[dict[str, Any]] = []
    try:
        adapter = adapter or FileImportAdapter(b.filename, storage.get_bytes(b.storage_key or ""))
        for rec in adapter.records():
            b.total_rows += 1
            if not rec.external_id:
                b.failed_count += 1
                errors.append({"row": rec.row_number, "error": "external_id is required"})
                continue
            if db.execute(
                select(GrievanceExternalReference.id).where(
                    GrievanceExternalReference.source_id == b.source_id,
                    GrievanceExternalReference.external_id == rec.external_id,
                )
            ).first():
                b.duplicate_count += 1
                continue
            resolved, warnings = _resolve(db, rec)
            try:
                with db.begin_nested():
                    priority = (
                        rec.priority.lower()
                        if rec.priority and rec.priority.lower() in ("low", "normal", "high", "urgent")
                        else "normal"
                    )
                    g = gsvc.register(
                        db,
                        None,
                        source_id=b.source_id,
                        subject=(rec.subject or rec.description[:120]).strip() or "Imported grievance",
                        description=rec.description,
                        received_at=rec.received_at,
                        category_id=resolved.get("category_id"),
                        subcategory_id=resolved.get("subcategory_id"),
                        department_id=None,
                        priority=priority,
                        location=gsvc.LocationInput(
                            block_id=resolved.get("block_id"), village_id=resolved.get("village_id")
                        ),
                        location_text=rec.location_text,
                        complainant=gsvc.ComplainantInput(
                            name=rec.complainant_name,
                            mobile=rec.complainant_mobile,
                            address=rec.complainant_address,
                        ),
                        external_id=rec.external_id,
                        import_batch_id=b.id,
                        actor_override=actor,
                    )
                    g.created_by = b.uploaded_by
                b.created_count += 1
                if warnings:
                    errors.append({"row": rec.row_number, "warnings": warnings})
            except AppError as exc:
                b.failed_count += 1
                errors.append({"row": rec.row_number, "error": exc.message})
        b.status = "completed"
    except AdapterError as exc:
        b.status = "failed"
        errors.append({"row": None, "error": str(exc)})
    b.errors = errors[:1000]
    b.completed_at = datetime.now(UTC)
    audit.record(
        db,
        action="intake.import_processed",
        actor=actor,
        resource_type="import_batch",
        resource_id=b.id,
        details={
            "status": b.status,
            "total": b.total_rows,
            "created": b.created_count,
            "duplicates": b.duplicate_count,
            "failed": b.failed_count,
        },
    )
    return b


def run_development_adapter(
    db: Session, user: CurrentUser, source_code: str, count: int, meta: RequestMeta
) -> ImportBatch:
    adapter = DevelopmentAdapter(count)  # raises outside development
    source = db.execute(select(GrievanceSource).where(GrievanceSource.code == source_code)).scalar_one_or_none()
    if source is None:
        raise AppError("Unknown source.", code="unknown_source")
    b = ImportBatch(
        source_id=source.id,
        adapter="development_adapter",
        filename="(synthetic development data)",
        file_sha256=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        uploaded_by=user.id,
    )
    db.add(b)
    db.flush()
    return process_batch(db, b.id, adapter=adapter)
