"""Citizen portal tables (schema ``citizen``). Personal data is encrypted at rest."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "citizen"


class CitizenAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "citizen_accounts"
    __table_args__ = (
        CheckConstraint("failed_login_count >= 0", name="failed_login_nonnegative"),
        {"schema": SCHEMA},
    )

    mobile_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    mobile_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    name_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    email_encrypted: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str] = mapped_column(String(20), nullable=False)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CitizenSession(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "citizen_sessions"
    __table_args__ = (Index("ix_citizen_sessions_account_id", "account_id"), {"schema": SCHEMA})

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("citizen.citizen_accounts.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OtpChallenge(UUIDPrimaryKeyMixin, Base):
    """One-time codes: only a hash is stored; limited attempts; short expiry; single use."""

    __tablename__ = "otp_challenges"
    __table_args__ = (
        CheckConstraint("purpose IN ('verify_mobile')", name="purpose_allowed"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        Index("ix_otp_challenges_account_id", "account_id", "created_at"),
        {"schema": SCHEMA},
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("citizen.citizen_accounts.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
