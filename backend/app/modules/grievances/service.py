"""Grievance lifecycle service.

Every state change:
* locks the grievance row (SELECT ... FOR UPDATE) and checks the client's
  ``version`` (optimistic concurrency) so two officers cannot act on stale data;
* is validated against the transition table below and the actor's permissions;
* appends to ``grievance_status_history`` and the audit log in the same transaction.
AI code has no access to these functions' write paths except through an officer's
explicit review (see intelligence.service.review_classification).
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, String, and_, cast, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from app.core import security
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.request_meta import RequestMeta
from app.infra import malware, storage
from app.modules.administration.models import Department, GrievanceSource, IssueCategory
from app.modules.audit import service as audit
from app.modules.geography.models import Block, GramPanchayat, Municipality, Village, Ward
from app.modules.grievances.models import (
    OPEN_STATUSES,
    Complainant,
    Grievance,
    GrievanceAssignment,
    GrievanceAttachment,
    GrievanceComment,
    GrievanceExternalReference,
    GrievanceRelationship,
    GrievanceStatusHistory,
    ReferenceCounter,
)
from app.modules.iam.models import User
from app.modules.iam.scope import grievance_scope
from app.modules.iam.service import CurrentUser, permission_codes
from app.modules.notifications.service import notify
from app.modules.performance import service as perf

logger = logging.getLogger("app.grievances")


class TransitionError(AppError):
    status_code = 409
    code = "invalid_transition"


# action -> (allowed from-statuses, to-status, required permission)
TRANSITIONS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "start_work": (("assigned",), "in_progress", "grievance.work"),
    "submit_resolution": (("in_progress",), "resolution_submitted", "grievance.work"),
    "accept_resolution": (("resolution_submitted",), "resolved", "grievance.verify"),
    "return_resolution": (("resolution_submitted",), "in_progress", "grievance.verify"),
    "close": (("resolved",), "closed", "grievance.verify"),
    "reopen": (("resolved", "closed"), "reopened", "grievance.reopen"),
}
ASSIGNABLE_FROM = ("registered", "assigned", "in_progress", "reopened")
REASON_REQUIRED = {"return_resolution", "reopen"}

ALLOWED_UPLOADS = {
    "application/pdf": (b"%PDF-", (".pdf",)),
    "image/png": (b"\x89PNG\r\n\x1a\n", (".png",)),
    "image/jpeg": (b"\xff\xd8\xff", (".jpg", ".jpeg")),
}


def now() -> datetime:
    return datetime.now(UTC)


# --- Scope helpers ---------------------------------------------------------------------


def in_scope(user: CurrentUser, g: Grievance) -> bool:
    for s in user.scopes:
        if (
            (s.scope_type == "district" and s.district_id and s.district_id == g.district_id)
            or (s.scope_type == "subdivision" and s.subdivision_id and s.subdivision_id == g.subdivision_id)
            or (s.scope_type == "block" and s.block_id and s.block_id == g.block_id)
            or (s.scope_type == "department" and s.department_id and s.department_id == g.department_id)
            or (s.scope_type == "assigned" and g.assigned_officer_id == user.id)
            or (s.scope_type == "own" and g.created_by == user.id)
        ):
            return True
    return False


def get_scoped(db: Session, user: CurrentUser, grievance_id: uuid.UUID, *, lock: bool = False) -> Grievance:
    stmt = select(Grievance).where(Grievance.id == grievance_id, grievance_scope(user))
    if lock:
        stmt = stmt.with_for_update(of=Grievance)
    g = db.execute(stmt).scalar_one_or_none()
    if g is None:
        raise NotFoundError("Grievance not found.")  # same response whether absent or out of scope
    return g


def _check_version(g: Grievance, version: int | None) -> None:
    if version is not None and version != g.version:
        raise ConflictError(
            "This grievance was changed by someone else. Reload and try again.",
            code="stale_version",
            details=[{"current_version": g.version}],
        )


def _bump(g: Grievance, user: CurrentUser) -> None:
    g.version += 1
    g.updated_by = user.id


# --- Registration --------------------------------------------------------------------------


def next_reference(db: Session, at: datetime) -> str:
    year = at.year
    db.execute(select(func.pg_advisory_xact_lock(771_000_100 + year)))
    counter = db.get(ReferenceCounter, year, with_for_update=True)
    if counter is None:
        counter = ReferenceCounter(year=year, last_value=0)
        db.add(counter)
        db.flush()
    counter.last_value += 1
    db.flush()
    prefix = re.sub(r"[^A-Z0-9]", "", get_settings().grievance_reference_prefix.upper())[:10] or "DGI"
    return f"{prefix}/{year}/{counter.last_value:06d}"


@dataclass
class LocationInput:
    district_id: uuid.UUID | None = None
    subdivision_id: uuid.UUID | None = None
    block_id: uuid.UUID | None = None
    gram_panchayat_id: uuid.UUID | None = None
    village_id: uuid.UUID | None = None
    municipality_id: uuid.UUID | None = None
    ward_id: uuid.UUID | None = None


def resolve_location(db: Session, loc: LocationInput) -> LocationInput:
    """Fill parent units from reference data and reject inconsistent combinations."""
    out = LocationInput(**loc.__dict__)

    def agree(field: str, value: uuid.UUID | None) -> None:
        if value is None:
            return
        current = getattr(out, field)
        if current is not None and current != value:
            raise AppError(
                "The selected locations do not belong together.",
                code="location_mismatch",
                details=[{"field": field}],
            )
        setattr(out, field, value)

    if out.ward_id:
        w = db.get(Ward, out.ward_id)
        if w is None:
            raise AppError("Unknown ward.", code="unknown_location")
        agree("municipality_id", w.municipality_id)
    if out.municipality_id:
        m = db.get(Municipality, out.municipality_id)
        if m is None:
            raise AppError("Unknown municipality.", code="unknown_location")
        agree("district_id", m.district_id)
        agree("subdivision_id", m.subdivision_id)
    if out.village_id:
        v = db.get(Village, out.village_id)
        if v is None:
            raise AppError("Unknown village.", code="unknown_location")
        agree("gram_panchayat_id", v.gram_panchayat_id)
        agree("block_id", v.block_id)
        agree("subdivision_id", v.subdivision_id)
        agree("district_id", v.district_id)
    if out.gram_panchayat_id:
        gp = db.get(GramPanchayat, out.gram_panchayat_id)
        if gp is None:
            raise AppError("Unknown gram panchayat.", code="unknown_location")
        agree("block_id", gp.block_id)
    if out.block_id:
        b = db.get(Block, out.block_id)
        if b is None:
            raise AppError("Unknown block.", code="unknown_location")
        agree("district_id", b.district_id)
        agree("subdivision_id", b.subdivision_id)
    if out.subdivision_id:
        from app.modules.geography.models import Subdivision

        sd = db.get(Subdivision, out.subdivision_id)
        if sd is None:
            raise AppError("Unknown subdivision.", code="unknown_location")
        agree("district_id", sd.district_id)
    return out


@dataclass
class ComplainantInput:
    name: str | None = None
    mobile: str | None = None
    email: str | None = None
    address: str | None = None
    consent_recorded: bool = False


def _store_complainant(db: Session, c: ComplainantInput | None) -> uuid.UUID | None:
    if c is None or not any([c.name, c.mobile, c.email, c.address]):
        return None
    row = Complainant(
        name_encrypted=security.encrypt_text(c.name),
        mobile_encrypted=security.encrypt_text(c.mobile),
        mobile_hash=security.lookup_hash(c.mobile),
        email_encrypted=security.encrypt_text(c.email),
        address_encrypted=security.encrypt_text(c.address),
        consent_recorded=c.consent_recorded,
    )
    db.add(row)
    db.flush()
    return row.id


def register(
    db: Session,
    user: CurrentUser | None,
    *,
    source_id: uuid.UUID,
    subject: str,
    description: str,
    received_at: datetime | None,
    category_id: uuid.UUID | None,
    subcategory_id: uuid.UUID | None,
    department_id: uuid.UUID | None,
    priority: str,
    location: LocationInput,
    location_text: str | None,
    complainant: ComplainantInput | None,
    external_id: str | None = None,
    import_batch_id: uuid.UUID | None = None,
    meta: RequestMeta | None = None,
    actor_override: audit.Actor | None = None,
) -> Grievance:
    source = db.get(GrievanceSource, source_id)
    if source is None or not source.is_active:
        raise AppError("Unknown or inactive grievance source.", code="unknown_source")
    if subcategory_id:
        sub = db.get(IssueCategory, subcategory_id)
        if sub is None or sub.parent_id is None or (category_id and sub.parent_id != category_id):
            raise AppError(
                "The subcategory does not belong to the selected category.",
                code="category_mismatch",
            )
        category_id = category_id or sub.parent_id
    if category_id and department_id is None:
        cat = db.get(IssueCategory, category_id)
        if cat is None:
            raise AppError("Unknown category.", code="unknown_category")
        department_id = cat.default_department_id  # configured default, not an AI decision
    loc = resolve_location(db, location)
    t = now()
    g = Grievance(
        reference_no=next_reference(db, t),
        source_id=source_id,
        received_at=received_at or t,
        registered_at=t,
        subject=subject.strip(),
        description=description.strip(),
        category_id=category_id,
        subcategory_id=subcategory_id,
        department_id=department_id,
        priority=priority,
        location_text=location_text,
        complainant_id=_store_complainant(db, complainant),
        import_batch_id=import_batch_id,
        created_by=user.id if user else None,
        status="registered",
        status_changed_at=t,
        **loc.__dict__,
    )
    if user is not None and not in_scope(user, g) and not any(s.scope_type == "own" for s in user.scopes):
        raise PermissionDeniedError("The grievance location is outside your authorised area.")
    db.add(g)
    db.flush()
    if external_id:
        add_external_reference(db, g, source_id, external_id, user.id if user else None)
    perf.apply_sla(db, g)
    db.add(
        GrievanceStatusHistory(
            grievance_id=g.id,
            from_status=None,
            to_status="registered",
            action="register",
            actor_user_id=user.id if user else None,
        )
    )
    actor = actor_override or (user.actor if user else audit.SYSTEM_ACTOR)
    audit.record(
        db,
        action="grievance.registered",
        actor=actor,
        resource_type="grievance",
        resource_id=g.id,
        details={"reference_no": g.reference_no, "source": source.code},
        meta=meta,
    )
    return g


def add_external_reference(
    db: Session, g: Grievance, source_id: uuid.UUID, external_id: str, by: uuid.UUID | None
) -> None:
    exists = db.execute(
        select(GrievanceExternalReference.grievance_id).where(
            GrievanceExternalReference.source_id == source_id,
            GrievanceExternalReference.external_id == external_id,
        )
    ).scalar()
    if exists:
        raise ConflictError(
            "This external reference is already linked to a grievance.",
            code="duplicate_external_reference",
            details=[{"grievance_id": str(exists)}],
        )
    db.add(GrievanceExternalReference(grievance_id=g.id, source_id=source_id, external_id=external_id, recorded_by=by))
    db.flush()


# --- Updates and workflow ----------------------------------------------------------------


EDITABLE = {
    "subject",
    "category_id",
    "subcategory_id",
    "department_id",
    "priority",
    "location_text",
    "district_id",
    "subdivision_id",
    "block_id",
    "gram_panchayat_id",
    "village_id",
    "municipality_id",
    "ward_id",
}


def update_details(
    db: Session,
    user: CurrentUser,
    gid: uuid.UUID,
    changes: dict[str, Any],
    version: int,
    meta: RequestMeta,
    *,
    reason: str | None = None,
) -> Grievance:
    g = get_scoped(db, user, gid, lock=True)
    _check_version(g, version)
    unknown = set(changes) - EDITABLE
    if unknown:
        raise AppError(
            "These fields cannot be edited.",
            code="not_editable",
            details=[{"fields": sorted(unknown)}],
        )
    loc_fields = {
        k for k in changes if k.endswith("_id") and k not in {"category_id", "subcategory_id", "department_id"}
    }
    if loc_fields:
        loc = resolve_location(db, LocationInput(**{k: changes[k] for k in loc_fields}))
        changes.update(dict(loc.__dict__.items()))
    before = {k: (str(getattr(g, k)) if getattr(g, k) is not None else None) for k in changes}
    for k, v in changes.items():
        setattr(g, k, v)
    if ("priority" in changes or "category_id" in changes) and g.status in OPEN_STATUSES:
        perf.apply_sla(db, g, start=g.registered_at, cycle=g.reopened_count)
    _bump(g, user)
    after = {k: (str(v) if v is not None else None) for k, v in changes.items()}
    audit.record(
        db,
        action="grievance.updated",
        actor=user.actor,
        resource_type="grievance",
        resource_id=g.id,
        details={"before": before, "after": after, "reason": reason},
        meta=meta,
    )
    return g


def assign(
    db: Session,
    user: CurrentUser,
    gid: uuid.UUID,
    officer_id: uuid.UUID,
    version: int,
    reason: str | None,
    meta: RequestMeta,
) -> Grievance:
    g = get_scoped(db, user, gid, lock=True)
    _check_version(g, version)
    if g.status not in ASSIGNABLE_FROM:
        raise TransitionError(f"A grievance in status '{g.status}' cannot be assigned.")
    officer = db.get(User, officer_id)
    if officer is None or not officer.is_active or "grievance.work" not in permission_codes(db, officer_id):
        raise AppError("The selected officer cannot be assigned grievances.", code="invalid_officer")
    t = now()
    db.execute(
        update(GrievanceAssignment)
        .where(GrievanceAssignment.grievance_id == g.id, GrievanceAssignment.ended_at.is_(None))
        .values(ended_at=t)
    )
    db.add(
        GrievanceAssignment(
            grievance_id=g.id,
            officer_user_id=officer_id,
            assigned_by=user.id,
            department_id=officer.department_id or g.department_id,
            reason=reason,
        )
    )
    previous_officer = g.assigned_officer_id
    g.assigned_officer_id = officer_id
    if officer.department_id and g.department_id is None:
        g.department_id = officer.department_id
    _set_status(db, g, "assigned", "reassign" if previous_officer else "assign", user, reason)
    notify(
        db,
        officer_id,
        "assignment",
        f"Grievance {g.reference_no} assigned to you",
        g.subject,
        f"/grievances/{g.id}",
    )
    audit.record(
        db,
        action="grievance.assigned",
        actor=user.actor,
        resource_type="grievance",
        resource_id=g.id,
        details={
            "officer_id": str(officer_id),
            "previous_officer_id": str(previous_officer) if previous_officer else None,
        },
        meta=meta,
    )
    return g


def _set_status(db: Session, g: Grievance, to: str, action: str, user: CurrentUser | None, reason: str | None) -> None:
    db.add(
        GrievanceStatusHistory(
            grievance_id=g.id,
            from_status=g.status,
            to_status=to,
            action=action,
            reason=reason,
            actor_user_id=user.id if user else None,
        )
    )
    g.status = to
    g.status_changed_at = now()
    if user:
        _bump(g, user)


def transition(
    db: Session,
    user: CurrentUser,
    gid: uuid.UUID,
    action: str,
    version: int,
    note: str | None,
    meta: RequestMeta,
) -> Grievance:
    if action not in TRANSITIONS:
        raise AppError("Unknown action.", code="unknown_action")
    allowed_from, to, permission = TRANSITIONS[action]
    if permission not in user.permissions:
        raise PermissionDeniedError()
    g = get_scoped(db, user, gid, lock=True)
    _check_version(g, version)
    if g.status not in allowed_from:
        raise TransitionError(f"'{action}' is not allowed while the grievance is '{g.status}'.")
    if (action in REASON_REQUIRED or action == "submit_resolution") and (not note or len(note.strip()) < 10):
        raise AppError("Please give a reason or details of at least 10 characters.", code="reason_required")
    if action in {"start_work", "submit_resolution"} and g.assigned_officer_id != user.id:
        raise PermissionDeniedError("Only the assigned officer can do this.")
    if action in {"accept_resolution", "return_resolution"}:
        submitter = db.execute(
            select(GrievanceStatusHistory.actor_user_id)
            .where(
                GrievanceStatusHistory.grievance_id == g.id,
                GrievanceStatusHistory.to_status == "resolution_submitted",
            )
            .order_by(GrievanceStatusHistory.occurred_at.desc())
            .limit(1)
        ).scalar()
        if submitter == user.id:
            raise PermissionDeniedError(
                "A resolution must be verified by someone other than the officer who submitted it."
            )
    if action == "submit_resolution":
        g.resolution_summary = note
        db.add(GrievanceComment(grievance_id=g.id, kind="resolution", body=note or "", author_user_id=user.id))
    if action in {"accept_resolution", "return_resolution"} and note:
        db.add(GrievanceComment(grievance_id=g.id, kind="verification", body=note, author_user_id=user.id))
    _set_status(db, g, to, action, user, note)
    if action == "accept_resolution":
        g.resolved_at = now()
        perf.record_resolution(db, g)
    elif action == "close":
        g.closed_at = now()
    elif action == "reopen":
        g.reopened_count += 1
        g.resolved_at = None
        g.closed_at = None
        perf.apply_sla(db, g, start=now(), cycle=g.reopened_count)
    if action == "return_resolution" and g.assigned_officer_id:
        notify(
            db,
            g.assigned_officer_id,
            "workflow",
            f"Resolution returned for {g.reference_no}",
            note,
            f"/grievances/{g.id}",
        )
    if action == "submit_resolution":
        from app.modules.notifications.service import notify_many, users_with_permission_in_scope

        verifiers = users_with_permission_in_scope(
            db,
            "grievance.verify",
            district_id=g.district_id,
            block_id=g.block_id,
            department_id=g.department_id,
        )
        notify_many(
            db,
            [v for v in verifiers if v != user.id],
            "workflow",
            f"Resolution submitted for {g.reference_no}",
            "Verification required.",
            f"/grievances/{g.id}",
        )
    audit.record(
        db,
        action=f"grievance.{action}",
        actor=user.actor,
        resource_type="grievance",
        resource_id=g.id,
        details={"to": to},
        meta=meta,
    )
    return g


def escalate(db: Session, user: CurrentUser, gid: uuid.UUID, reason: str, version: int, meta: RequestMeta) -> Grievance:
    g = get_scoped(db, user, gid, lock=True)
    _check_version(g, version)
    if g.status not in OPEN_STATUSES:
        raise TransitionError("Only open grievances can be escalated.")
    if len(reason.strip()) < 10:
        raise AppError("Please give a reason of at least 10 characters.", code="reason_required")
    perf.escalate(db, g, reason=reason, trigger="manual", actor=user.actor, meta=meta)
    _bump(g, user)
    return g


def add_comment(
    db: Session, user: CurrentUser, gid: uuid.UUID, kind: str, body: str, meta: RequestMeta
) -> GrievanceComment:
    g = get_scoped(db, user, gid)
    if kind not in {"comment", "investigation"}:
        raise AppError("Unsupported comment type.", code="invalid_kind")
    c = GrievanceComment(grievance_id=g.id, kind=kind, body=body.strip(), author_user_id=user.id)
    db.add(c)
    db.flush()
    audit.record(
        db,
        action="grievance.commented",
        actor=user.actor,
        resource_type="grievance",
        resource_id=g.id,
        details={"kind": kind, "comment_id": str(c.id)},
        meta=meta,
    )
    return c


def link(
    db: Session,
    user: CurrentUser,
    gid: uuid.UUID,
    related_id: uuid.UUID,
    relation: str,
    note: str | None,
    meta: RequestMeta,
) -> GrievanceRelationship:
    g = get_scoped(db, user, gid, lock=True)
    other = get_scoped(db, user, related_id)
    if g.id == other.id:
        raise AppError("A grievance cannot be linked to itself.", code="invalid_link")
    if relation not in {"duplicate_of", "related", "follow_up"}:
        raise AppError("Unknown relation type.", code="invalid_link")
    existing = db.execute(
        select(GrievanceRelationship).where(
            GrievanceRelationship.grievance_id == g.id,
            GrievanceRelationship.related_grievance_id == other.id,
            GrievanceRelationship.relation_type == relation,
        )
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("These grievances are already linked.")
    rel = GrievanceRelationship(
        grievance_id=g.id,
        related_grievance_id=other.id,
        relation_type=relation,
        note=note,
        created_by=user.id,
    )
    db.add(rel)
    if relation == "duplicate_of":
        g.duplicate_of_id = other.id
        _bump(g, user)
    db.flush()
    audit.record(
        db,
        action="grievance.linked",
        actor=user.actor,
        resource_type="grievance",
        resource_id=g.id,
        details={"related": str(other.id), "relation": relation},
        meta=meta,
    )
    return rel


# --- Attachments ---------------------------------------------------------------------------------


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]")


def sanitize_filename(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = _SAFE_NAME.sub("_", base).strip(" .") or "attachment"
    return base[:150]


def upload_attachment(
    db: Session, user: CurrentUser, gid: uuid.UUID, filename: str, data: bytes, meta: RequestMeta
) -> GrievanceAttachment:
    g = get_scoped(db, user, gid)
    settings = get_settings()
    if len(data) == 0:
        raise AppError("The file is empty.", code="empty_file")
    if len(data) > settings.upload_max_bytes:
        raise AppError(
            f"Files may be at most {settings.upload_max_bytes // (1024 * 1024)} MB.",
            code="file_too_large",
        )
    clean_name = sanitize_filename(filename)
    ext = "." + clean_name.rsplit(".", 1)[-1].lower() if "." in clean_name else ""
    content_type = next((ct for ct, (magic, exts) in ALLOWED_UPLOADS.items() if data.startswith(magic)), None)
    if content_type is None or ext not in ALLOWED_UPLOADS[content_type][1]:
        raise AppError(
            "Only PDF, PNG and JPEG files are accepted, and the file extension must match its content.",
            code="file_type_not_allowed",
        )
    result = malware.scan(data)
    if result.status == "infected":
        audit.record_independent(
            action="grievance.attachment_rejected",
            outcome="denied",
            actor=user.actor,
            resource_type="grievance",
            resource_id=g.id,
            details={"reason": "malware", "signature": result.detail},
            meta=meta,
        )
        raise AppError("The file was rejected by the malware scanner.", code="malware_detected")
    if result.status == "error":
        raise AppError("The file could not be scanned for malware. Try again later.", code="scan_unavailable")
    att_id = uuid.uuid4()
    key = f"grievances/{g.id}/{att_id}"
    storage.put_bytes(key, data, content_type)
    att = GrievanceAttachment(
        id=att_id,
        grievance_id=g.id,
        filename=clean_name,
        content_type=content_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=key,
        scan_status=result.status,
        scan_detail=result.detail,
        uploaded_by=user.id,
    )
    db.add(att)
    db.flush()
    audit.record(
        db,
        action="grievance.attachment_uploaded",
        actor=user.actor,
        resource_type="grievance",
        resource_id=g.id,
        details={"attachment_id": str(att.id), "sha256": att.sha256, "scan": result.status},
        meta=meta,
    )
    return att


def attachment_for_download(
    db: Session, user: CurrentUser, gid: uuid.UUID, att_id: uuid.UUID, meta: RequestMeta
) -> GrievanceAttachment:
    g = get_scoped(db, user, gid)
    att = db.execute(
        select(GrievanceAttachment).where(GrievanceAttachment.id == att_id, GrievanceAttachment.grievance_id == g.id)
    ).scalar_one_or_none()
    if att is None:
        raise NotFoundError("Attachment not found.")
    if att.scan_status not in {"clean", "not_scanned"}:
        raise PermissionDeniedError("This file is not available for download.")
    audit.record(
        db,
        action="grievance.attachment_downloaded",
        actor=user.actor,
        resource_type="grievance",
        resource_id=g.id,
        details={"attachment_id": str(att.id)},
        meta=meta,
    )
    return att


# --- Queries -------------------------------------------------------------------------------------


@dataclass
class SearchFilters:
    q: str | None = None
    status: list[str] | None = None
    priority: list[str] | None = None
    category_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    district_id: uuid.UUID | None = None
    block_id: uuid.UUID | None = None
    village_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    assigned_to_me: bool = False
    overdue: bool | None = None
    open_only: bool = False
    escalated: bool | None = None
    risk_level: list[str] | None = None
    registered_from: datetime | None = None
    registered_to: datetime | None = None
    sort: str = "registered_at"
    order: str = "desc"


SORTS = {"registered_at", "due_at", "priority", "status", "reference_no"}


def search_query(user: CurrentUser, f: SearchFilters) -> Select[tuple[Grievance]]:
    from app.modules.intelligence.models import RiskAssessment

    stmt = select(Grievance).where(grievance_scope(user))
    if f.q:
        q = f.q.strip()[:200]
        stmt = stmt.where(
            or_(
                Grievance.reference_no == q.upper(),
                Grievance.subject.ilike(f"%{q}%"),
                Grievance.description.ilike(f"%{q}%"),
            )
        )
    if f.status:
        stmt = stmt.where(Grievance.status.in_(f.status))
    if f.open_only:
        stmt = stmt.where(Grievance.status.in_(OPEN_STATUSES))
    if f.priority:
        stmt = stmt.where(Grievance.priority.in_(f.priority))
    for col, val in (
        (Grievance.category_id, f.category_id),
        (Grievance.department_id, f.department_id),
        (Grievance.district_id, f.district_id),
        (Grievance.block_id, f.block_id),
        (Grievance.village_id, f.village_id),
        (Grievance.source_id, f.source_id),
    ):
        if val:
            stmt = stmt.where(col == val)
    if f.assigned_to_me:
        stmt = stmt.where(Grievance.assigned_officer_id == user.id)
    if f.overdue is True:
        stmt = stmt.where(perf.overdue_clause())
    elif f.overdue is False:
        stmt = stmt.where(~perf.overdue_clause())
    if f.escalated is True:
        stmt = stmt.where(Grievance.escalation_level > 0)
    if f.risk_level:
        stmt = stmt.where(
            Grievance.id.in_(
                select(RiskAssessment.grievance_id).where(
                    RiskAssessment.is_current.is_(True), RiskAssessment.level.in_(f.risk_level)
                )
            )
        )
    if f.registered_from:
        stmt = stmt.where(Grievance.registered_at >= f.registered_from)
    if f.registered_to:
        stmt = stmt.where(Grievance.registered_at < f.registered_to)
    sort_col = getattr(Grievance, f.sort if f.sort in SORTS else "registered_at")
    if f.sort == "priority":
        from sqlalchemy import case

        sort_col = case({"urgent": 4, "high": 3, "normal": 2, "low": 1}, value=Grievance.priority)
    stmt = stmt.order_by(
        sort_col.desc().nulls_last() if f.order == "desc" else sort_col.asc().nulls_last(),
        Grievance.id,
    )
    return stmt


def list_rows(
    db: Session, user: CurrentUser, f: SearchFilters, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    from app.modules.intelligence.models import RiskAssessment

    base = search_query(user, f)
    total = db.execute(select(func.count()).select_from(base.order_by(None).subquery())).scalar_one()
    page = base.limit(limit).offset(offset).subquery()
    G = aliased(Grievance, page)
    officer = aliased(User)
    t = now()
    rows = db.execute(
        select(
            G,
            IssueCategory.name_en,
            Department.name_en,
            Block.name_en,
            Village.name_en,
            officer.full_name,
            GrievanceSource.name_en,
            RiskAssessment.level,
        )
        .outerjoin(IssueCategory, IssueCategory.id == G.category_id)
        .outerjoin(Department, Department.id == G.department_id)
        .outerjoin(Block, Block.id == G.block_id)
        .outerjoin(Village, Village.id == G.village_id)
        .outerjoin(officer, officer.id == G.assigned_officer_id)
        .outerjoin(GrievanceSource, GrievanceSource.id == G.source_id)
        .outerjoin(
            RiskAssessment,
            and_(RiskAssessment.grievance_id == G.id, RiskAssessment.is_current.is_(True)),
        )
    ).all()
    order = {r[0].id: i for i, r in enumerate(rows)}
    ids_in_order = [gid for (gid,) in db.execute(select(page.c.id)).all()]
    by_id = {r[0].id: r for r in rows}
    out = []
    for gid in ids_in_order:
        g, cat, dep, blk, vil, off, src, risk = by_id[gid]
        out.append(
            {
                "id": g.id,
                "reference_no": g.reference_no,
                "subject": g.subject,
                "status": g.status,
                "priority": g.priority,
                "category": cat,
                "department": dep,
                "block": blk,
                "village": vil,
                "assigned_officer": off,
                "source": src,
                "registered_at": g.registered_at,
                "due_at": g.due_at,
                "overdue": bool(g.due_at and g.due_at < t and g.status in OPEN_STATUSES),
                "risk_level": risk,
                "escalation_level": g.escalation_level,
                "reopened_count": g.reopened_count,
            }
        )
    del order
    return out, total


def complainant_view(
    db: Session,
    user: CurrentUser,
    complainant_id: uuid.UUID | None,
    *,
    gid: uuid.UUID,
    meta: RequestMeta | None,
) -> dict[str, Any] | None:
    if complainant_id is None:
        return None
    c = db.get(Complainant, complainant_id)
    if c is None:
        return None
    if "citizen.read" in user.permissions:
        audit.record(
            db,
            action="citizen.viewed",
            actor=user.actor,
            resource_type="grievance",
            resource_id=gid,
            meta=meta,
        )
        return {
            "masked": False,
            "name": security.decrypt_text(c.name_encrypted),
            "mobile": security.decrypt_text(c.mobile_encrypted),
            "email": security.decrypt_text(c.email_encrypted),
            "address": security.decrypt_text(c.address_encrypted),
            "consent_recorded": c.consent_recorded,
        }
    return {
        "masked": True,
        "name": "Restricted" if c.name_encrypted else None,
        "mobile": security.mask(security.decrypt_text(c.mobile_encrypted), 2),
        "email": None,
        "address": None,
        "consent_recorded": c.consent_recorded,
    }


def allowed_actions(user: CurrentUser, g: Grievance) -> list[str]:
    acts = []
    for action, (froms, _to, perm) in TRANSITIONS.items():
        if g.status in froms and perm in user.permissions:
            if action in {"start_work", "submit_resolution"} and g.assigned_officer_id != user.id:
                continue
            acts.append(action)
    if g.status in ASSIGNABLE_FROM and "grievance.assign" in user.permissions:
        acts.append("assign")
    if g.status in OPEN_STATUSES and "grievance.escalate" in user.permissions:
        acts.append("escalate")
    for perm, act in (
        ("grievance.update", "edit"),
        ("grievance.comment", "comment"),
        ("grievance.attach", "attach"),
        ("grievance.link", "link"),
        ("ai.review", "review_ai"),
    ):
        if perm in user.permissions:
            acts.append(act)
    return acts


__all__ = ["String", "cast"]
