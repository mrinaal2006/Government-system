"""AI/analytics tables (schema ``intel``). Advisory only: nothing here changes a
grievance without an officer's explicit review action."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "intel"
TASKS = ("category", "department", "location", "summary")
VERIFICATION = ("pending", "accepted", "edited", "rejected", "not_applicable")
RISK_LEVELS = ("normal", "watch", "high", "critical")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _fk(target: str, *, nullable: bool = True, ondelete: str = "RESTRICT") -> Any:
    return mapped_column(UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable)


class ClassificationRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Administrator-maintained keyword rules: explainable, deterministic classification."""

    __tablename__ = "classification_rules"
    __table_args__ = (
        CheckConstraint("weight > 0 AND weight <= 10", name="weight_range"),
        CheckConstraint("length(btrim(keyword)) >= 2", name="keyword_not_blank"),
        UniqueConstraint("category_id", "keyword"),
        {"schema": SCHEMA},
    )

    category_id: Mapped[uuid.UUID] = _fk("ref.issue_categories.id", nullable=False)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, server_default=text("1"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[uuid.UUID | None] = _fk("iam.users.id")


class AIClassification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_classifications"
    __table_args__ = (
        CheckConstraint(_in("task", TASKS), name="task_allowed"),
        CheckConstraint(
            _in("processing_status", ("completed", "no_prediction", "failed")),
            name="processing_status_allowed",
        ),
        CheckConstraint(_in("verification_status", VERIFICATION), name="verification_status_allowed"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"),
        Index("ix_ai_classifications_grievance_id", "grievance_id", "task"),
        Index("ix_ai_classifications_verification_status", "verification_status"),
        {"schema": SCHEMA},
    )

    grievance_id: Mapped[uuid.UUID] = _fk("grievance.grievances.id", nullable=False)
    task: Mapped[str] = mapped_column(String(20), nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prediction: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    input_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    verified_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    verified_by: Mapped[uuid.UUID | None] = _fk("iam.users.id")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AIClassificationHistory(UUIDPrimaryKeyMixin, Base):
    """Append-only record of every change to an AI classification's review state."""

    __tablename__ = "ai_classification_history"
    __table_args__ = (
        Index("ix_ai_classification_history_classification_id", "classification_id"),
        {"schema": SCHEMA},
    )

    classification_id: Mapped[uuid.UUID] = _fk("intel.ai_classifications.id", nullable=False)
    event: Mapped[str] = mapped_column(String(30), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = _fk("iam.users.id")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class DuplicateCandidate(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "duplicate_candidates"
    __table_args__ = (
        CheckConstraint("grievance_id <> candidate_grievance_id", name="not_self"),
        CheckConstraint(_in("status", ("pending", "confirmed", "rejected")), name="status_allowed"),
        UniqueConstraint("grievance_id", "candidate_grievance_id"),
        {"schema": SCHEMA},
    )

    grievance_id: Mapped[uuid.UUID] = _fk("grievance.grievances.id", nullable=False)
    candidate_grievance_id: Mapped[uuid.UUID] = _fk("grievance.grievances.id", nullable=False)
    similarity: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    reviewed_by: Mapped[uuid.UUID | None] = _fk("iam.users.id")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class GrievanceCluster(UUIDPrimaryKeyMixin, Base):
    """Grievances sharing a category and an administrative unit within a time window."""

    __tablename__ = "grievance_clusters"
    __table_args__ = (
        CheckConstraint(
            _in("unit_level", ("village", "gram_panchayat", "block", "ward", "municipality")),
            name="unit_level_allowed",
        ),
        UniqueConstraint("cluster_key"),
        {"schema": SCHEMA},
    )

    cluster_key: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[uuid.UUID | None] = _fk("ref.issue_categories.id")
    unit_level: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    grievance_count: Mapped[int] = mapped_column(Integer, nullable=False)
    open_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_emerging: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    method_version: Mapped[str] = mapped_column(String(50), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ClusterMember(Base):
    __tablename__ = "cluster_members"
    __table_args__ = ({"schema": SCHEMA},)

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intel.grievance_clusters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    grievance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("grievance.grievances.id", ondelete="RESTRICT"),
        primary_key=True,
    )


class RiskModel(UUIDPrimaryKeyMixin, Base):
    """Versioned, configurable risk scoring and alert thresholds. One active version."""

    __tablename__ = "risk_models"
    __table_args__ = (
        UniqueConstraint("version"),
        Index("uq_risk_models_active", "is_active", unique=True, postgresql_where=text("is_active")),
        {"schema": SCHEMA},
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_provisional: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = _fk("iam.users.id")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class RiskAssessment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (
        CheckConstraint(_in("level", RISK_LEVELS), name="level_allowed"),
        Index("ix_risk_assessments_grievance_id", "grievance_id", "assessed_at"),
        Index(
            "uq_risk_assessments_current",
            "grievance_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        {"schema": SCHEMA},
    )

    grievance_id: Mapped[uuid.UUID] = _fk("grievance.grievances.id", nullable=False)
    risk_model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    factors: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
