"""Asynchronous report jobs (schema ``governance``)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin

SCHEMA = "governance"
REPORT_TYPES = (
    "grievance_register",
    "department_performance",
    "block_summary",
    "executive_summary",
)


class ReportJob(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "report_jobs"
    __table_args__ = (
        CheckConstraint(
            "report_type IN (" + ", ".join(f"'{t}'" for t in REPORT_TYPES) + ")",
            name="report_type_allowed",
        ),
        CheckConstraint("format IN ('pdf', 'xlsx')", name="format_allowed"),
        CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="status_allowed"),
        Index("ix_report_jobs_requested_by", "requested_by", "created_at"),
        {"schema": SCHEMA},
    )

    report_type: Mapped[str] = mapped_column(String(40), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'queued'"))
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("iam.users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    storage_key: Mapped[str | None] = mapped_column(String(300))
    filename: Mapped[str | None] = mapped_column(String(200))
    row_count: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
