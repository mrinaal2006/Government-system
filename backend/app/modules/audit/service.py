"""Audit logging with a tamper-evident hash chain.

``record`` writes in the caller's transaction, so an audited action and its audit
row commit or roll back together. ``record_independent`` commits in its own
transaction; it is used for security events (failed logins, denied access) that
must be kept even though the request itself fails.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.logging import redact
from app.core.request_meta import RequestMeta
from app.modules.audit.models import AuditLog

logger = logging.getLogger("app.audit")
GENESIS_HASH = "0" * 64
_CHAIN_LOCK_KEY = 771_000_001


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID | None
    username: str | None


SYSTEM_ACTOR = Actor(None, "system")


def _canonical(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _payload(entry: AuditLog) -> dict[str, Any]:
    return {
        "occurred_at": entry.occurred_at.astimezone(UTC).isoformat(),
        "actor_user_id": str(entry.actor_user_id) if entry.actor_user_id else None,
        "actor_username": entry.actor_username,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "outcome": entry.outcome,
        "ip_address": str(entry.ip_address) if entry.ip_address else None,
        "request_id": entry.request_id,
        "details": entry.details,
    }


def compute_hash(prev_hash: str, entry: AuditLog) -> str:
    return hashlib.sha256((prev_hash + _canonical(_payload(entry))).encode()).hexdigest()


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def record(
    db: Session,
    *,
    action: str,
    actor: Actor = SYSTEM_ACTOR,
    outcome: str = "success",
    resource_type: str | None = None,
    resource_id: object | None = None,
    details: dict[str, Any] | None = None,
    meta: RequestMeta | None = None,
) -> AuditLog:
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CHAIN_LOCK_KEY})
    prev = db.execute(select(AuditLog.row_hash).order_by(AuditLog.seq.desc()).limit(1)).scalar()
    entry = AuditLog(
        occurred_at=datetime.now(UTC),
        actor_user_id=actor.user_id,
        actor_username=actor.username,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        outcome=outcome,
        ip_address=meta.ip if meta else None,
        user_agent=meta.user_agent if meta else None,
        request_id=meta.request_id if meta else None,
        details=_json_safe(redact(details or {})),
        prev_hash=prev or GENESIS_HASH,
        row_hash="",
    )
    entry.row_hash = compute_hash(entry.prev_hash, entry)
    db.add(entry)
    db.flush()
    return entry


def record_independent(**kwargs: Any) -> None:
    from app.db.session import get_session_factory

    try:
        with get_session_factory()() as db, db.begin():
            record(db, **kwargs)
    except Exception:
        logger.exception("audit_write_failed", extra={"audit_action": kwargs.get("action")})


def verify_chain(db: Session, *, limit: int | None = None) -> dict[str, Any]:
    stmt = select(AuditLog).order_by(AuditLog.seq)
    prev = GENESIS_HASH
    checked = 0
    for entry in db.execute(stmt).scalars().yield_per(1000):
        if entry.prev_hash != prev or compute_hash(prev, entry) != entry.row_hash:
            return {"valid": False, "checked": checked, "first_invalid_seq": entry.seq}
        prev = entry.row_hash
        checked += 1
        if limit and checked >= limit:
            break
    return {"valid": True, "checked": checked, "first_invalid_seq": None}
