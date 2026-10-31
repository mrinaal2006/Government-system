"""Citizen portal: registration, mobile verification, sign-in, filing and tracking."""

from __future__ import annotations

import hmac
import logging
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Environment, get_settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.ratelimit import hit
from app.core.request_meta import RequestMeta
from app.modules.administration.models import GrievanceSource
from app.modules.audit import service as audit
from app.modules.citizen_portal.models import CitizenAccount, CitizenSession, OtpChallenge
from app.modules.grievances.models import Grievance, GrievanceStatusHistory

logger = logging.getLogger("app.citizen")

CONSENT_VERSION = "2026-10"
OTP_TTL = timedelta(minutes=10)
OTP_MAX_ATTEMPTS = 5
_MOBILE = re.compile(r"^(?:\+91|91|0)?([6-9]\d{9})$")

# What citizens see: no internal workflow detail, no officer identities.
PUBLIC_STATUS = {
    "registered": "Received",
    "assigned": "Assigned to the responsible office",
    "in_progress": "Action in progress",
    "resolution_submitted": "Action taken, under verification",
    "resolved": "Resolved",
    "closed": "Closed",
    "reopened": "Reopened for further action",
}


class CitizenAuthError(AppError):
    status_code = 401
    code = "authentication_failed"
    message = "Invalid mobile number or password."


def now() -> datetime:
    return datetime.now(UTC)


def normalize_mobile(raw: str) -> str:
    m = _MOBILE.fullmatch(re.sub(r"[\s-]", "", raw or ""))
    if not m:
        raise AppError("Enter a valid 10-digit Indian mobile number.", code="invalid_mobile")
    return "+91" + m.group(1)


def _account_by_mobile(db: Session, mobile: str, *, lock: bool = False) -> CitizenAccount | None:
    stmt = select(CitizenAccount).where(CitizenAccount.mobile_hash == security.lookup_hash(mobile))
    if lock:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def _actor(account: CitizenAccount) -> audit.Actor:
    return audit.Actor(None, f"citizen:{str(account.id)[:8]}")


def _code_hash(account_id: uuid.UUID, code: str) -> str:
    return security.lookup_hash(f"otp:{account_id}:{code}") or ""


# --- One-time codes ------------------------------------------------------------------------


def issue_otp(db: Session, account: CitizenAccount) -> str | None:
    """Create a fresh code and send it. Returns the code only in development (console provider)."""
    hit(f"otp-send:{account.id}", 1, window_seconds=60, fail_closed=True)
    hit(f"otp-send-hour:{account.id}", 5, window_seconds=3600, fail_closed=True)
    db.execute(
        update(OtpChallenge)
        .where(OtpChallenge.account_id == account.id, OtpChallenge.consumed_at.is_(None))
        .values(consumed_at=now())
    )
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        OtpChallenge(
            account_id=account.id,
            purpose="verify_mobile",
            code_hash=_code_hash(account.id, code),
            expires_at=now() + OTP_TTL,
        )
    )
    db.flush()
    settings = get_settings()
    if settings.citizen_otp_provider == "console":
        # DEVELOPMENT ONLY: production refuses to enable the portal with this provider.
        mobile = security.decrypt_text(account.mobile_encrypted) or ""
        logger.warning("DEVELOPMENT one-time code for %s: %s", security.mask(mobile, 4), code)
        return code if settings.app_env in (Environment.DEVELOPMENT, Environment.TEST) else None
    raise AppError("No SMS provider is configured.", code="otp_unavailable")


def verify_mobile(db: Session, mobile: str, code: str, meta: RequestMeta) -> CitizenAccount:
    mobile = normalize_mobile(mobile)
    hit(f"otp-verify:{security.lookup_hash(mobile)}", 10, window_seconds=3600, fail_closed=True)
    account = _account_by_mobile(db, mobile, lock=True)
    challenge = None
    if account is not None:
        challenge = db.execute(
            select(OtpChallenge)
            .where(
                OtpChallenge.account_id == account.id,
                OtpChallenge.consumed_at.is_(None),
                OtpChallenge.expires_at > now(),
            )
            .order_by(OtpChallenge.created_at.desc())
            .limit(1)
            .with_for_update()
        ).scalar_one_or_none()
    if account is None or challenge is None or challenge.attempts >= OTP_MAX_ATTEMPTS:
        raise AppError("The code is invalid or has expired. Request a new code.", code="invalid_code")
    challenge.attempts += 1
    if not hmac.compare_digest(challenge.code_hash, _code_hash(account.id, code.strip())):
        db.commit()  # persist the attempt count before failing
        raise AppError("The code is incorrect.", code="invalid_code")
    challenge.consumed_at = now()
    account.verified_at = account.verified_at or now()
    audit.record(
        db,
        action="citizen.mobile_verified",
        actor=_actor(account),
        resource_type="citizen_account",
        resource_id=account.id,
        meta=meta,
    )
    return account


