"""SLA application, breach scanning, escalation and performance metrics."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.audit import service as audit
from app.modules.audit.service import SYSTEM_ACTOR, Actor
from app.modules.grievances.models import OPEN_STATUSES, Grievance
from app.modules.notifications.service import notify_many, users_with_permission_in_scope
from app.modules.performance.models import (
    DepartmentPerformanceSnapshot,
    Escalation,
    SlaEvent,
    SlaPolicy,
)


def now() -> datetime:
    return datetime.now(UTC)


def select_policy(db: Session, category_id: uuid.UUID | None, priority: str) -> SlaPolicy | None:
    """Most specific active policy: category+priority > category > priority > default."""
    candidates = (
        db.execute(
            select(SlaPolicy).where(
                SlaPolicy.is_active.is_(True),
                or_(SlaPolicy.category_id == category_id, SlaPolicy.category_id.is_(None)),
                or_(SlaPolicy.priority == priority, SlaPolicy.priority.is_(None)),
            )
        )
        .scalars()
        .all()
    )

    def specificity(p: SlaPolicy) -> tuple[int, int]:
        return (1 if p.category_id else 0, 1 if p.priority else 0)

    return max(candidates, key=specificity, default=None)


def apply_sla(db: Session, g: Grievance, *, start: datetime | None = None, cycle: int = 0) -> None:
    policy = select_policy(db, g.category_id, g.priority)
    g.sla_policy_id = policy.id if policy else None
    base = start or g.registered_at or now()
    g.due_at = base + timedelta(hours=policy.resolution_hours) if policy else None
    if policy:
        _event(db, g, "started" if cycle == 0 else "restarted", cycle, policy.id)


def _event(db: Session, g: Grievance, event_type: str, cycle: int, policy_id: uuid.UUID | None) -> bool:
    res = db.execute(
        insert(SlaEvent)
        .values(
            grievance_id=g.id,
            event_type=event_type,
            cycle=cycle,
            sla_policy_id=policy_id,
            due_at=g.due_at,
        )
        .on_conflict_do_nothing(index_elements=["grievance_id", "event_type", "cycle"])
        .returning(SlaEvent.id)
    )
    # rowcount is not reliable for INSERT .. ON CONFLICT; RETURNING yields a row only if inserted.
    return res.scalar() is not None


def record_resolution(db: Session, g: Grievance) -> None:
    if g.due_at is None:
        return
    _event(
        db,
        g,
        "met" if (g.resolved_at or now()) <= g.due_at else "missed",
        g.reopened_count,
        g.sla_policy_id,
    )


def escalate(db: Session, g: Grievance, *, reason: str, trigger: str, actor: Actor, meta: Any = None) -> Escalation:
    g.escalation_level += 1
    esc = Escalation(
        grievance_id=g.id,
        level=g.escalation_level,
        trigger=trigger,
        reason=reason,
        created_by=actor.user_id,
        escalated_to_role="senior_officers_in_scope",
    )
    db.add(esc)
    db.flush()
    recipients = users_with_permission_in_scope(db, "grievance.verify", district_id=g.district_id)
    recipients += users_with_permission_in_scope(db, "grievance.assign", department_id=g.department_id)
    notify_many(
        db,
        recipients,
        "escalation",
        f"Grievance {g.reference_no} escalated (level {g.escalation_level})",
        reason[:500],
        f"/grievances/{g.id}",
    )
    audit.record(
        db,
        action="grievance.escalated",
        actor=actor,
        resource_type="grievance",
        resource_id=g.id,
        details={"level": g.escalation_level, "trigger": trigger},
        meta=meta,
    )
    return esc


def scan_sla(db: Session) -> dict[str, int]:
    """Record warnings and breaches for open grievances; auto-escalate on breach."""
    t = now()
    breached = warned = 0
    rows = db.execute(
        select(Grievance, SlaPolicy)
        .join(SlaPolicy, SlaPolicy.id == Grievance.sla_policy_id)
        .where(Grievance.status.in_(OPEN_STATUSES), Grievance.due_at.is_not(None))
        .with_for_update(of=Grievance, skip_locked=True)
    ).all()
    for g, policy in rows:
        assert g.due_at is not None
        total = g.due_at - g.registered_at
        if g.due_at <= t:
            if _event(db, g, "breached", g.reopened_count, policy.id):
                breached += 1
                escalate(
                    db,
                    g,
                    reason=f"Resolution time limit ({policy.resolution_hours} h, policy '{policy.name}') exceeded.",
                    trigger="sla_breach",
                    actor=SYSTEM_ACTOR,
                )
        elif t >= g.registered_at + total * (policy.warning_percent / 100) and _event(
            db, g, "warning", g.reopened_count, policy.id
        ):
            warned += 1
            if g.assigned_officer_id:
                notify_many(
                    db,
                    [g.assigned_officer_id],
                    "sla",
                    f"Grievance {g.reference_no} is nearing its due time",
                    f"Due {g.due_at.isoformat()}",
                    f"/grievances/{g.id}",
                )
    return {"breached": breached, "warned": warned}


def overdue_clause(t: datetime | None = None) -> Any:
    return and_(
        Grievance.status.in_(OPEN_STATUSES),
        Grievance.due_at.is_not(None),
        Grievance.due_at < (t or now()),
    )


def performance_by(
    db: Session,
    group_col: Any | None,
    scope_clause: Any,
    since: datetime | None,
    until: datetime | None,
) -> list[dict[str, Any]]:
    """Metrics grouped by ``group_col``, or overall totals when it is None."""
    t = now()
    conds = [scope_clause]
    if since:
        conds.append(Grievance.registered_at >= since)
    if until:
        conds.append(Grievance.registered_at < until)
    resolved = Grievance.resolved_at.is_not(None)
    hours = func.extract("epoch", Grievance.resolved_at - Grievance.registered_at) / 3600
    stmt = select(
        (group_col if group_col is not None else literal(None)).label("key"),
        func.count().label("received"),
        func.count().filter(Grievance.status.in_(OPEN_STATUSES)).label("open"),
        func.count().filter(resolved).label("resolved"),
        func.count().filter(overdue_clause(t)).label("overdue"),
        func.count()
        .filter(resolved, Grievance.due_at.is_not(None), Grievance.resolved_at <= Grievance.due_at)
        .label("within_sla"),
        func.count().filter(resolved, Grievance.due_at.is_not(None)).label("resolved_with_sla"),
        func.count().filter(Grievance.reopened_count > 0).label("reopened"),
        func.count().filter(Grievance.escalation_level > 0).label("escalated"),
        func.avg(case((resolved, hours))).label("avg_hours"),
    ).where(*conds)
    if group_col is not None:
        stmt = stmt.group_by(group_col)
    out = []
    for r in db.execute(stmt).mappings():
        row = dict(r)
        row["sla_compliance_pct"] = (
            round(100 * row["within_sla"] / row["resolved_with_sla"], 1) if row["resolved_with_sla"] else None
        )
        row["resolution_rate_pct"] = round(100 * row["resolved"] / row["received"], 1) if row["received"] else None
        row["avg_hours"] = round(float(row["avg_hours"]), 1) if row["avg_hours"] is not None else None
        out.append(row)
    return out


def take_snapshots(db: Session, snapshot_date: date | None = None) -> int:
    from sqlalchemy import true

    day = snapshot_date or now().date()
    rows = performance_by(db, Grievance.department_id, true(), None, None)
    n = 0
    for r in rows:
        if r["key"] is None:
            continue
        stmt = (
            insert(DepartmentPerformanceSnapshot)
            .values(
                snapshot_date=day,
                department_id=r["key"],
                received_total=r["received"],
                open_total=r["open"],
                resolved_total=r["resolved"],
                overdue_total=r["overdue"],
                resolved_within_sla=r["within_sla"],
                reopened_total=r["reopened"],
                escalated_total=r["escalated"],
                avg_resolution_hours=r["avg_hours"],
                metrics={"sla_compliance_pct": r["sla_compliance_pct"]},
            )
            .on_conflict_do_update(
                index_elements=["snapshot_date", "department_id"],
                set_={
                    "received_total": r["received"],
                    "open_total": r["open"],
                    "resolved_total": r["resolved"],
                    "overdue_total": r["overdue"],
                    "resolved_within_sla": r["within_sla"],
                    "reopened_total": r["reopened"],
                    "escalated_total": r["escalated"],
                    "avg_resolution_hours": r["avg_hours"],
                    "computed_at": func.now(),
                },
            )
        )
        db.execute(stmt)
        n += 1
    return n
