from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.auth import DbDep, require
from app.api.common import Page, paging
from app.modules.audit import service
from app.modules.audit.models import AuditLog
from app.modules.iam.service import CurrentUser

router = APIRouter(prefix="/audit", tags=["audit"])
AuditRead = Annotated[CurrentUser, Depends(require("audit.read"))]


class AuditOut(BaseModel):
    seq: int
    occurred_at: datetime
    actor_username: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    outcome: str
    ip_address: str | None
    request_id: str | None
    details: dict[str, Any]


@router.get("/logs", response_model=Page[AuditOut])
def logs(
    cu: AuditRead,
    db: DbDep,
    pg: Annotated[tuple[int, int], Depends(paging)],
    action: str | None = None,
    actor: str | None = None,
    outcome: str | None = None,
    resource_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Page[AuditOut]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action[:100]))
    if actor:
        stmt = stmt.where(AuditLog.actor_username == actor[:100])
    if outcome:
        stmt = stmt.where(AuditLog.outcome == outcome[:20])
    if resource_id:
        stmt = stmt.where(AuditLog.resource_id == resource_id[:100])
    if since:
        stmt = stmt.where(AuditLog.occurred_at >= since)
    if until:
        stmt = stmt.where(AuditLog.occurred_at < until)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(AuditLog.seq.desc()).limit(pg[0]).offset(pg[1])).scalars()
    items = [
        AuditOut(
            seq=r.seq,
            occurred_at=r.occurred_at,
            actor_username=r.actor_username,
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            outcome=r.outcome,
            ip_address=str(r.ip_address) if r.ip_address else None,
            request_id=r.request_id,
            details=r.details,
        )
        for r in rows
    ]
    return Page(items=items, total=total, limit=pg[0], offset=pg[1])


@router.get("/verify")
def verify(cu: AuditRead, db: DbDep) -> dict[str, Any]:
    return service.verify_chain(db)


__all__ = ["uuid"]
