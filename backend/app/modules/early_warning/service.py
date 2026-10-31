"""Explainable early-warning engine and alert workflow.

Each run evaluates the six indicators from the specification using thresholds in
the active risk model. An alert carries its reasons (with numbers), the grievance
references behind it, geographic context, the risk-model version, and recommended
administrative actions from configuration. Re-detection updates the open alert with
the same ``dedup_key`` instead of creating duplicates. Nothing here takes any
administrative action; officers acknowledge, investigate, escalate or dismiss.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, delete, false, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.request_meta import RequestMeta
from app.modules.administration.models import Department, IssueCategory
from app.modules.audit import service as audit
from app.modules.early_warning.models import AlertAction, AlertGrievance, EarlyWarningAlert
from app.modules.geography.models import Block, Village
from app.modules.grievances.models import OPEN_STATUSES, Grievance
from app.modules.iam.scope import unit_scope_ids
from app.modules.iam.service import CurrentUser
from app.modules.intelligence.models import ClusterMember, GrievanceCluster
from app.modules.intelligence.service import active_risk_model
from app.modules.notifications.service import notify_many, users_with_permission_in_scope
from app.modules.performance.models import Escalation

ACTIVE = ("open", "acknowledged", "investigating", "escalated")
LEVEL_RANK = {"watch": 1, "high": 2, "critical": 3}
ACTION_TRANSITIONS: dict[str, tuple[tuple[str, ...], str | None]] = {
    "acknowledge": (("open",), "acknowledged"),
    "investigate": (("open", "acknowledged"), "investigating"),
    "escalate": (ACTIVE, "escalated"),
    "dismiss": (ACTIVE, "dismissed"),
    "resolve": (ACTIVE, "resolved"),
    "comment": ((*ACTIVE, "dismissed", "resolved"), None),
}


def now() -> datetime:
    return datetime.now(UTC)


def _level(value: float, watch: float, high: float | None, critical: float | None) -> str | None:
    if critical is not None and value >= critical:
        return "critical"
    if high is not None and value >= high:
        return "high"
    if value >= watch:
        return "watch"
    return None


def _upsert(
    db: Session,
    *,
    alert_type: str,
    level: str,
    title: str,
    reasons: list[str],
    metrics: dict[str, Any],
    dedup_key: str,
    grievance_ids: list[uuid.UUID],
    model_version: int,
    actions: list[str],
    **context: Any,
) -> tuple[EarlyWarningAlert, bool]:
    a = db.execute(
        select(EarlyWarningAlert)
        .where(EarlyWarningAlert.dedup_key == dedup_key, EarlyWarningAlert.status.in_(ACTIVE))
        .with_for_update()
    ).scalar_one_or_none()
    created = a is None
    if a is None:
        a = EarlyWarningAlert(
            alert_type=alert_type,
            level=level,
            title=title,
            reasons=reasons,
            metrics=metrics,
            dedup_key=dedup_key,
            risk_model_version=model_version,
            recommended_actions=actions,
            **context,
        )
        db.add(a)
        db.flush()
    else:
        if LEVEL_RANK[level] > LEVEL_RANK[a.level]:
            a.level = level
        a.title, a.reasons, a.metrics, a.last_detected_at = title, reasons, metrics, now()
        a.risk_model_version = model_version
        db.execute(delete(AlertGrievance).where(AlertGrievance.alert_id == a.id))
    for gid in dict.fromkeys(grievance_ids[:500]):
        db.add(AlertGrievance(alert_id=a.id, grievance_id=gid))
    db.flush()
    return a, created


def evaluate(db: Session) -> dict[str, int]:
    model = active_risk_model(db)
    cfg = model.parameters["alerts"]
    rec = model.parameters.get("recommended_actions", {})
    t = now()
    created: list[EarlyWarningAlert] = []
    touched = 0

    def emit(**kw: Any) -> None:
        nonlocal touched
        a, new = _upsert(db, model_version=model.version, actions=rec.get(kw["alert_type"], []), **kw)
        touched += 1
        if new:
            created.append(a)

    open_ = Grievance.status.in_(OPEN_STATUSES)

    # 1. Overdue backlog per department
    c = cfg["overdue_backlog"]
    for dep_id, dep_name, district_id, ids in db.execute(
        select(
            Grievance.department_id,
            Department.name_en,
            Grievance.district_id,
            func.array_agg(Grievance.id),
        )
        .join(Department, Department.id == Grievance.department_id)
        .where(open_, Grievance.due_at < t)
        .group_by(Grievance.department_id, Department.name_en, Grievance.district_id)
    ).all():
        n = len(ids)
        lvl = _level(n, c["min_overdue"], c.get("high"), c.get("critical"))
        if lvl:
            emit(
                alert_type="overdue_backlog",
                level=lvl,
                title=f"{n} overdue grievances: {dep_name}",
                reasons=[f"{n} open grievances are past their resolution due time (threshold {c['min_overdue']})."],
                metrics={"overdue": n},
                dedup_key=f"overdue_backlog:{dep_id}:{district_id}",
                grievance_ids=ids,
                department_id=dep_id,
                district_id=district_id,
            )

    # 2. Repeated unresolved (reopened) grievances
    c = cfg["repeated_unresolved"]
    for g in db.execute(select(Grievance).where(open_, Grievance.reopened_count >= c["min_reopened"])).scalars():
        lvl = "high" if g.reopened_count >= c.get("high", 99) else "watch"
        emit(
            alert_type="repeated_unresolved",
            level=lvl,
            title=f"Repeatedly reopened: {g.reference_no}",
            reasons=[f"Reopened {g.reopened_count} times and still unresolved (threshold {c['min_reopened']})."],
            metrics={"reopened": g.reopened_count},
            dedup_key=f"repeated_unresolved:{g.id}",
            grievance_ids=[g.id],
            district_id=g.district_id,
            block_id=g.block_id,
            village_id=g.village_id,
            category_id=g.category_id,
            department_id=g.department_id,
        )

    # 3. Area concentration (from clusters)
    c = cfg["area_concentration"]
    for cl, cat_name in db.execute(
        select(GrievanceCluster, IssueCategory.name_en)
        .outerjoin(IssueCategory, IssueCategory.id == GrievanceCluster.category_id)
        .where(GrievanceCluster.window_end >= t - timedelta(days=1))
    ).all():
        lvl = _level(cl.open_count, c["min_count"], c.get("high"), c.get("critical"))
        if not lvl:
            continue
        ids = list(db.execute(select(ClusterMember.grievance_id).where(ClusterMember.cluster_id == cl.id)).scalars())
        ctx = _unit_context(db, cl.unit_level, cl.unit_id)
        emit(
            alert_type="area_concentration",
            level=lvl,
            title=f"{cl.open_count} open '{cat_name}' complaints in {ctx.pop('unit_name')}",
            reasons=[
                f"{cl.grievance_count} complaints of the same category in the same {cl.unit_level} within "
                f"{c['window_days']} days; {cl.open_count} still open (threshold {c['min_count']})."
            ],
            metrics={"count": cl.grievance_count, "open": cl.open_count},
            dedup_key=f"area_concentration:{cl.cluster_key}",
            grievance_ids=ids,
            category_id=cl.category_id,
            **ctx,
        )

    # 4. Essential service disruption
    c = cfg["essential_service"]
    since = t - timedelta(days=c["window_days"])
    for cat_id, cat_name, block_id, ids in db.execute(
        select(
            Grievance.category_id,
            IssueCategory.name_en,
            Grievance.block_id,
            func.array_agg(Grievance.id),
        )
        .join(IssueCategory, IssueCategory.id == Grievance.category_id)
        .where(
            open_,
            IssueCategory.is_essential_service.is_(True),
            Grievance.registered_at >= since,
            Grievance.block_id.is_not(None),
        )
        .group_by(Grievance.category_id, IssueCategory.name_en, Grievance.block_id)
    ).all():
        lvl = _level(len(ids), c["min_count"], None, c.get("critical"))
        if lvl:
            lvl = "high" if lvl == "watch" else lvl
            ctx = _unit_context(db, "block", block_id)
            emit(
                alert_type="essential_service",
                level=lvl,
                title=f"Possible essential service disruption: {cat_name} in {ctx.pop('unit_name')}",
                reasons=[
                    f"{len(ids)} open complaints about an essential service in {c['window_days']} days "
                    f"(threshold {c['min_count']})."
                ],
                metrics={"open": len(ids)},
                dedup_key=f"essential_service:{cat_id}:{block_id}",
                grievance_ids=ids,
                category_id=cat_id,
                **ctx,
            )

    # 5. Escalation history per department
    c = cfg["escalation_history"]
    since = t - timedelta(days=c["window_days"])
    for dep_id, dep_name, n, ids in db.execute(
        select(
            Grievance.department_id,
            Department.name_en,
            func.count(Escalation.id),
            func.array_agg(Grievance.id),
        )
        .join(Grievance, Grievance.id == Escalation.grievance_id)
        .join(Department, Department.id == Grievance.department_id)
        .where(Escalation.created_at >= since)
        .group_by(Grievance.department_id, Department.name_en)
    ).all():
        lvl = _level(n, c["min_escalations"], c.get("high"), None)
        if lvl:
            emit(
                alert_type="escalation_history",
                level=lvl,
                title=f"{n} escalations in {c['window_days']} days: {dep_name}",
                reasons=[f"{n} escalations recorded in {c['window_days']} days (threshold {c['min_escalations']})."],
                metrics={"escalations": n},
                dedup_key=f"escalation_history:{dep_id}",
                grievance_ids=list(ids),
                department_id=dep_id,
            )

    # 6. Volume spike per category and block
    c = cfg["volume_spike"]
    recent_start = t - timedelta(days=c["recent_days"])
    base_start = recent_start - timedelta(weeks=c["baseline_weeks"])
    rows = db.execute(
        select(
            Grievance.category_id,
            Grievance.block_id,
            func.count().filter(Grievance.registered_at >= recent_start),
            func.count().filter(Grievance.registered_at < recent_start),
            func.array_agg(Grievance.id).filter(Grievance.registered_at >= recent_start),
        )
        .where(
            Grievance.registered_at >= base_start,
            Grievance.block_id.is_not(None),
            Grievance.category_id.is_not(None),
        )
        .group_by(Grievance.category_id, Grievance.block_id)
    ).all()
    for cat_id, block_id, recent, baseline_total, ids in rows:
        weekly_baseline = baseline_total / c["baseline_weeks"] * (c["recent_days"] / 7)
        ratio = recent / max(weekly_baseline, 1.0)
        if recent >= c["min_count"] and ratio >= c["ratio"]:
            lvl = "critical" if ratio >= c["critical_ratio"] else "high"
            cat = db.get(IssueCategory, cat_id)
            ctx = _unit_context(db, "block", block_id)
            emit(
                alert_type="volume_spike",
                level=lvl,
                title=f"Rising complaints: {cat.name_en if cat else 'category'} in {ctx.pop('unit_name')}",
                reasons=[
                    f"{recent} complaints in the last {c['recent_days']} days against a baseline of "
                    f"{weekly_baseline:.1f} for the same period ({ratio:.1f}x; threshold {c['ratio']}x)."
                ],
                metrics={
                    "recent": recent,
                    "baseline": round(weekly_baseline, 2),
                    "ratio": round(ratio, 2),
                },
                dedup_key=f"volume_spike:{cat_id}:{block_id}",
                grievance_ids=list(ids or []),
                category_id=cat_id,
                **ctx,
            )

    for a in created:
        if a.level in ("high", "critical"):
            recipients = users_with_permission_in_scope(
                db,
                "alert.act",
                district_id=a.district_id,
                block_id=a.block_id,
                department_id=a.department_id,
            )
            notify_many(
                db,
                recipients,
                "alert",
                f"{a.level.upper()} alert: {a.title}",
                "; ".join(a.reasons)[:500],
                f"/early-warning/{a.id}",
            )
    return {"evaluated": touched, "new_alerts": len(created)}


def _unit_context(db: Session, level: str, unit_id: uuid.UUID) -> dict[str, Any]:
    if level == "village":
        v = db.get(Village, unit_id)
        return {
            "village_id": unit_id,
            "block_id": v.block_id if v else None,
            "district_id": v.district_id if v else None,
            "unit_name": v.name_en if v else "village",
        }
    if level == "block":
        b = db.get(Block, unit_id)
        return {
            "block_id": unit_id,
            "district_id": b.district_id if b else None,
            "unit_name": b.name_en if b else "block",
        }
    return {"unit_name": level}


def scope_clause(user: CurrentUser) -> ColumnElement[bool]:
    units = unit_scope_ids(user)
    clauses: list[ColumnElement[bool]] = []
    if units["district"]:
        clauses.append(EarlyWarningAlert.district_id.in_(units["district"]))
    if units["block"]:
        clauses.append(EarlyWarningAlert.block_id.in_(units["block"]))
    if units["department"]:
        clauses.append(EarlyWarningAlert.department_id.in_(units["department"]))
    return or_(*clauses) if clauses else false()


def get_alert(db: Session, user: CurrentUser, alert_id: uuid.UUID, *, lock: bool = False) -> EarlyWarningAlert:
    stmt = select(EarlyWarningAlert).where(EarlyWarningAlert.id == alert_id, scope_clause(user))
    if lock:
        stmt = stmt.with_for_update()
    a = db.execute(stmt).scalar_one_or_none()
    if a is None:
        raise NotFoundError("Alert not found.")
    return a


def act(
    db: Session, user: CurrentUser, alert_id: uuid.UUID, action: str, reason: str, meta: RequestMeta
) -> EarlyWarningAlert:
    if action not in ACTION_TRANSITIONS:
        raise AppError("Unknown action.", code="invalid_action")
    if len(reason.strip()) < 5:
        raise AppError("A reason is required.", code="reason_required")
    a = get_alert(db, user, alert_id, lock=True)
    froms, to = ACTION_TRANSITIONS[action]
    if a.status not in froms:
        raise ConflictError(f"'{action}' is not allowed while the alert is '{a.status}'.")
    previous = a.status
    if to:
        a.status = to
        if to in ("dismissed", "resolved"):
            a.closed_at = now()
    db.add(
        AlertAction(
            alert_id=a.id,
            action=action,
            reason=reason.strip(),
            from_status=previous,
            to_status=a.status,
            actor_user_id=user.id,
        )
    )
    if action == "escalate":
        recipients = users_with_permission_in_scope(db, "alert.act", district_id=a.district_id)
        notify_many(
            db,
            [r for r in recipients if r != user.id],
            "alert",
            f"Alert escalated: {a.title}",
            reason[:500],
            f"/early-warning/{a.id}",
        )
    audit.record(
        db,
        action=f"alert.{action}",
        actor=user.actor,
        resource_type="alert",
        resource_id=a.id,
        details={"from": previous, "to": a.status},
        meta=meta,
    )
    return a
