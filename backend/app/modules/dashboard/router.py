"""District Magistrate command dashboard. Every figure is a live query over the
grievances visible to the user, and every KPI carries the filter that opens its records."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.api.auth import DbDep, require
from app.modules.administration.models import IssueCategory
from app.modules.audit.models import AuditLog
from app.modules.early_warning import service as ew
from app.modules.early_warning.models import EarlyWarningAlert
from app.modules.geography.models import Block, Village
from app.modules.grievances.models import OPEN_STATUSES, Grievance
from app.modules.iam.scope import grievance_scope
from app.modules.iam.service import CurrentUser
from app.modules.intelligence.models import GrievanceCluster, RiskAssessment
from app.modules.performance import service as perf
from app.modules.performance.router import _named

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
Dash = Annotated[CurrentUser, Depends(require("dashboard.read", "grievance.read"))]
IST = ZoneInfo("Asia/Kolkata")


def _count(db: DbDep, *conds: Any) -> int:
    return int(db.execute(select(func.count()).select_from(Grievance).where(*conds)).scalar_one())


@router.get("/summary")
def summary(cu: Dash, db: DbDep) -> dict[str, Any]:
    scope = grievance_scope(cu)
    start_today = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    high_risk = select(RiskAssessment.grievance_id).where(
        RiskAssessment.is_current.is_(True), RiskAssessment.level.in_(("high", "critical"))
    )
    critical_alerts = db.execute(
        select(func.count())
        .select_from(EarlyWarningAlert)
        .where(
            ew.scope_clause(cu),
            EarlyWarningAlert.status.in_(ew.ACTIVE),
            EarlyWarningAlert.level == "critical",
        )
    ).scalar_one()
    kpis = [
        {"key": "total", "label": "Total grievances", "value": _count(db, scope), "filter": {}},
        {
            "key": "today",
            "label": "Received today (IST)",
            "value": _count(db, scope, Grievance.registered_at >= start_today),
            "filter": {"registered_from": start_today.isoformat()},
        },
        {
            "key": "pending",
            "label": "Pending",
            "value": _count(db, scope, Grievance.status.in_(OPEN_STATUSES)),
            "filter": {"open_only": True},
        },
        {
            "key": "resolved",
            "label": "Resolved or closed",
            "value": _count(db, scope, Grievance.status.in_(("resolved", "closed"))),
            "filter": {"status": ["resolved", "closed"]},
        },
        {
            "key": "overdue",
            "label": "Overdue",
            "value": _count(db, scope, perf.overdue_clause()),
            "filter": {"overdue": True},
        },
        {
            "key": "high_risk",
            "label": "High risk",
            "value": _count(db, scope, Grievance.id.in_(high_risk)),
            "filter": {"risk_level": ["high", "critical"]},
        },
        {
            "key": "critical_alerts",
            "label": "Critical alerts",
            "value": int(critical_alerts),
            "link": "/early-warning?level=critical",
        },
    ]
    return {"generated_at": datetime.now(UTC), "kpis": kpis}


@router.get("/trends")
def trends(cu: Dash, db: DbDep, granularity: Literal["week", "month"] = "week") -> dict[str, Any]:
    periods = 12
    span = timedelta(weeks=periods) if granularity == "week" else timedelta(days=31 * periods)
    since = datetime.now(UTC) - span
    bucket = func.date_trunc(granularity, func.timezone("Asia/Kolkata", Grievance.registered_at))
    received: dict[Any, Any] = {
        r[0]: r[1]
        for r in db.execute(
            select(bucket, func.count()).where(grievance_scope(cu), Grievance.registered_at >= since).group_by(bucket)
        ).all()
    }
    rbucket = func.date_trunc(granularity, func.timezone("Asia/Kolkata", Grievance.resolved_at))
    resolved: dict[Any, Any] = {
        r[0]: r[1]
        for r in db.execute(
            select(rbucket, func.count()).where(grievance_scope(cu), Grievance.resolved_at >= since).group_by(rbucket)
        ).all()
    }
    keys = sorted(set(received) | set(resolved))
    return {
        "granularity": granularity,
        "timezone": "Asia/Kolkata",
        "series": [
            {
                "period": k.date().isoformat(),
                "received": received.get(k, 0),
                "resolved": resolved.get(k, 0),
            }
            for k in keys
        ],
    }


@router.get("/blocks")
def block_distribution(cu: Dash, db: DbDep) -> list[dict[str, Any]]:
    return _named(db, perf.performance_by(db, Grievance.block_id, grievance_scope(cu), None, None), Block)


@router.get("/categories")
def category_distribution(cu: Dash, db: DbDep) -> list[dict[str, Any]]:
    return _named(
        db,
        perf.performance_by(db, Grievance.category_id, grievance_scope(cu), None, None),
        IssueCategory,
    )


@router.get("/clusters")
def emerging_clusters(cu: Dash, db: DbDep) -> list[dict[str, Any]]:
    from app.modules.intelligence.models import ClusterMember

    visible = (
        select(ClusterMember.cluster_id)
        .join(Grievance, Grievance.id == ClusterMember.grievance_id)
        .where(grievance_scope(cu))
    )
    rows = db.execute(
        select(GrievanceCluster, IssueCategory.name_en)
        .outerjoin(IssueCategory, IssueCategory.id == GrievanceCluster.category_id)
        .where(GrievanceCluster.id.in_(visible), GrievanceCluster.open_count > 0)
        .order_by(GrievanceCluster.open_count.desc())
        .limit(10)
    ).all()
    out = []
    for c, cat in rows:
        unit = (
            db.get(Village if c.unit_level == "village" else Block, c.unit_id)
            if c.unit_level in ("village", "block")
            else None
        )
        out.append(
            {
                "id": str(c.id),
                "category": cat,
                "category_id": str(c.category_id) if c.category_id else None,
                "unit_level": c.unit_level,
                "unit_id": str(c.unit_id),
                "unit_name": unit.name_en if unit else c.unit_level,
                "open_count": c.open_count,
                "grievance_count": c.grievance_count,
                "window_end": c.window_end,
            }
        )
    return out


@router.get("/important")
def important(cu: Dash, db: DbDep) -> list[dict[str, Any]]:
    ra = aliased(RiskAssessment)
    rows = db.execute(
        select(Grievance, ra.level, ra.score)
        .join(ra, (ra.grievance_id == Grievance.id) & ra.is_current.is_(True))
        .where(
            grievance_scope(cu),
            Grievance.status.in_(OPEN_STATUSES),
            ra.level.in_(("high", "critical")),
        )
        .order_by(ra.score.desc(), Grievance.registered_at)
        .limit(10)
    ).all()
    return [
        {
            "id": str(g.id),
            "reference_no": g.reference_no,
            "subject": g.subject,
            "status": g.status,
            "risk_level": lvl,
            "risk_score": float(score),
            "due_at": g.due_at,
        }
        for g, lvl, score in rows
    ]


@router.get("/recent-actions")
def recent_actions(cu: Dash, db: DbDep) -> list[dict[str, Any]]:
    visible = select(Grievance.id.cast(AuditLog.resource_id.type)).where(grievance_scope(cu))
    rows = db.execute(
        select(AuditLog)
        .where(
            AuditLog.resource_type == "grievance",
            AuditLog.resource_id.in_(visible),
            AuditLog.outcome == "success",
            AuditLog.action != "citizen.viewed",
        )
        .order_by(AuditLog.seq.desc())
        .limit(15)
    ).scalars()
    return [
        {
            "action": r.action,
            "actor": r.actor_username,
            "occurred_at": r.occurred_at,
            "grievance_id": r.resource_id,
        }
        for r in rows
    ]
