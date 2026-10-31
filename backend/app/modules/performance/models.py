"""SLA, escalation and performance tables (schema ``perf``)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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

SCHEMA = "perf"


class SlaPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Resolution time limits, configured by administrators. None are pre-loaded:
    statutory/administrative timelines differ by state and service."""

    __tablename__ = "sla_policies"
    __table_args__ = (
        CheckConstraint("resolution_hours > 0 AND resolution_hours <= 8760", name="hours_range"),
        CheckConstraint(
            "priority IS NULL OR priority IN ('low', 'normal', 'high', 'urgent')",
            name="priority_allowed",
        ),
        CheckConstraint("warning_percent > 0 AND warning_percent < 100", name="warning_range"),
        {"schema": SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ref.issue_categories.id"))
    priority: Mapped[str | None] = mapped_column(String(10))
    resolution_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_percent: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("75"))
    legal_reference: Mapped[str | None] = mapped_column(Text, comment="Order/notification establishing this timeline")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("iam.users.id"))


class SlaEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sla_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('started', 'warning', 'breached', 'met', 'missed', 'restarted')",
            name="event_type_allowed",
        ),
        UniqueConstraint("grievance_id", "event_type", "cycle"),
        Index("ix_sla_events_grievance_id", "grievance_id"),
        {"schema": SCHEMA},
    )

    grievance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grievance.grievances.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    cycle: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    sla_policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("perf.sla_policies.id"))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Escalation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "escalations"
    __table_args__ = (
        CheckConstraint("trigger IN ('manual', 'sla_breach')", name="trigger_allowed"),
        CheckConstraint("level >= 1", name="level_positive"),
        Index("ix_escalations_grievance_id", "grievance_id"),
        Index("ix_escalations_created_at", "created_at"),
        {"schema": SCHEMA},
    )

    grievance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grievance.grievances.id"), nullable=False
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    escalated_to_role: Mapped[str | None] = mapped_column(String(64))
    escalated_to_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("iam.users.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("iam.users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class DepartmentPerformanceSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "department_performance_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_date", "department_id"),
        {"schema": SCHEMA},
    )

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ref.departments.id"), nullable=False
    )
    received_total: Mapped[int] = mapped_column(Integer, nullable=False)
    open_total: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_total: Mapped[int] = mapped_column(Integer, nullable=False)
    overdue_total: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_within_sla: Mapped[int] = mapped_column(Integer, nullable=False)
    reopened_total: Mapped[int] = mapped_column(Integer, nullable=False)
    escalated_total: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_resolution_hours: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
