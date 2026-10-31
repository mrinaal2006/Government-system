"""Notification creation and queries."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.iam.models import Permission, RolePermission, User, UserRole, UserScopeAssignment
from app.modules.notifications.models import Notification


def notify(db: Session, user_id: uuid.UUID, category: str, title: str, body: str | None, link: str | None) -> None:
    db.add(Notification(user_id=user_id, category=category, title=title[:300], body=body, link=link))


def notify_many(
    db: Session,
    user_ids: Iterable[uuid.UUID],
    category: str,
    title: str,
    body: str | None,
    link: str | None,
) -> None:
    for uid in set(user_ids):
        notify(db, uid, category, title, body, link)


def users_with_permission_in_scope(
    db: Session,
    permission: str,
    *,
    district_id: uuid.UUID | None = None,
    block_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    """Active users holding ``permission`` whose scope covers the given unit/department."""
    holders = (
        select(UserRole.user_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(Permission.code == permission)
    )
    conds = []
    if district_id:
        conds.append((UserScopeAssignment.scope_type == "district") & (UserScopeAssignment.district_id == district_id))
    if block_id:
        conds.append((UserScopeAssignment.scope_type == "block") & (UserScopeAssignment.block_id == block_id))
    if department_id:
        conds.append(
            (UserScopeAssignment.scope_type == "department") & (UserScopeAssignment.department_id == department_id)
        )
    if not conds:
        return []
    from sqlalchemy import or_

    stmt = (
        select(User.id)
        .join(UserScopeAssignment, UserScopeAssignment.user_id == User.id)
        .where(User.is_active.is_(True), User.id.in_(holders), or_(*conds))
        .distinct()
    )
    return list(db.execute(stmt).scalars())


def list_for(
    db: Session, user_id: uuid.UUID, *, unread_only: bool, limit: int, offset: int
) -> tuple[list[Notification], int, int]:
    base = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        base = base.where(Notification.read_at.is_(None))
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    unread = db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    ).scalar_one()
    rows = list(db.execute(base.order_by(Notification.created_at.desc()).limit(limit).offset(offset)).scalars())
    return rows, total, unread


def mark_read(db: Session, user_id: uuid.UUID, notification_id: uuid.UUID | None) -> int:
    stmt = update(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    if notification_id:
        stmt = stmt.where(Notification.id == notification_id)
    return db.execute(stmt.values(read_at=datetime.now(UTC))).rowcount or 0  # type: ignore[attr-defined]
