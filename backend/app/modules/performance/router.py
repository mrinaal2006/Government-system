from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.auth import DbDep, require
from app.modules.administration.models import Department
from app.modules.geography.models import Block
from app.modules.grievances.models import Grievance
from app.modules.iam.scope import grievance_scope
from app.modules.iam.service import CurrentUser
from app.modules.performance import service
from app.modules.performance.models import DepartmentPerformanceSnapshot, Escalation

router = APIRouter(prefix="/performance", tags=["performance"])
PerfRead = Annotated[CurrentUser, Depends(require("performance.read"))]


def _named(db: DbDep, rows: list[dict[str, Any]], model: Any) -> list[dict[str, Any]]:
    ids = [r["key"] for r in rows if r["key"]]
    names: dict[Any, Any] = (
        {r[0]: r[1] for r in db.execute(select(model.id, model.name_en).where(model.id.in_(ids))).all()} if ids else {}
    )
    for r in rows:
        r["id"] = str(r.pop("key")) if r.get("key") else None
        r["name"] = names.get(uuid.UUID(r["id"])) if r["id"] else "Not assigned"
    return sorted(rows, key=lambda r: (-(r["overdue"] or 0), r["name"] or ""))


@router.get("/departments")
def departments(
    cu: PerfRead, db: DbDep, since: datetime | None = None, until: datetime | None = None
) -> list[dict[str, Any]]:
    return _named(
        db,
        service.performance_by(db, Grievance.department_id, grievance_scope(cu), since, until),
        Department,
    )


@router.get("/blocks")
def blocks(
    cu: PerfRead, db: DbDep, since: datetime | None = None, until: datetime | None = None
) -> list[dict[str, Any]]:
    return _named(db, service.performance_by(db, Grievance.block_id, grievance_scope(cu), since, until), Block)


@router.get("/escalations")
def escalations(cu: PerfRead, db: DbDep, days: int = 30) -> list[dict[str, Any]]:
    since = service.now() - timedelta(days=min(max(days, 1), 365))
    rows = db.execute(
        select(Escalation, Grievance.reference_no, Grievance.subject, Grievance.id)
        .join(Grievance, Grievance.id == Escalation.grievance_id)
        .where(Escalation.created_at >= since, grievance_scope(cu))
        .order_by(Escalation.created_at.desc())
        .limit(500)
    ).all()
    return [
        {
            "grievance_id": str(gid),
            "reference_no": ref,
            "subject": subj,
            "level": e.level,
            "trigger": e.trigger,
            "reason": e.reason,
            "created_at": e.created_at,
        }
        for e, ref, subj, gid in rows
    ]


@router.get("/snapshots")
def snapshots(cu: PerfRead, db: DbDep, department_id: uuid.UUID, days: int = 90) -> list[dict[str, Any]]:
    since = service.now().date() - timedelta(days=min(days, 730))
    rows = db.execute(
        select(DepartmentPerformanceSnapshot)
        .where(
            DepartmentPerformanceSnapshot.department_id == department_id,
            DepartmentPerformanceSnapshot.snapshot_date >= since,
        )
        .order_by(DepartmentPerformanceSnapshot.snapshot_date)
    ).scalars()
    return [
        {
            "date": r.snapshot_date,
            "received": r.received_total,
            "open": r.open_total,
            "resolved": r.resolved_total,
            "overdue": r.overdue_total,
            "within_sla": r.resolved_within_sla,
            "avg_hours": float(r.avg_resolution_hours) if r.avg_resolution_hours is not None else None,
        }
        for r in rows
    ]


__all__ = ["Literal"]
