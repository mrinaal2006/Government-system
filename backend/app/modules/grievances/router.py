"""Grievance API (/grievances)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.api.auth import CurrentUserDep, DbDep, require
from app.api.common import Page, paging
from app.core.config import get_settings
from app.core.request_meta import RequestMeta
from app.infra import storage
from app.modules.administration.models import Department, GrievanceSource, IssueCategory
from app.modules.geography.models import (
    Block,
    District,
    GramPanchayat,
    Municipality,
    Subdivision,
    Village,
    Ward,
)
from app.modules.grievances import service
from app.modules.grievances.models import (
    OPEN_STATUSES,
    PRIORITIES,
    Grievance,
    GrievanceAssignment,
    GrievanceAttachment,
    GrievanceComment,
    GrievanceExternalReference,
    GrievanceRelationship,
    GrievanceStatusHistory,
)
from app.modules.iam.models import User
from app.modules.iam.service import CurrentUser

router = APIRouter(prefix="/grievances", tags=["grievances"])

Reader = Annotated[CurrentUser, Depends(require("grievance.read"))]


class ComplainantIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    mobile: str | None = Field(default=None, pattern=r"^\+?[0-9 ]{10,15}$")
    email: str | None = Field(default=None, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    address: str | None = Field(default=None, max_length=1000)
    consent_recorded: bool = False


class LocationIn(BaseModel):
    district_id: uuid.UUID | None = None
    subdivision_id: uuid.UUID | None = None
    block_id: uuid.UUID | None = None
    gram_panchayat_id: uuid.UUID | None = None
    village_id: uuid.UUID | None = None
    municipality_id: uuid.UUID | None = None
    ward_id: uuid.UUID | None = None


class GrievanceCreate(BaseModel):
    source_id: uuid.UUID
    subject: str = Field(min_length=5, max_length=300)
    description: str = Field(min_length=10, max_length=20_000)
    received_at: datetime | None = None
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    location: LocationIn = Field(default_factory=LocationIn)
    location_text: str | None = Field(default=None, max_length=500)
    complainant: ComplainantIn | None = None
    external_id: str | None = Field(default=None, max_length=200)

    @field_validator("received_at")
    @classmethod
    def _not_future(cls, v: datetime | None) -> datetime | None:
        if v is not None:
            if v.tzinfo is None:
                raise ValueError("received_at must include a timezone")
            if v > service.now():
                raise ValueError("received_at cannot be in the future")
        return v


class GrievanceListItem(BaseModel):
    id: uuid.UUID
    reference_no: str
    subject: str
    status: str
    priority: str
    category: str | None
    department: str | None
    block: str | None
    village: str | None
    assigned_officer: str | None
    source: str | None
    registered_at: datetime
    due_at: datetime | None
    overdue: bool
    risk_level: str | None
    escalation_level: int
    reopened_count: int


class Versioned(BaseModel):
    version: int = Field(ge=1)


class UpdateIn(Versioned):
    changes: dict[str, Any]
    reason: str | None = Field(default=None, max_length=1000)


class AssignIn(Versioned):
    officer_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=1000)


class TransitionIn(Versioned):
    action: Literal[
        "start_work",
        "submit_resolution",
        "accept_resolution",
        "return_resolution",
        "close",
        "reopen",
    ]
    note: str | None = Field(default=None, max_length=10_000)


class EscalateIn(Versioned):
    reason: str = Field(min_length=10, max_length=2000)


class CommentIn(BaseModel):
    kind: Literal["comment", "investigation"] = "comment"
    body: str = Field(min_length=1, max_length=10_000)


class LinkIn(BaseModel):
    related_grievance_id: uuid.UUID
    relation_type: Literal["duplicate_of", "related", "follow_up"]
    note: str | None = Field(default=None, max_length=1000)


class ExternalRefIn(BaseModel):
    source_id: uuid.UUID
    external_id: str = Field(min_length=1, max_length=200)


def _meta(request: Request) -> RequestMeta:
    return RequestMeta.from_request(request)


@router.get("", response_model=Page[GrievanceListItem])
def search(
    cu: Reader,
    db: DbDep,
    pg: Annotated[tuple[int, int], Depends(paging)],
    q: str | None = Query(None, max_length=200),
    status: Annotated[list[str] | None, Query()] = None,
    priority: Annotated[list[str] | None, Query()] = None,
    category_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    district_id: uuid.UUID | None = None,
    block_id: uuid.UUID | None = None,
    village_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    assigned_to_me: bool = False,
    overdue: bool | None = None,
    open_only: bool = False,
    escalated: bool | None = None,
    risk_level: Annotated[list[str] | None, Query()] = None,
    registered_from: datetime | None = None,
    registered_to: datetime | None = None,
    sort: Literal["registered_at", "due_at", "priority", "status", "reference_no"] = "registered_at",
    order: Literal["asc", "desc"] = "desc",
) -> Page[GrievanceListItem]:
    f = service.SearchFilters(
        q=q,
        status=status,
        priority=priority,
        category_id=category_id,
        department_id=department_id,
        district_id=district_id,
        block_id=block_id,
        village_id=village_id,
        source_id=source_id,
        assigned_to_me=assigned_to_me,
        overdue=overdue,
        open_only=open_only,
        escalated=escalated,
        risk_level=risk_level,
        registered_from=registered_from,
        registered_to=registered_to,
        sort=sort,
        order=order,
    )
    rows, total = service.list_rows(db, cu, f, pg[0], pg[1])
    return Page(items=[GrievanceListItem(**r) for r in rows], total=total, limit=pg[0], offset=pg[1])


@router.post("", status_code=201)
def create(
    body: GrievanceCreate,
    request: Request,
    cu: Annotated[CurrentUser, Depends(require("grievance.create"))],
    db: DbDep,
) -> dict[str, Any]:
    g = service.register(
        db,
        cu,
        source_id=body.source_id,
        subject=body.subject,
        description=body.description,
        received_at=body.received_at,
        category_id=body.category_id,
        subcategory_id=body.subcategory_id,
        department_id=body.department_id,
        priority=body.priority,
        location=service.LocationInput(**body.location.model_dump()),
        location_text=body.location_text,
        complainant=service.ComplainantInput(**body.complainant.model_dump()) if body.complainant else None,
        external_id=body.external_id,
        meta=_meta(request),
    )
    from app.modules.intelligence import service as intel

    candidates = intel.find_duplicates(db, g)
    db.flush()
    intel.enqueue_analysis(g.id)
    return {
        "id": str(g.id),
        "reference_no": g.reference_no,
        "status": g.status,
        "due_at": g.due_at,
        "possible_duplicates": [
            {"grievance_id": str(c.candidate_grievance_id), "similarity": float(c.similarity)} for c in candidates
        ],
    }


def _names(db: DbDep, g: Grievance) -> dict[str, Any]:
    def name(model: Any, ident: uuid.UUID | None) -> dict[str, Any] | None:
        if ident is None:
            return None
        obj = db.get(model, ident)
        return (
            {
                "id": str(ident),
                "name": getattr(obj, "name_en", None) or getattr(obj, "full_name", None),
            }
            if obj
            else None
        )

    ward = db.get(Ward, g.ward_id) if g.ward_id else None
    return {
        "source": name(GrievanceSource, g.source_id),
        "category": name(IssueCategory, g.category_id),
        "subcategory": name(IssueCategory, g.subcategory_id),
        "department": name(Department, g.department_id),
        "district": name(District, g.district_id),
        "subdivision": name(Subdivision, g.subdivision_id),
        "block": name(Block, g.block_id),
        "gram_panchayat": name(GramPanchayat, g.gram_panchayat_id),
        "village": name(Village, g.village_id),
        "municipality": name(Municipality, g.municipality_id),
        "ward": {"id": str(ward.id), "name": f"Ward {ward.ward_number}"} if ward else None,
        "assigned_officer": name(User, g.assigned_officer_id),
        "created_by": name(User, g.created_by),
    }


@router.get("/{grievance_id}")
def detail(grievance_id: uuid.UUID, request: Request, cu: Reader, db: DbDep) -> dict[str, Any]:
    from app.modules.intelligence.models import RiskAssessment
    from app.modules.performance.models import Escalation, SlaEvent

    g = service.get_scoped(db, cu, grievance_id)
    risk = db.execute(
        select(RiskAssessment).where(RiskAssessment.grievance_id == g.id, RiskAssessment.is_current.is_(True))
    ).scalar_one_or_none()
    t = service.now()
    return {
        "id": str(g.id),
        "reference_no": g.reference_no,
        "subject": g.subject,
        "description": g.description,
        "summary": g.summary,
        "status": g.status,
        "priority": g.priority,
        "received_at": g.received_at,
        "registered_at": g.registered_at,
        "status_changed_at": g.status_changed_at,
        "due_at": g.due_at,
        "overdue": bool(g.due_at and g.due_at < t and g.status in OPEN_STATUSES),
        "resolution_summary": g.resolution_summary,
        "resolved_at": g.resolved_at,
        "closed_at": g.closed_at,
        "reopened_count": g.reopened_count,
        "escalation_level": g.escalation_level,
        "location_text": g.location_text,
        "duplicate_of_id": str(g.duplicate_of_id) if g.duplicate_of_id else None,
        "version": g.version,
        **_names(db, g),
        "complainant": service.complainant_view(db, cu, g.complainant_id, gid=g.id, meta=_meta(request)),
        "risk": {
            "level": risk.level,
            "score": float(risk.score),
            "factors": risk.factors,
            "model_version": risk.risk_model_version,
            "assessed_at": risk.assessed_at,
        }
        if risk
        else None,
        "sla_events": [
            {"event_type": e.event_type, "occurred_at": e.occurred_at, "cycle": e.cycle}
            for e in db.execute(
                select(SlaEvent).where(SlaEvent.grievance_id == g.id).order_by(SlaEvent.occurred_at)
            ).scalars()
        ],
        "escalations": [
            {"level": e.level, "trigger": e.trigger, "reason": e.reason, "created_at": e.created_at}
            for e in db.execute(
                select(Escalation).where(Escalation.grievance_id == g.id).order_by(Escalation.created_at)
            ).scalars()
        ],
        "allowed_actions": service.allowed_actions(cu, g),
    }


@router.get("/{grievance_id}/history")
def history(grievance_id: uuid.UUID, cu: Reader, db: DbDep) -> dict[str, Any]:
    g = service.get_scoped(db, cu, grievance_id)
    actor = aliased(User)
    statuses = db.execute(
        select(GrievanceStatusHistory, actor.full_name)
        .outerjoin(actor, actor.id == GrievanceStatusHistory.actor_user_id)
        .where(GrievanceStatusHistory.grievance_id == g.id)
        .order_by(GrievanceStatusHistory.occurred_at)
    ).all()
    officer, by = aliased(User), aliased(User)
    assignments = db.execute(
        select(GrievanceAssignment, officer.full_name, by.full_name)
        .join(officer, officer.id == GrievanceAssignment.officer_user_id)
        .join(by, by.id == GrievanceAssignment.assigned_by)
        .where(GrievanceAssignment.grievance_id == g.id)
        .order_by(GrievanceAssignment.assigned_at)
    ).all()
    author = aliased(User)
    comments = db.execute(
        select(GrievanceComment, author.full_name)
        .join(author, author.id == GrievanceComment.author_user_id)
        .where(GrievanceComment.grievance_id == g.id)
        .order_by(GrievanceComment.created_at)
    ).all()
    return {
        "status_history": [
            {
                "from_status": s.from_status,
                "to_status": s.to_status,
                "action": s.action,
                "reason": s.reason,
                "actor": name,
                "occurred_at": s.occurred_at,
            }
            for s, name in statuses
        ],
        "assignments": [
            {
                "officer": o,
                "assigned_by": b,
                "assigned_at": a.assigned_at,
                "ended_at": a.ended_at,
                "reason": a.reason,
            }
            for a, o, b in assignments
        ],
        "comments": [
            {
                "id": str(c.id),
                "kind": c.kind,
                "body": c.body,
                "author": name,
                "created_at": c.created_at,
            }
            for c, name in comments
        ],
        "attachments": [
            {
                "id": str(a.id),
                "filename": a.filename,
                "content_type": a.content_type,
                "size_bytes": a.size_bytes,
                "scan_status": a.scan_status,
                "uploaded_at": a.uploaded_at,
            }
            for a in db.execute(
                select(GrievanceAttachment)
                .where(GrievanceAttachment.grievance_id == g.id)
                .order_by(GrievanceAttachment.uploaded_at)
            ).scalars()
        ],
        "external_references": [
            {
                "source_id": str(e.source_id),
                "external_id": e.external_id,
                "recorded_at": e.recorded_at,
            }
            for e in db.execute(
                select(GrievanceExternalReference).where(GrievanceExternalReference.grievance_id == g.id)
            ).scalars()
        ],
        "relationships": [
            {
                "related_grievance_id": str(r.related_grievance_id),
                "relation_type": r.relation_type,
                "note": r.note,
                "created_at": r.created_at,
            }
            for r in db.execute(
                select(GrievanceRelationship).where(GrievanceRelationship.grievance_id == g.id)
            ).scalars()
        ],
    }


@router.patch("/{grievance_id}")
def update_details(
    grievance_id: uuid.UUID,
    body: UpdateIn,
    request: Request,
    cu: Annotated[CurrentUser, Depends(require("grievance.update"))],
    db: DbDep,
) -> dict[str, Any]:
    changes = dict(body.changes)
    if "priority" in changes and changes["priority"] not in PRIORITIES:
        from app.core.errors import AppError

        raise AppError("Invalid priority.", code="invalid_priority")
    for k, v in list(changes.items()):
        if k.endswith("_id") and v is not None:
            changes[k] = uuid.UUID(str(v))
    g = service.update_details(db, cu, grievance_id, changes, body.version, _meta(request), reason=body.reason)
    return {"id": str(g.id), "version": g.version}


@router.post("/{grievance_id}/assign")
def assign(
    grievance_id: uuid.UUID,
    body: AssignIn,
    request: Request,
    cu: Annotated[CurrentUser, Depends(require("grievance.assign"))],
    db: DbDep,
) -> dict[str, Any]:
    g = service.assign(db, cu, grievance_id, body.officer_id, body.version, body.reason, _meta(request))
    return {"id": str(g.id), "status": g.status, "version": g.version}


@router.post("/{grievance_id}/transition")
def transition(
    grievance_id: uuid.UUID, body: TransitionIn, request: Request, cu: CurrentUserDep, db: DbDep
) -> dict[str, Any]:
    g = service.transition(db, cu, grievance_id, body.action, body.version, body.note, _meta(request))
    return {"id": str(g.id), "status": g.status, "version": g.version}


@router.post("/{grievance_id}/escalate")
def escalate(
    grievance_id: uuid.UUID,
    body: EscalateIn,
    request: Request,
    cu: Annotated[CurrentUser, Depends(require("grievance.escalate"))],
    db: DbDep,
) -> dict[str, Any]:
    g = service.escalate(db, cu, grievance_id, body.reason, body.version, _meta(request))
    return {"id": str(g.id), "escalation_level": g.escalation_level, "version": g.version}


@router.post("/{grievance_id}/comments", status_code=201)
def comment(
    grievance_id: uuid.UUID,
    body: CommentIn,
    request: Request,
    cu: Annotated[CurrentUser, Depends(require("grievance.comment"))],
    db: DbDep,
) -> dict[str, Any]:
    c = service.add_comment(db, cu, grievance_id, body.kind, body.body, _meta(request))
    return {"id": str(c.id)}


@router.post("/{grievance_id}/links", status_code=201)
def link(
    grievance_id: uuid.UUID,
    body: LinkIn,
    request: Request,
    cu: Annotated[CurrentUser, Depends(require("grievance.link"))],
    db: DbDep,
) -> dict[str, Any]:
    r = service.link(
        db,
        cu,
        grievance_id,
        body.related_grievance_id,
        body.relation_type,
        body.note,
        _meta(request),
    )
    return {"id": str(r.id)}


@router.post("/{grievance_id}/external-references", status_code=201)
def external_reference(
    grievance_id: uuid.UUID,
    body: ExternalRefIn,
    request: Request,
    cu: Annotated[CurrentUser, Depends(require("grievance.update"))],
    db: DbDep,
) -> dict[str, Any]:
    from app.modules.audit import service as audit

    g = service.get_scoped(db, cu, grievance_id)
    service.add_external_reference(db, g, body.source_id, body.external_id, cu.id)
    audit.record(
        db,
        action="grievance.external_reference_added",
        actor=cu.actor,
        resource_type="grievance",
        resource_id=g.id,
        details={"source_id": str(body.source_id)},
        meta=_meta(request),
    )
    return {"ok": True}


@router.post("/{grievance_id}/attachments", status_code=201)
async def upload(
    grievance_id: uuid.UUID,
    request: Request,
    cu: Annotated[CurrentUser, Depends(require("grievance.attach"))],
    db: DbDep,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    limit = get_settings().upload_max_bytes
    data = await file.read(limit + 1)
    from starlette.concurrency import run_in_threadpool

    att = await run_in_threadpool(
        service.upload_attachment,
        db,
        cu,
        grievance_id,
        file.filename or "attachment",
        data,
        _meta(request),
    )
    return {
        "id": str(att.id),
        "filename": att.filename,
        "scan_status": att.scan_status,
        "sha256": att.sha256,
    }


@router.get("/{grievance_id}/attachments/{attachment_id}")
def download(
    grievance_id: uuid.UUID, attachment_id: uuid.UUID, request: Request, cu: Reader, db: DbDep
) -> StreamingResponse:
    att: GrievanceAttachment = service.attachment_for_download(db, cu, grievance_id, attachment_id, _meta(request))
    db.commit()
    return StreamingResponse(
        storage.get_stream(att.storage_key),
        media_type=att.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{att.filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{grievance_id}/officers")
def assignable_officers(
    grievance_id: uuid.UUID,
    cu: Annotated[CurrentUser, Depends(require("grievance.assign"))],
    db: DbDep,
) -> list[dict[str, Any]]:
    """Active users holding grievance.work (candidates for assignment)."""
    from app.modules.iam.models import Permission, RolePermission, UserRole

    g = service.get_scoped(db, cu, grievance_id)
    holders = (
        select(UserRole.user_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(Permission.code == "grievance.work")
    )
    rows = db.execute(
        select(User.id, User.full_name, User.designation, User.department_id, Department.name_en)
        .outerjoin(Department, Department.id == User.department_id)
        .where(User.is_active.is_(True), User.id.in_(holders))
        .order_by(User.full_name)
    ).all()
    return [
        {
            "id": str(r[0]),
            "full_name": r[1],
            "designation": r[2],
            "department": r[4],
            "same_department": r[3] == g.department_id,
        }
        for r in rows
    ]
