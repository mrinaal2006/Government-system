"""Explainable intelligence services.

Methods (all deterministic; no trained ML model is used, so no accuracy is claimed):

* ``category``   - keyword rules maintained by administrators (intel.classification_rules).
                   Confidence = matched weight / total matched weight across categories.
* ``department`` - the configured default department of the suggested category.
* ``location``   - exact (case/space-insensitive) matches of official unit names from
                   the reference tables in the complaint text.
* ``summary``    - extractive: the leading sentences of the description.
* duplicates     - PostgreSQL trigram similarity within the same area and time window,
                   plus same-complainant (HMAC of mobile number) + same category.
* clusters       - grievances with the same category in the same unit within a window.
* risk           - weighted factors from the active, versioned risk model.

Outputs are stored with model id/version, confidence, evidence and an input hash.
Suggestions change a grievance ONLY through ``review_classification`` by an officer.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.request_meta import RequestMeta
from app.modules.administration.models import IssueCategory
from app.modules.audit import service as audit
from app.modules.geography.models import Block, GramPanchayat, Village, Ward
from app.modules.grievances.models import OPEN_STATUSES, Complainant, Grievance
from app.modules.iam.service import CurrentUser
from app.modules.intelligence.models import (
    AIClassification,
    AIClassificationHistory,
    ClassificationRule,
    ClusterMember,
    DuplicateCandidate,
    GrievanceCluster,
    RiskAssessment,
    RiskModel,
)

logger = logging.getLogger("app.intelligence")

RULES_MODEL = "keyword-rules"
LOCATION_MODEL = "gazetteer-match"
SUMMARY_MODEL = "extractive-lead"
SUMMARY_VERSION = "1"
DUPLICATE_METHOD = "trigram+complainant-hash/1"
CLUSTER_METHOD = "category-unit-window/1"


def now() -> datetime:
    return datetime.now(UTC)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s.lower())).strip()


def input_ref(g: Grievance) -> str:
    digest = hashlib.sha256((g.subject + "\n" + g.description).encode()).hexdigest()[:32]
    return f"grievance:{g.id}:sha256:{digest}"


def active_risk_model(db: Session) -> RiskModel:
    m = db.execute(select(RiskModel).where(RiskModel.is_active.is_(True))).scalar_one_or_none()
    if m is None:
        raise AppError("No active risk model is configured.", code="no_risk_model")
    return m


def _store(
    db: Session,
    g: Grievance,
    task: str,
    model_id: str,
    version: str,
    prediction: dict[str, Any],
    confidence: float | None,
    evidence: list[Any],
    status: str,
) -> AIClassification:
    # Supersede earlier pending suggestions for the same task.
    db.execute(
        update(AIClassification)
        .where(
            AIClassification.grievance_id == g.id,
            AIClassification.task == task,
            AIClassification.verification_status == "pending",
        )
        .values(verification_status="not_applicable")
    )
    row = AIClassification(
        grievance_id=g.id,
        task=task,
        model_id=model_id,
        model_version=version,
        prediction=prediction,
        confidence=Decimal(str(round(confidence, 4))) if confidence is not None else None,
        input_ref=input_ref(g),
        processing_status=status,
        evidence=evidence,
        verification_status="pending" if status == "completed" else "not_applicable",
    )
    db.add(row)
    db.flush()
    db.add(AIClassificationHistory(classification_id=row.id, event="created", snapshot=_snapshot(row)))
    return row


def _snapshot(c: AIClassification) -> dict[str, Any]:
    return {
        "prediction": c.prediction,
        "confidence": float(c.confidence) if c.confidence is not None else None,
        "verification_status": c.verification_status,
        "verified_value": c.verified_value,
        "model_id": c.model_id,
        "model_version": c.model_version,
    }


# --- Category / department -----------------------------------------------------------------


def rules_version(db: Session) -> str:
    rows = db.execute(
        select(
            ClassificationRule.id,
            ClassificationRule.keyword,
            ClassificationRule.weight,
            ClassificationRule.updated_at,
        )
        .where(ClassificationRule.is_active.is_(True))
        .order_by(ClassificationRule.id)
    ).all()
    return hashlib.sha256(repr(rows).encode()).hexdigest()[:12] if rows else "empty"


def classify_category(db: Session, g: Grievance) -> AIClassification:
    text_n = " " + _norm(g.subject + " " + g.description) + " "
    rules = db.execute(
        select(ClassificationRule, IssueCategory)
        .join(IssueCategory, IssueCategory.id == ClassificationRule.category_id)
        .where(ClassificationRule.is_active.is_(True), IssueCategory.is_active.is_(True))
    ).all()
    version = rules_version(db)
    scores: dict[uuid.UUID, float] = {}
    evidence: dict[uuid.UUID, list[str]] = {}
    cats: dict[uuid.UUID, IssueCategory] = {}
    for rule, cat in rules:
        kw = " " + _norm(rule.keyword) + " "
        if kw.strip() and kw in text_n:
            scores[cat.id] = scores.get(cat.id, 0.0) + float(rule.weight)
            evidence.setdefault(cat.id, []).append(rule.keyword)
            cats[cat.id] = cat
    if not scores:
        return _store(
            db,
            g,
            "category",
            RULES_MODEL,
            version,
            {},
            None,
            [{"note": "No configured keyword matched" if rules else "No classification rules are configured"}],
            "no_prediction",
        )
    best = max(scores, key=lambda k: scores[k])
    total = sum(scores.values())
    cat = cats[best]
    top_level = cat.parent_id or cat.id
    pred = {
        "category_id": str(top_level),
        "subcategory_id": str(cat.id) if cat.parent_id else None,
        "category_name": cat.name_en,
    }
    alternatives = [
        {"category_id": str(k), "name": cats[k].name_en, "score": v}
        for k, v in sorted(scores.items(), key=lambda kv: -kv[1])
        if k != best
    ][:3]
    c = _store(
        db,
        g,
        "category",
        RULES_MODEL,
        version,
        pred,
        scores[best] / total,
        [{"matched_keywords": evidence[best]}, {"alternatives": alternatives}],
        "completed",
    )
    parent = db.get(IssueCategory, top_level) if cat.parent_id else None
    dep_id = cat.default_department_id or (parent.default_department_id if parent else None)
    if dep_id:
        _store(
            db,
            g,
            "department",
            RULES_MODEL,
            version,
            {"department_id": str(dep_id)},
            scores[best] / total,
            [
                {
                    "rule": "configured default department of suggested category",
                    "category": cat.name_en,
                }
            ],
            "completed",
        )
    return c


# --- Location ---------------------------------------------------------------------------------


def extract_location(db: Session, g: Grievance) -> AIClassification:
    text_n = " " + _norm(g.subject + " " + g.description + " " + (g.location_text or "")) + " "
    matches: list[dict[str, Any]] = []
    for level, model in (("village", Village), ("gram_panchayat", GramPanchayat), ("block", Block)):
        stmt = select(model.id, model.name_en).where(model.is_active.is_(True))
        if g.district_id and hasattr(model, "district_id"):
            stmt = stmt.where(model.district_id == g.district_id)
        for uid, name in db.execute(stmt).all():
            n = _norm(name)
            if len(n) >= 4 and f" {n} " in text_n:
                matches.append({"level": level, "id": str(uid), "name": name})
    for uid, num, muni in db.execute(select(Ward.id, Ward.ward_number, Ward.municipality_id)).all():
        if g.municipality_id and muni == g.municipality_id and f" ward {num.lower()} " in text_n:
            matches.append({"level": "ward", "id": str(uid), "name": f"Ward {num}"})
    if not matches:
        return _store(
            db,
            g,
            "location",
            LOCATION_MODEL,
            "1",
            {},
            None,
            [{"note": "No official unit name found in the text"}],
            "no_prediction",
        )
    rank = {"ward": 0, "village": 1, "gram_panchayat": 2, "block": 3}
    best = sorted(matches, key=lambda m: rank[m["level"]])[0]
    same_level = [m for m in matches if m["level"] == best["level"]]
    confidence = 1.0 / len(same_level)  # ambiguity lowers confidence
    return _store(
        db,
        g,
        "location",
        LOCATION_MODEL,
        "1",
        {f"{best['level']}_id": best["id"], "name": best["name"], "level": best["level"]},
        confidence,
        [{"matched_names": matches}],
        "completed",
    )


# --- Summary --------------------------------------------------------------------------------------


def summarise(db: Session, g: Grievance, max_chars: int = 280) -> AIClassification:
    sentences = re.split(r"(?<=[.!?।])\s+", g.description.strip())
    out = ""
    for s in sentences:
        if len(out) + len(s) + 1 > max_chars:
            break
        out = (out + " " + s).strip()
    if not out:
        out = g.description.strip()[: max_chars - 1] + "…"
    g.summary = out
    return _store(
        db,
        g,
        "summary",
        SUMMARY_MODEL,
        SUMMARY_VERSION,
        {"summary": out},
        None,
        [{"method": "leading sentences of the description, unchanged"}],
        "completed",
    )


# --- Duplicates ------------------------------------------------------------------------------------


def find_duplicates(db: Session, g: Grievance) -> list[DuplicateCandidate]:
    params = active_risk_model(db).parameters.get("duplicate", {})
    threshold = float(params.get("similarity_threshold", 0.55))
    window = timedelta(days=int(params.get("window_days", 30)))
    area_conds = []
    if g.village_id:
        area_conds.append("village_id = :village")
    elif g.block_id:
        area_conds.append("block_id = :block")
    elif g.ward_id:
        area_conds.append("ward_id = :ward")
    # area_conds contains only the constant fragments above; all values are bound parameters.
    sql = (
        "SELECT id, similarity(description, :d) AS sim FROM grievance.grievances "  # noqa: S608
        "WHERE id <> :id AND registered_at >= :since "
        + ("AND " + " AND ".join(area_conds) + " " if area_conds else "")
        + "AND similarity(description, :d) >= :t ORDER BY sim DESC LIMIT 10"
    )
    rows = db.execute(
        text(sql),
        {
            "d": g.description,
            "id": g.id,
            "since": g.registered_at - window,
            "t": threshold,
            "village": g.village_id,
            "block": g.block_id,
            "ward": g.ward_id,
        },
    ).all()
    found: dict[uuid.UUID, tuple[float, list[Any]]] = {
        r.id: (float(r.sim), [{"text_similarity": round(float(r.sim), 3)}]) for r in rows
    }
    if g.complainant_id:
        mh = db.execute(select(Complainant.mobile_hash).where(Complainant.id == g.complainant_id)).scalar()
        if mh:
            same = db.execute(
                select(Grievance.id)
                .join(Complainant, Complainant.id == Grievance.complainant_id)
                .where(
                    Complainant.mobile_hash == mh,
                    Grievance.id != g.id,
                    Grievance.registered_at >= g.registered_at - window,
                    Grievance.category_id == g.category_id if g.category_id else Grievance.category_id.is_(None),
                )
            ).scalars()
            for gid in same:
                sim, ev = found.get(gid, (0.0, []))
                found[gid] = (max(sim, 0.9), [*ev, {"same_complainant_and_category": True}])
    out = []
    for gid, (sim, ev) in found.items():
        stmt = (
            insert(DuplicateCandidate)
            .values(
                grievance_id=g.id,
                candidate_grievance_id=gid,
                similarity=Decimal(str(round(sim, 4))),
                method=DUPLICATE_METHOD,
                evidence=ev,
            )
            .on_conflict_do_nothing()
            .returning(DuplicateCandidate.id)
        )
        new_id = db.execute(stmt).scalar()
        if new_id:
            out.append(db.get(DuplicateCandidate, new_id))
    return [c for c in out if c is not None]


# --- Risk ------------------------------------------------------------------------------------------


def assess_risk(db: Session, g: Grievance, model: RiskModel | None = None) -> RiskAssessment:
    model = model or active_risk_model(db)
    p = model.parameters["risk_factors"]
    levels = model.parameters["levels"]
    t = now()
    factors: list[dict[str, Any]] = []

    def add(name: str, points: float, detail: str) -> None:
        if points > 0:
            factors.append({"factor": name, "points": round(points, 2), "detail": detail})

    if g.status in OPEN_STATUSES and g.due_at and g.due_at < t:
        days = (t - g.due_at).days
        add(
            "overdue",
            p["overdue"] + min(days * p["overdue_per_day"], p["overdue_per_day_cap"]),
            f"Overdue by {days} day(s)",
        )
    if g.reopened_count:
        add(
            "reopened",
            min(g.reopened_count * p["reopened_each"], p["reopened_cap"]),
            f"Reopened {g.reopened_count} time(s)",
        )
    if g.escalation_level:
        add(
            "escalated",
            min(g.escalation_level * p["escalation_level_each"], p["escalation_cap"]),
            f"Escalation level {g.escalation_level}",
        )
    if g.category_id:
        cat = db.get(IssueCategory, g.category_id)
        if cat and cat.is_essential_service:
            add(
                "essential_service",
                p["essential_service"],
                f"Essential service category: {cat.name_en}",
            )
    in_cluster = db.execute(
        select(func.count())
        .select_from(ClusterMember)
        .join(GrievanceCluster, GrievanceCluster.id == ClusterMember.cluster_id)
        .where(ClusterMember.grievance_id == g.id)
    ).scalar_one()
    if in_cluster:
        add(
            "in_cluster",
            p["in_cluster"],
            "Part of a cluster of similar complaints in the same area",
        )
    if g.priority == "urgent":
        add("priority", p["priority_urgent"], "Priority: urgent")
    elif g.priority == "high":
        add("priority", p["priority_high"], "Priority: high")
    score = sum(f["points"] for f in factors)
    level = "normal"
    for name in ("watch", "high", "critical"):
        if score >= levels[name]:
            level = name
    db.execute(
        update(RiskAssessment)
        .where(RiskAssessment.grievance_id == g.id, RiskAssessment.is_current.is_(True))
        .values(is_current=False)
    )
    ra = RiskAssessment(
        grievance_id=g.id,
        risk_model_version=model.version,
        score=Decimal(str(round(score, 2))),
        level=level,
        factors=factors,
        is_current=True,
    )
    db.add(ra)
    db.flush()
    return ra


def assess_all_open(db: Session) -> int:
    model = active_risk_model(db)
    n = 0
    for g in db.execute(select(Grievance).where(Grievance.status.in_(OPEN_STATUSES))).scalars():
        assess_risk(db, g, model)
        n += 1
    return n


# --- Clusters -----------------------------------------------------------------------------------


def compute_clusters(db: Session) -> int:
    params = active_risk_model(db).parameters["cluster"]
    window_days, min_count = int(params["window_days"]), int(params["min_count"])
    t = now()
    since = t - timedelta(days=window_days)
    db.execute(delete(GrievanceCluster).where(GrievanceCluster.window_end < t - timedelta(days=1)))
    created = 0
    for level, col in (
        ("village", Grievance.village_id),
        ("ward", Grievance.ward_id),
        ("block", Grievance.block_id),
    ):
        rows = db.execute(
            select(
                Grievance.category_id,
                col,
                func.array_agg(Grievance.id),
                func.count(),
                func.count().filter(Grievance.status.in_(OPEN_STATUSES)),
            )
            .where(
                Grievance.registered_at >= since,
                col.is_not(None),
                Grievance.category_id.is_not(None),
            )
            .group_by(Grievance.category_id, col)
            .having(func.count() >= min_count)
        ).all()
        for cat_id, unit_id, ids, count, open_count in rows:
            key = f"{level}:{unit_id}:{cat_id}:{window_days}d"
            stmt = (
                insert(GrievanceCluster)
                .values(
                    cluster_key=key,
                    category_id=cat_id,
                    unit_level=level,
                    unit_id=unit_id,
                    window_start=since,
                    window_end=t,
                    grievance_count=count,
                    open_count=open_count,
                    method_version=CLUSTER_METHOD,
                    evidence={
                        "rule": f">= {min_count} grievances of the same category in the same {level} within {window_days} days"
                    },
                )
                .on_conflict_do_update(
                    index_elements=["cluster_key"],
                    set_={
                        "window_start": since,
                        "window_end": t,
                        "grievance_count": count,
                        "open_count": open_count,
                        "computed_at": func.now(),
                    },
                )
                .returning(GrievanceCluster.id)
            )
            cid = db.execute(stmt).scalar_one()
            db.execute(delete(ClusterMember).where(ClusterMember.cluster_id == cid))
            for gid in ids:
                db.execute(insert(ClusterMember).values(cluster_id=cid, grievance_id=gid).on_conflict_do_nothing())
            created += 1
    return created


# --- Pipeline ------------------------------------------------------------------------------------


def analyse(db: Session, grievance_id: uuid.UUID) -> dict[str, Any]:
    g = db.get(Grievance, grievance_id)
    if g is None:
        raise NotFoundError()
    results = {}
    for name, fn in (
        ("category", classify_category),
        ("location", extract_location),
        ("summary", summarise),
    ):
        try:
            results[name] = fn(db, g).processing_status
        except Exception:
            logger.exception("ai_task_failed", extra={"task": name})
            _store(db, g, name, "pipeline", "1", {}, None, [{"error": "processing failed"}], "failed")
            results[name] = "failed"
    find_duplicates(db, g)
    results["risk"] = assess_risk(db, g).level
    return results


def enqueue_analysis(grievance_id: uuid.UUID) -> None:
    """Queue analysis after commit; failure to queue never blocks registration."""
    try:
        from app.worker.tasks import analyse_grievance

        analyse_grievance.apply_async(args=[str(grievance_id)], countdown=2)
    except Exception:  # noqa: BLE001
        logger.warning("ai_enqueue_failed", extra={"grievance_id": str(grievance_id)})


# --- Human review -------------------------------------------------------------------------------


def review_classification(
    db: Session,
    user: CurrentUser,
    cid: uuid.UUID,
    decision: str,
    value: dict[str, Any] | None,
    note: str | None,
    meta: RequestMeta,
) -> AIClassification:
    from app.modules.grievances import service as gsvc

    c = db.execute(select(AIClassification).where(AIClassification.id == cid).with_for_update()).scalar_one_or_none()
    if c is None:
        raise NotFoundError()
    g = gsvc.get_scoped(db, user, c.grievance_id, lock=True)
    if c.verification_status != "pending":
        raise ConflictError("This suggestion has already been reviewed or superseded.")
    if decision not in {"accept", "edit", "reject"}:
        raise AppError("Unknown decision.", code="invalid_decision")
    applied = c.prediction if decision == "accept" else (value or {})
    if decision == "edit" and not value:
        raise AppError("Provide the corrected value.", code="value_required")
    if decision in {"accept", "edit"} and c.task in {"category", "department", "location"}:
        changes: dict[str, Any] = {}
        for k in (
            "category_id",
            "subcategory_id",
            "department_id",
            "village_id",
            "gram_panchayat_id",
            "block_id",
            "ward_id",
        ):
            if applied.get(k):
                changes[k] = uuid.UUID(str(applied[k]))
        if changes:
            gsvc.update_details(
                db,
                user,
                g.id,
                changes,
                g.version,
                meta,
                reason=f"AI suggestion {decision}ed by officer ({c.model_id} {c.model_version})",
            )
    c.verification_status = {"accept": "accepted", "edit": "edited", "reject": "rejected"}[decision]
    c.verified_value = applied if decision != "reject" else None
    c.verified_by, c.verified_at, c.review_note = user.id, now(), note
    db.add(
        AIClassificationHistory(
            classification_id=c.id,
            event=f"reviewed_{decision}",
            snapshot=_snapshot(c),
            actor_user_id=user.id,
        )
    )
    audit.record(
        db,
        action="ai.suggestion_reviewed",
        actor=user.actor,
        resource_type="grievance",
        resource_id=g.id,
        details={"classification_id": str(c.id), "task": c.task, "decision": decision},
        meta=meta,
    )
    return c


def review_duplicate(
    db: Session, user: CurrentUser, dup_id: uuid.UUID, confirm: bool, meta: RequestMeta
) -> DuplicateCandidate:
    from app.modules.grievances import service as gsvc

    d = db.get(DuplicateCandidate, dup_id, with_for_update=True)
    if d is None:
        raise NotFoundError()
    gsvc.get_scoped(db, user, d.grievance_id)
    if d.status != "pending":
        raise ConflictError("Already reviewed.")
    d.status, d.reviewed_by, d.reviewed_at = (
        ("confirmed" if confirm else "rejected"),
        user.id,
        now(),
    )
    if confirm:
        gsvc.link(
            db,
            user,
            d.grievance_id,
            d.candidate_grievance_id,
            "duplicate_of",
            "Confirmed duplicate candidate",
            meta,
        )
    audit.record(
        db,
        action="ai.duplicate_reviewed",
        actor=user.actor,
        resource_type="grievance",
        resource_id=d.grievance_id,
        details={"candidate": str(d.candidate_grievance_id), "confirmed": confirm},
        meta=meta,
    )
    return d
