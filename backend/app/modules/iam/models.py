"""Identity and access management tables (schema ``iam``)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "iam"
SCOPE_TYPES = ("district", "subdivision", "block", "department", "assigned", "own")


def _fk(target: str, ondelete: str = "RESTRICT") -> ForeignKey:
    return ForeignKey(target, ondelete=ondelete)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("username ~ '^[a-z0-9._-]{3,64}$'", name="username_format"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_nonnegative"),
        CheckConstraint("approval_status IN ('approved', 'pending', 'rejected')", name="approval_status_allowed"),
        Index("ix_users_approval_status", "approval_status"),
        {"schema": SCHEMA},
    )

    username: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(CITEXT)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("ref.departments.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("iam.users.id"))
    # Self-service access requests: created "pending" and inactive until an administrator
    # approves them and assigns the actual roles and area of responsibility.
    approval_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="approved", server_default=text("'approved'")
    )
    requested_role: Mapped[str | None] = mapped_column(String(64))
    access_request_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("iam.users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = ({"schema": SCHEMA},)

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))


class Permission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = ({"schema": SCHEMA},)

    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = ({"schema": SCHEMA},)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("iam.users.id", "CASCADE"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("iam.roles.id"), primary_key=True)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("iam.users.id"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = ({"schema": SCHEMA},)

    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("iam.roles.id", "CASCADE"), primary_key=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("iam.permissions.id", "CASCADE"), primary_key=True
    )


class UserScopeAssignment(UUIDPrimaryKeyMixin, Base):
    """Resource scope. A user sees a record if ANY of their scopes matches it."""

    __tablename__ = "user_scope_assignments"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN (" + ", ".join(f"'{s}'" for s in SCOPE_TYPES) + ")",
            name="scope_type_allowed",
        ),
        CheckConstraint(
            "(scope_type = 'district' AND district_id IS NOT NULL) OR "
            "(scope_type = 'subdivision' AND subdivision_id IS NOT NULL) OR "
            "(scope_type = 'block' AND block_id IS NOT NULL) OR "
            "(scope_type = 'department' AND department_id IS NOT NULL) OR "
            "(scope_type IN ('assigned', 'own'))",
            name="scope_target_present",
        ),
        Index("ix_user_scope_assignments_user_id", "user_id"),
        {"schema": SCHEMA},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("iam.users.id", "CASCADE"), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    district_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("ref.districts.id"))
    subdivision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("ref.subdivisions.id"))
    block_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("ref.blocks.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("ref.departments.id"))
    granted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("iam.users.id"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class UserSession(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_user_id", "user_id"),
        {"schema": SCHEMA},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("iam.users.id", "CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mfa_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(100))


class MfaCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mfa_credentials"
    __table_args__ = (
        CheckConstraint("method IN ('totp')", name="method_allowed"),
        Index(
            "uq_mfa_credentials_user_confirmed",
            "user_id",
            unique=True,
            postgresql_where=text("confirmed_at IS NOT NULL AND revoked_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("iam.users.id", "CASCADE"), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'totp'"))
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_step: Mapped[int | None] = mapped_column(BigInteger)


class LoginEvent(UUIDPrimaryKeyMixin, Base):
    """Successful/failed sign-in attempts, used for suspicious-login detection."""

    __tablename__ = "login_events"
    __table_args__ = (
        Index("ix_login_events_user_id_occurred_at", "user_id", "occurred_at"),
        Index("ix_login_events_ip_address_occurred_at", "ip_address", "occurred_at"),
        {"schema": SCHEMA},
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("iam.users.id", "CASCADE"))
    username_attempted: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(50))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    suspicious: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))


__all__ = [
    "LoginEvent",
    "MfaCredential",
    "Permission",
    "Role",
    "RolePermission",
    "UniqueConstraint",
    "User",
    "UserRole",
    "UserScopeAssignment",
    "UserSession",
]
