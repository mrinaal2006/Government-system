from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.api.auth import DbDep, require
from app.api.common import paging
from app.core.request_meta import RequestMeta
from app.modules.administration.models import Department, IssueCategory
from app.modules.early_warning import service
from app.modules.early_warning.models import AlertAction, AlertGrievance, EarlyWarningAlert
from app.modules.geography.models import Block, District, Village
from app.modules.grievances.models import Grievance
from app.modules.iam.models import User
from app.modules.iam.scope import grievance_scope
from app.modules.iam.service import CurrentUser

router = APIRouter(prefix="/alerts", tags=["early-warning"])
AlertRead = Annotated[CurrentUser, Depends(require("alert.read"))]
AlertAct = Annotated[CurrentUser, Depends(require("alert.act"))]


def _summary(db: DbDep, a: EarlyWarningAlert) -> dict[str, Any]:
    def nm(model: Any, i: Any) -> str | None:
        return db.get(model, i).name_en if i and db.get(model, i) else None  # type: ignore[union-attr]

    return {
        "id": str(a.id),
        "alert_type": a.alert_type,
        "level": a.level,
        "title": a.title,
        "status": a.status,
        "reasons": a.reasons,
        "metrics": a.metrics,
        "recommended_actions": a.recommended_actions,
        "district": nm(District, a.district_id),
        "block": nm(Block, a.block_id),
        "village": nm(Village, a.village_id),
        "category": nm(IssueCategory, a.category_id),
        "department": nm(Department, a.department_id),
        "block_id": str(a.block_id) if a.block_id else None,
        "category_id": str(a.category_id) if a.category_id else None,
        "department_id": str(a.department_id) if a.department_id else None,
        "risk_model_version": a.risk_model_version,
        "first_detected_at": a.first_detected_at,
        "last_detected_at": a.last_detected_at,
        "closed_at": a.closed_at,
    }


@router.get("")
def list_alerts(
    cu: AlertRead,
    db: DbDep,
    pg: Annotated[tuple[int, int], Depends(paging)],
    status: Literal["active", "closed", "all"] = "active",
    level: Annotated[list[str] | None, Query()] = None,
) -> dict[str, Any]:
    stmt = select(EarlyWarningAlert).where(service.scope_clause(cu))
    if status == "active":
        stmt = stmt.where(EarlyWarningAlert.status.in_(service.ACTIVE))
    elif status == "closed":
        stmt = stmt.where(EarlyWarningAlert.status.in_(("dismissed", "resolved")))
    if level:
        stmt = stmt.where(EarlyWarningAlert.level.in_(level))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    from sqlalchemy import case

    rank = case({"critical": 3, "high": 2, "watch": 1}, value=EarlyWarningAlert.level)
    rows = db.execute(
        stmt.order_by(rank.desc(), EarlyWarningAlert.last_detected_at.desc()).limit(pg[0]).offset(pg[1])
    ).scalars()
    return {
        "items": [_summary(db, a) for a in rows],
        "total": total,
        "limit": pg[0],
        "offset": pg[1],
    }


@router.get("/{alert_id}")
def get_alert(alert_id: uuid.UUID, cu: AlertRead, db: DbDep) -> dict[str, Any]:
    a = service.get_alert(db, cu, alert_id)
    grievances = db.execute(
        select(
            Grievance.id,
            Grievance.reference_no,
            Grievance.subject,
            Grievance.status,
            Grievance.due_at,
        )
        .join(AlertGrievance, AlertGrievance.grievance_id == Grievance.id)
        .where(AlertGrievance.alert_id == a.id, grievance_scope(cu))
        .order_by(Grievance.registered_at.desc())
    ).all()
    actor = aliased(User)
    actions = db.execute(
        select(AlertAction, actor.full_name)
        .join(actor, actor.id == AlertAction.actor_user_id)
        .where(AlertAction.alert_id == a.id)
        .order_by(AlertAction.occurred_at)
    ).all()
    return {
        **_summary(db, a),
        "grievances": [
            {"id": str(i), "reference_no": r, "subject": s, "status": st, "due_at": d} for i, r, s, st, d in grievances
        ],
        "actions": [
            {
                "action": x.action,
                "reason": x.reason,
                "from_status": x.from_status,
                "to_status": x.to_status,
                "actor": n,
                "occurred_at": x.occurred_at,
            }
            for x, n in actions
        ],
    }


class ActionIn(BaseModel):
    action: Literal["acknowledge", "investigate", "escalate", "dismiss", "resolve", "comment"]
    reason: str = Field(min_length=5, max_length=2000)


@router.post("/{alert_id}/actions")
def act(alert_id: uuid.UUID, body: ActionIn, request: Request, cu: AlertAct, db: DbDep) -> dict[str, Any]:
    a = service.act(db, cu, alert_id, body.action, body.reason, RequestMeta.from_request(request))
    return {"id": str(a.id), "status": a.status}


@router.post("/evaluate")
def evaluate(cu: AlertAct, db: DbDep) -> dict[str, Any]:
    from app.modules.intelligence import service as intel

    intel.compute_clusters(db)
    intel.assess_all_open(db)
    return service.evaluate(db)
