"""Administrative configuration reference tables (schema ``ref``).

Departments, the issue category tree and the grievance source channels. These are
master data maintained by authorised administrators (CRUD APIs arrive in Phase 3/4);
no departments or categories are pre-populated because they differ by state and
district. Only the source channel list mandated by the project specification is
seeded (migration 0002), each marked ``not_configured``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    SCHEMA_REFERENCE,
    ActiveFlagMixin,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

CODE_PATTERN = r"^[A-Z][A-Z0-9_]{1,49}$"

SOURCE_CHANNEL_TYPES = (
    "helpline",
    "government_portal",
    "administrative_office",
    "print_media",
    "social_media",
    "manual",
    "departmental_record",
)
SOURCE_INTEGRATION_MODES = (
    "not_configured",  # nothing connected yet
    "development_adapter",  # explicitly labelled development-only adapter
    "file_import",  # authorised CSV/XLSX import
    "live_api",  # documented, authorised live integration
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class Department(UUIDPrimaryKeyMixin, TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (
        CheckConstraint(f"code ~ '{CODE_PATTERN}'", name="code_format"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
        Index("ix_departments_parent_id", "parent_id"),
        Index(
            "ix_departments_name_en_trgm",
            "name_en",
            postgresql_using="gin",
            postgresql_ops={"name_en": "gin_trgm_ops"},
        ),
        {"schema": SCHEMA_REFERENCE},
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_local: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA_REFERENCE}.departments.id", ondelete="RESTRICT")
    )


class IssueCategory(UUIDPrimaryKeyMixin, TimestampMixin, ActiveFlagMixin, Base):
    """Category tree; a row with ``parent_id`` set is a subcategory."""

    __tablename__ = "issue_categories"
    __table_args__ = (
        CheckConstraint(f"code ~ '{CODE_PATTERN}'", name="code_format"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
        Index("ix_issue_categories_parent_id", "parent_id"),
        Index("ix_issue_categories_default_department_id", "default_department_id"),
        {"schema": SCHEMA_REFERENCE},
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_local: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_REFERENCE}.issue_categories.id", ondelete="RESTRICT"),
    )
    default_department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA_REFERENCE}.departments.id", ondelete="RESTRICT")
    )
    is_essential_service: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="Set by administrators; used by the early-warning engine (Phase 6)",
    )


class GrievanceSource(UUIDPrimaryKeyMixin, TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "grievance_sources"
    __table_args__ = (
        CheckConstraint(f"code ~ '{CODE_PATTERN}'", name="code_format"),
        CheckConstraint(_in("channel_type", SOURCE_CHANNEL_TYPES), name="channel_type_allowed"),
        CheckConstraint(
            _in("integration_mode", SOURCE_INTEGRATION_MODES), name="integration_mode_allowed"
        ),
        {"schema": SCHEMA_REFERENCE},
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_local: Mapped[str | None] = mapped_column(String(200))
    channel_type: Mapped[str] = mapped_column(String(40), nullable=False)
    integration_mode: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default=text("'not_configured'")
    )
    description: Mapped[str | None] = mapped_column(Text)
