"""Officer access requests (self-service sign-up with administrator approval).

A request creates an INACTIVE user with approval_status "pending", no roles and no
scopes, so it grants no access whatsoever. Administrators holding iam.users.manage are
notified, choose the actual roles and area of responsibility, and approve or reject.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.ratelimit import hit
from app.core.request_meta import RequestMeta
from app.modules.audit import service as audit
from app.modules.iam.catalogue import ROLES
from app.modules.iam.models import Permission, RolePermission, User, UserRole
from app.modules.iam.service import CurrentUser, revoke_sessions
from app.modules.notifications.service import notify_many

REQUESTABLE_ROLES = [r for r in ROLES if r != "super_admin"]


def administrators(db: Session) -> list[uuid.UUID]:
    holders = (
        select(UserRole.user_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(Permission.code == "iam.users.manage")
    )
    return list(db.execute(select(User.id).where(User.is_active.is_(True), User.id.in_(holders))).scalars())


def request_access(db: Session, data: dict[str, Any], meta: RequestMeta) -> User:
    hit(f"signup-ip:{meta.ip or 'unknown'}", 5, window_seconds=3600, fail_closed=True)
    if data["requested_role"] not in REQUESTABLE_ROLES:
        raise AppError("This role cannot be requested.", code="role_not_requestable")
    if db.execute(select(User.id).where(User.username == data["username"])).first():
        raise ConflictError("That username is already in use. Choose another.")
    try:
        security.validate_password_policy(data["password"], username=data["username"], full_name=data["full_name"])
    except security.WeakPasswordError as exc:
        raise AppError(str(exc), code="weak_password") from exc
    user = User(
        username=data["username"],
        full_name=data["full_name"],
        designation=data["designation"],
        email=data["email"],
        department_id=data.get("department_id"),
        password_hash=security.hash_password(data["password"]),
        password_changed_at=datetime.now(UTC),
        must_change_password=False,
        is_active=False,
        approval_status="pending",
        requested_role=data["requested_role"],
        access_request_note=data.get("note"),
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        action="iam.access_requested",
        actor=audit.Actor(user.id, user.username),
        resource_type="user",
        resource_id=user.id,
        details={"requested_role": user.requested_role},
        meta=meta,
    )
    notify_many(
        db,
        administrators(db),
        "access_request",
        f"Access request from {user.full_name}",
        f"{user.designation or ''} requested the role {ROLES[data['requested_role']]['name']}.",
        "/admin/users?status=pending",
    )
    return user


def approve(
    db: Session,
    admin: CurrentUser,
    user_id: uuid.UUID,
    roles: list[str],
    scopes: list[dict[str, Any]],
    note: str | None,
    meta: RequestMeta,
) -> User:
    from app.modules.iam.models import Role, UserScopeAssignment

    user = db.get(User, user_id, with_for_update=True)
    if user is None:
        raise NotFoundError("User not found.")
    if user.approval_status != "pending":
        raise ConflictError("This request has already been decided.")
    if not roles:
        raise AppError("Assign at least one role.", code="roles_required")
    for rid in db.execute(select(Role.id).where(Role.code.in_(roles))).scalars():
        db.add(UserRole(user_id=user.id, role_id=rid, granted_by=admin.id))
    for s in scopes:
        db.add(UserScopeAssignment(user_id=user.id, granted_by=admin.id, **s))
    user.approval_status, user.is_active = "approved", True
    user.reviewed_by, user.reviewed_at, user.review_note = admin.id, datetime.now(UTC), note
    db.flush()
    audit.record(
        db,
        action="iam.access_approved",
        actor=admin.actor,
        resource_type="user",
        resource_id=user.id,
        details={"roles": roles, "scopes": len(scopes), "requested_role": user.requested_role},
        meta=meta,
    )
    return user


def reject(db: Session, admin: CurrentUser, user_id: uuid.UUID, note: str, meta: RequestMeta) -> User:
    user = db.get(User, user_id, with_for_update=True)
    if user is None:
        raise NotFoundError("User not found.")
    if user.approval_status != "pending":
        raise ConflictError("This request has already been decided.")
    user.approval_status, user.is_active = "rejected", False
    user.reviewed_by, user.reviewed_at, user.review_note = admin.id, datetime.now(UTC), note
    revoke_sessions(db, user.id, "access_rejected")
    audit.record(
        db,
        action="iam.access_rejected",
        actor=admin.actor,
        resource_type="user",
        resource_id=user.id,
        details={"note": note},
        meta=meta,
    )
    return user