# --- Registration and sign-in ------------------------------------------------------------------


def register(db: Session, data: dict[str, Any], meta: RequestMeta) -> tuple[CitizenAccount, str | None]:
    hit(f"citizen-register-ip:{meta.ip or 'unknown'}", 10, window_seconds=3600, fail_closed=True)
    if not data.get("consent"):
        raise AppError("Please accept the consent notice to create an account.", code="consent_required")
    mobile = normalize_mobile(data["mobile"])
    try:
        security.validate_password_policy(data["password"], username=mobile[-10:], full_name=data["name"])
    except security.WeakPasswordError as exc:
        raise AppError(str(exc), code="weak_password") from exc
    account = _account_by_mobile(db, mobile, lock=True)
    if account is not None and account.verified_at is not None:
        raise ConflictError("This mobile number is already registered. Sign in instead.", code="already_registered")
    if account is None:
        account = CitizenAccount(
            mobile_hash=security.lookup_hash(mobile) or "",
            mobile_encrypted="",
            name_encrypted="",
            password_hash="",
            consent_version=CONSENT_VERSION,
            consent_at=now(),
        )
        db.add(account)
    # An unverified registration may be replaced: only the phone's owner can complete it.
    account.mobile_encrypted = security.encrypt_text(mobile) or ""
    account.name_encrypted = security.encrypt_text(data["name"].strip()) or ""
    account.email_encrypted = security.encrypt_text(data.get("email"))
    account.password_hash = security.hash_password(data["password"])
    account.consent_version, account.consent_at = CONSENT_VERSION, now()
    db.flush()
    audit.record(
        db,
        action="citizen.registered",
        actor=_actor(account),
        resource_type="citizen_account",
        resource_id=account.id,
        details={"consent_version": CONSENT_VERSION},
        meta=meta,
    )
    return account, issue_otp(db, account)


def resend_otp(db: Session, mobile: str) -> str | None:
    account = _account_by_mobile(db, normalize_mobile(mobile))
    if account is None or account.verified_at is not None:
        return None  # same response whether or not the number is registered
    return issue_otp(db, account)


@dataclass
class IssuedCitizenSession:
    token: str
    csrf: str


def login(db: Session, mobile: str, password: str, meta: RequestMeta) -> tuple[CitizenAccount, IssuedCitizenSession]:
    settings = get_settings()
    mobile = normalize_mobile(mobile)
    hit(f"citizen-login-ip:{meta.ip or 'unknown'}", settings.login_rate_limit_per_minute, fail_closed=True)
    hit(f"citizen-login:{security.lookup_hash(mobile)}", settings.login_rate_limit_per_minute, fail_closed=True)
    account = _account_by_mobile(db, mobile, lock=True)
    if account is None:
        security.verify_password(security.DUMMY_PASSWORD_HASH, password)
        raise CitizenAuthError()
    ok = security.verify_password(account.password_hash, password)
    t = now()
    if account.locked_until and account.locked_until > t:
        raise (
            AppError("Too many failed attempts. Try again later.", code="account_locked") if ok else CitizenAuthError()
        )
    if not ok or not account.is_active:
        if not ok:
            account.failed_login_count += 1
            if account.failed_login_count >= settings.lockout_threshold:
                account.locked_until, account.failed_login_count = t + timedelta(minutes=settings.lockout_minutes), 0
            db.commit()
        raise CitizenAuthError()
    if account.verified_at is None:
        raise AppError("Verify your mobile number first.", code="mobile_not_verified")
    account.failed_login_count, account.locked_until, account.last_login_at = 0, None, t
    token, csrf = security.new_token(), security.new_token()
    db.add(
        CitizenSession(
            account_id=account.id,
            token_hash=security.token_hash(token),
            csrf_hash=security.token_hash(csrf),
            expires_at=t + timedelta(minutes=settings.session_absolute_timeout_minutes),
            ip_address=meta.ip,
        )
    )
    audit.record(
        db,
        action="citizen.login",
        actor=_actor(account),
        resource_type="citizen_account",
        resource_id=account.id,
        meta=meta,
    )
    return account, IssuedCitizenSession(token, csrf)


