"""Early-warning alerts (schema ``intel``)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin

SCHEMA = "intel"
ALERT_TYPES = (
    "overdue_backlog",
    "repeated_unresolved",
    "area_concentration",
    "essential_service",
    "escalation_history",
    "volume_spike",
)
ALERT_STATUSES = ("open", "acknowledged", "investigating", "escalated", "dismissed", "resolved")
ALERT_ACTIONS = ("acknowledge", "investigate", "escalate", "dismiss", "resolve", "comment")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class EarlyWarningAlert(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "early_warning_alerts"
    __table_args__ = (
        CheckConstraint(_in("alert_type", ALERT_TYPES), name="alert_type_allowed"),
        CheckConstraint(_in("level", ("watch", "high", "critical")), name="level_allowed"),
        CheckConstraint(_in("status", ALERT_STATUSES), name="status_allowed"),
        Index(
            "uq_early_warning_alerts_open_dedup",
            "dedup_key",
            unique=True,
            postgresql_where=text("status IN ('open', 'acknowledged', 'investigating', 'escalated')"),
        ),
        Index("ix_early_warning_alerts_status_level", "status", "level"),
        {"schema": SCHEMA},
    )

    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    reasons: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    recommended_actions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False)
    district_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ref.districts.id"))
    block_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ref.blocks.id"))
    village_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ref.villages.id"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ref.issue_categories.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ref.departments.id"))
    risk_model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'open'"))
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AlertGrievance(Base):
    __tablename__ = "alert_grievances"
    __table_args__ = ({"schema": SCHEMA},)

    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intel.early_warning_alerts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    grievance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grievance.grievances.id"), primary_key=True
    )


class AlertAction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "alert_actions"
    __table_args__ = (
        CheckConstraint(_in("action", ALERT_ACTIONS), name="action_allowed"),
        CheckConstraint("length(btrim(reason)) >= 5", name="reason_required"),
        Index("ix_alert_actions_alert_id", "alert_id"),
        {"schema": SCHEMA},
    )

    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intel.early_warning_alerts.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("iam.users.id"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
