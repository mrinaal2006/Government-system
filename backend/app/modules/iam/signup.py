"""Self-service sign-up for officials.

The account is active immediately; no approval step.

* While no active Super Administrator exists, the person who signs up becomes the
  Super Administrator. This replaces the command-line bootstrap. A transaction-level
  advisory lock makes this safe when two sign-ups arrive at the same moment.
* Every later account gets the Data Entry Operator role with the "own" scope: it can
  register grievances and see only the ones it registered. It cannot see anyone
  else's grievances or citizen data until an administrator assigns a wider role and
  area under Users and roles.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import AppError, ConflictError
from app.core.ratelimit import hit
from app.core.request_meta import RequestMeta
from app.modules.audit import service as audit
from app.modules.iam.models import Permission, Role, RolePermission, User, UserRole, UserScopeAssignment
from app.modules.notifications.service import notify_many

DEFAULT_ROLE = "data_entry_operator"
DEFAULT_SCOPE = "own"
_BOOTSTRAP_LOCK = 0x44474953  # arbitrary constant: serialises "first account" sign-ups


def _active_users_with(db: Session, permission: str) -> list[Any]:
    holders = (
        select(UserRole.user_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(Permission.code == permission)
    )
    return list(db.execute(select(User.id).where(User.is_active.is_(True), User.id.in_(holders))).scalars())


def super_admin_exists(db: Session) -> bool:
    return bool(
        db.execute(
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.code == "super_admin", User.is_active.is_(True))
            .limit(1)
        ).first()
    )


def sign_up(db: Session, data: dict[str, Any], meta: RequestMeta) -> User:
    hit(f"signup-ip:{meta.ip or 'unknown'}", 5, window_seconds=3600, fail_closed=True)
    username = data["username"]
    if db.execute(select(User.id).where(User.username == username)).first():
        raise ConflictError("That username is already in use. Choose another.")
    try:
        security.validate_password_policy(data["password"], username=username, full_name=data["full_name"])
    except security.WeakPasswordError as exc:
        raise AppError(str(exc), code="weak_password") from exc

    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _BOOTSTRAP_LOCK})
    first_admin = not super_admin_exists(db)
    role_code = "super_admin" if first_admin else DEFAULT_ROLE

    user = User(
        username=username,
        full_name=data["full_name"],
        email=data.get("email"),
        password_hash=security.hash_password(data["password"]),
        password_changed_at=datetime.now(UTC),
        must_change_password=False,
        is_active=True,
    )
    db.add(user)
    db.flush()
    role_id = db.execute(select(Role.id).where(Role.code == role_code)).scalar_one()
    db.add(UserRole(user_id=user.id, role_id=role_id))
    if not first_admin:
        db.add(UserScopeAssignment(user_id=user.id, scope_type=DEFAULT_SCOPE))
    db.flush()
    audit.record(
        db,
        action="iam.signed_up",
        actor=audit.Actor(user.id, user.username),
        resource_type="user",
        resource_id=user.id,
        details={"role": role_code, "first_administrator": first_admin},
        meta=meta,
    )
    if not first_admin:
        notify_many(
            db,
            _active_users_with(db, "iam.users.manage"),
            "user_signed_up",
            f"New account: {user.full_name}",
            f"{user.username} signed up as Data Entry Operator (own records only). "
            "Assign a role and area under Users and roles if needed.",
            "/admin/users",
        )
    return user