def load_session(db: Session, token: str) -> tuple[CitizenSession, CitizenAccount] | None:
    settings = get_settings()
    row = db.execute(
        select(CitizenSession, CitizenAccount)
        .join(CitizenAccount, CitizenAccount.id == CitizenSession.account_id)
        .where(CitizenSession.token_hash == security.token_hash(token))
    ).first()
    if row is None:
        return None
    sess, account = row
    t = now()
    if (
        sess.revoked_at
        or sess.expires_at <= t
        or sess.last_seen_at + timedelta(minutes=settings.session_idle_timeout_minutes) <= t
        or not account.is_active
    ):
        return None
    if (t - sess.last_seen_at).total_seconds() > 60:
        sess.last_seen_at = t
    return sess, account


def profile(account: CitizenAccount) -> dict[str, Any]:
    return {
        "id": str(account.id),
        "name": security.decrypt_text(account.name_encrypted),
        "mobile": security.mask(security.decrypt_text(account.mobile_encrypted), 4),
        "verified": account.verified_at is not None,
    }


# --- Grievances ------------------------------------------------------------------------------------


def submit_grievance(db: Session, account: CitizenAccount, data: dict[str, Any], meta: RequestMeta) -> Grievance:
    from app.modules.grievances import service as gsvc

    hit(f"citizen-file:{account.id}", 10, window_seconds=86400, fail_closed=True)
    source = db.execute(select(GrievanceSource.id).where(GrievanceSource.code == "CITIZEN_PORTAL")).scalar_one()
    g = gsvc.register(
        db,
        None,
        source_id=source,
        subject=data["subject"],
        description=data["description"],
        received_at=None,
        category_id=data.get("category_id"),
        subcategory_id=None,
        department_id=None,
        priority="normal",
        location=gsvc.LocationInput(**data.get("location", {})),
        location_text=data.get("location_text"),
        complainant=gsvc.ComplainantInput(
            name=security.decrypt_text(account.name_encrypted),
            mobile=security.decrypt_text(account.mobile_encrypted),
            email=security.decrypt_text(account.email_encrypted),
            address=data.get("address"),
            consent_recorded=True,
        ),
        meta=meta,
        actor_override=_actor(account),
    )
    g.citizen_account_id = account.id
    db.flush()
    return g


def _own(db: Session, account: CitizenAccount, grievance_id: uuid.UUID) -> Grievance:
    g = db.execute(
        select(Grievance).where(Grievance.id == grievance_id, Grievance.citizen_account_id == account.id)
    ).scalar_one_or_none()
    if g is None:
        raise NotFoundError("Grievance not found.")
    return g


def list_own(db: Session, account: CitizenAccount) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Grievance)
        .where(Grievance.citizen_account_id == account.id)
        .order_by(Grievance.registered_at.desc())
        .limit(200)
    ).scalars()
    return [
        {
            "id": str(g.id),
            "reference_no": g.reference_no,
            "subject": g.subject,
            "status": g.status,
            "status_label": PUBLIC_STATUS.get(g.status, g.status),
            "registered_at": g.registered_at,
            "updated_at": g.status_changed_at,
        }
        for g in rows
    ]


def detail_own(db: Session, account: CitizenAccount, grievance_id: uuid.UUID) -> dict[str, Any]:
    from app.modules.administration.models import Department

    g = _own(db, account, grievance_id)
    timeline = db.execute(
        select(GrievanceStatusHistory.to_status, GrievanceStatusHistory.occurred_at)
        .where(GrievanceStatusHistory.grievance_id == g.id)
        .order_by(GrievanceStatusHistory.occurred_at)
    ).all()
    dept = db.get(Department, g.department_id) if g.department_id else None
    public_resolution = g.resolution_summary if g.status in ("resolved", "closed") else None
    return {
        "id": str(g.id),
        "reference_no": g.reference_no,
        "subject": g.subject,
        "description": g.description,
        "status": g.status,
        "status_label": PUBLIC_STATUS.get(g.status, g.status),
        "registered_at": g.registered_at,
        "responsible_office": dept.name_en if dept else None,
        "resolution": public_resolution,
        "timeline": [{"status_label": PUBLIC_STATUS.get(s, s), "at": at} for s, at in timeline],
    }
