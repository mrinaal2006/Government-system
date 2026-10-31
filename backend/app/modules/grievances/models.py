"""Grievance management tables (schemas ``grievance`` and ``citizen``).

* ``reference_no`` is generated once and protected from UPDATE by a trigger.
* Status history, assignments history and comments are append-only for the
  runtime role (no UPDATE/DELETE grants on history tables; assignments may only
  have ``ended_at`` set, enforced by a trigger).
* Complainant personal data lives in ``citizen.complainants``, encrypted at the
  application layer, readable only through the ``citizen.read`` permission.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "grievance"
CITIZEN_SCHEMA = "citizen"

STATUSES = (
    "registered",
    "assigned",
    "in_progress",
    "resolution_submitted",
    "resolved",
    "closed",
    "reopened",
)
OPEN_STATUSES = ("registered", "assigned", "in_progress", "resolution_submitted", "reopened")
PRIORITIES = ("low", "normal", "high", "urgent")
RELATION_TYPES = ("duplicate_of", "related", "follow_up")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _uuid_fk(target: str, *, nullable: bool = True, ondelete: str = "RESTRICT") -> Any:
    return mapped_column(UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable)


class Complainant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "complainants"
    __table_args__ = (
        Index("ix_complainants_mobile_hash", "mobile_hash"),
        {"schema": CITIZEN_SCHEMA},
    )

    name_encrypted: Mapped[str | None] = mapped_column(Text)
    mobile_encrypted: Mapped[str | None] = mapped_column(Text)
    mobile_hash: Mapped[str | None] = mapped_column(String(64))
    email_encrypted: Mapped[str | None] = mapped_column(Text)
    address_encrypted: Mapped[str | None] = mapped_column(Text)
    consent_recorded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReferenceCounter(Base):
    __tablename__ = "reference_counters"
    __table_args__ = ({"schema": SCHEMA},)

    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    last_value: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))


class Grievance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "grievances"
    __table_args__ = (
        CheckConstraint(_in("status", STATUSES), name="status_allowed"),
        CheckConstraint(_in("priority", PRIORITIES), name="priority_allowed"),
        CheckConstraint("length(btrim(description)) >= 10", name="description_min_length"),
        CheckConstraint("duplicate_of_id IS NULL OR duplicate_of_id <> id", name="not_own_duplicate"),
        Index("ix_grievances_status", "status"),
        Index("ix_grievances_registered_at", "registered_at"),
        Index("ix_grievances_due_at", "due_at"),
        Index("ix_grievances_department_id", "department_id"),
        Index("ix_grievances_assigned_officer_id", "assigned_officer_id"),
        Index("ix_grievances_category_id", "category_id"),
        Index("ix_grievances_block_id", "block_id"),
        Index("ix_grievances_village_id", "village_id"),
        Index("ix_grievances_district_id", "district_id"),
        Index("ix_grievances_subdivision_id", "subdivision_id"),
        Index("ix_grievances_source_id", "source_id"),
        Index("ix_grievances_created_by", "created_by"),
        Index("ix_grievances_citizen_account_id", "citizen_account_id"),
        Index(
            "ix_grievances_description_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"},
        ),
        Index(
            "ix_grievances_subject_trgm",
            "subject",
            postgresql_using="gin",
            postgresql_ops={"subject": "gin_trgm_ops"},
        ),
        {"schema": SCHEMA},
    )

    reference_no: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    source_id: Mapped[uuid.UUID] = _uuid_fk("ref.grievance_sources.id", nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[uuid.UUID | None] = _uuid_fk("ref.issue_categories.id")
    subcategory_id: Mapped[uuid.UUID | None] = _uuid_fk("ref.issue_categories.id")
    department_id: Mapped[uuid.UUID | None] = _uuid_fk("ref.departments.id")
    district_id: Mapped[uuid.UUID | None] = _uuid_fk("ref.districts.id")
    subdivision_id: Mapped[uuid.UUID | None] = _uuid_fk("ref.subdivisions.id")
    block_id: Mapped[uuid.UUID | None] = _uuid_fk("ref.blocks.id")
    gram_panchayat_id: Mapped[uuid.UUID | None] = _uuid_fk("ref.gram_panchayats.id")
    village_id: Mapped[uuid.UUID | None] = _uuid_fk("ref.villages.id")
    municipality_id: Mapped[uuid.UUID | None] = _uuid_fk("ref.municipalities.id")
    ward_id: Mapped[uuid.UUID | None] = _uuid_fk("ref.wards.id")
    location_text: Mapped[str | None] = mapped_column(String(500))
    assigned_officer_id: Mapped[uuid.UUID | None] = _uuid_fk("iam.users.id")
    priority: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'normal'"))
    sla_policy_id: Mapped[uuid.UUID | None] = _uuid_fk("perf.sla_policies.id")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'registered'"))
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    complainant_id: Mapped[uuid.UUID | None] = _uuid_fk("citizen.complainants.id")
    duplicate_of_id: Mapped[uuid.UUID | None] = _uuid_fk("grievance.grievances.id")
    import_batch_id: Mapped[uuid.UUID | None] = _uuid_fk("grievance.import_batches.id")
    # Set when filed by a citizen through the self-service portal.
    citizen_account_id: Mapped[uuid.UUID | None] = _uuid_fk("citizen.citizen_accounts.id")
    created_by: Mapped[uuid.UUID | None] = _uuid_fk("iam.users.id")
    updated_by: Mapped[uuid.UUID | None] = _uuid_fk("iam.users.id")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


class GrievanceAssignment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "grievance_assignments"
    __table_args__ = (
        Index(
            "uq_grievance_assignments_active",
            "grievance_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
        Index("ix_grievance_assignments_officer_user_id", "officer_user_id"),
        {"schema": SCHEMA},
    )

    grievance_id: Mapped[uuid.UUID] = _uuid_fk("grievance.grievances.id", nullable=False)
    department_id: Mapped[uuid.UUID | None] = _uuid_fk("ref.departments.id")
    officer_user_id: Mapped[uuid.UUID] = _uuid_fk("iam.users.id", nullable=False)
    assigned_by: Mapped[uuid.UUID] = _uuid_fk("iam.users.id", nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)


class GrievanceStatusHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "grievance_status_history"
    __table_args__ = (
        Index("ix_grievance_status_history_grievance_id", "grievance_id", "occurred_at"),
        {"schema": SCHEMA},
    )

    grievance_id: Mapped[uuid.UUID] = _uuid_fk("grievance.grievances.id", nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[uuid.UUID | None] = _uuid_fk("iam.users.id")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class GrievanceComment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "grievance_comments"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('comment', 'investigation', 'resolution', 'verification')",
            name="kind_allowed",
        ),
        Index("ix_grievance_comments_grievance_id", "grievance_id", "created_at"),
        {"schema": SCHEMA},
    )

    grievance_id: Mapped[uuid.UUID] = _uuid_fk("grievance.grievances.id", nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'comment'"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_user_id: Mapped[uuid.UUID] = _uuid_fk("iam.users.id", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class GrievanceAttachment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "grievance_attachments"
    __table_args__ = (
        CheckConstraint(
            "scan_status IN ('pending', 'clean', 'infected', 'error', 'not_scanned')",
            name="scan_status_allowed",
        ),
        Index("ix_grievance_attachments_grievance_id", "grievance_id"),
        {"schema": SCHEMA},
    )

    grievance_id: Mapped[uuid.UUID] = _uuid_fk("grievance.grievances.id", nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    scan_status: Mapped[str] = mapped_column(String(20), nullable=False)
    scan_detail: Mapped[str | None] = mapped_column(String(200))
    uploaded_by: Mapped[uuid.UUID] = _uuid_fk("iam.users.id", nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class GrievanceExternalReference(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "grievance_external_references"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        Index("ix_grievance_external_references_grievance_id", "grievance_id"),
        {"schema": SCHEMA},
    )

    grievance_id: Mapped[uuid.UUID] = _uuid_fk("grievance.grievances.id", nullable=False)
    source_id: Mapped[uuid.UUID] = _uuid_fk("ref.grievance_sources.id", nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    recorded_by: Mapped[uuid.UUID | None] = _uuid_fk("iam.users.id")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class GrievanceRelationship(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "grievance_relationships"
    __table_args__ = (
        CheckConstraint(_in("relation_type", RELATION_TYPES), name="relation_type_allowed"),
        CheckConstraint("grievance_id <> related_grievance_id", name="not_self"),
        UniqueConstraint("grievance_id", "related_grievance_id", "relation_type"),
        {"schema": SCHEMA},
    )

    grievance_id: Mapped[uuid.UUID] = _uuid_fk("grievance.grievances.id", nullable=False)
    related_grievance_id: Mapped[uuid.UUID] = _uuid_fk("grievance.grievances.id", nullable=False)
    relation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = _uuid_fk("iam.users.id", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ImportBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'processing', 'completed', 'failed')", name="status_allowed"),
        UniqueConstraint("source_id", "file_sha256"),
        {"schema": SCHEMA},
    )

    source_id: Mapped[uuid.UUID] = _uuid_fk("ref.grievance_sources.id", nullable=False)
    adapter: Mapped[str] = mapped_column(String(50), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'queued'"))
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    errors: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    uploaded_by: Mapped[uuid.UUID] = _uuid_fk("iam.users.id", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
