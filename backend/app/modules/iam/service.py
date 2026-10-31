"""Authentication, sessions, MFA and permission/scope resolution."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, exists, func, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError
from app.core.ratelimit import hit
from app.core.request_meta import RequestMeta
from app.modules.audit import service as audit
from app.modules.audit.service import Actor
from app.modules.iam.models import (
    LoginEvent,
    MfaCredential,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
    UserScopeAssignment,
    UserSession,
)

GENERIC_LOGIN_FAILURE = "Invalid username or password."


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_failed"
    message = GENERIC_LOGIN_FAILURE


class AccountLockedError(AppError):
    status_code = 423
    code = "account_locked"
    message = "This account is temporarily locked. Try again later or contact the administrator."


class AccessPendingError(AppError):
    status_code = 403
    code = "access_request_pending"
    message = "Your access request is awaiting approval by the administrator."


class InvalidCodeError(AppError):
    status_code = 400
    code = "invalid_code"
    message = "The verification code is not valid."


@dataclass
class Scope:
    scope_type: str
    district_id: uuid.UUID | None = None
    subdivision_id: uuid.UUID | None = None
    block_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None


@dataclass
class CurrentUser:
    id: uuid.UUID
    username: str
    full_name: str
    roles: list[str]
    permissions: frozenset[str]
    scopes: list[Scope]
    session_id: uuid.UUID
    state: str
    department_id: uuid.UUID | None = None
    mfa_enrolled: bool = False
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def actor(self) -> Actor:
        return Actor(self.id, self.username)

    def has(self, permission: str) -> bool:
        return permission in self.permissions


@dataclass
class IssuedSession:
    token: str
    csrf_token: str
    session: UserSession


def now() -> datetime:
    return datetime.now(UTC)


# --- Roles, permissions, scopes ----------------------------------------------------


def role_codes(db: Session, user_id: uuid.UUID) -> list[str]:
    return list(
        db.execute(
            select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
        ).scalars()
    )


def permission_codes(db: Session, user_id: uuid.UUID) -> frozenset[str]:
    rows = db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    ).scalars()
    return frozenset(rows)


def scopes_for(db: Session, user_id: uuid.UUID) -> list[Scope]:
    rows = db.execute(select(UserScopeAssignment).where(UserScopeAssignment.user_id == user_id)).scalars()
    return [Scope(r.scope_type, r.district_id, r.subdivision_id, r.block_id, r.department_id) for r in rows]


def has_confirmed_mfa(db: Session, user_id: uuid.UUID) -> bool:
    return bool(
        db.execute(
            select(
                exists().where(
                    MfaCredential.user_id == user_id,
                    MfaCredential.confirmed_at.is_not(None),
                    MfaCredential.revoked_at.is_(None),
                )
            )
        ).scalar()
    )


def mfa_required_for(roles: list[str]) -> bool:
    required = set(get_settings().mfa_required_roles)
    return any(r in required for r in roles)


# --- Sessions --------------------------------------------------------------------------


def issue_session(db: Session, user: User, meta: RequestMeta, *, mfa_satisfied: bool) -> IssuedSession:
    settings = get_settings()
    token, csrf = security.new_token(), security.new_token()
    sess = UserSession(
        user_id=user.id,
        token_hash=security.token_hash(token),
        csrf_hash=security.token_hash(csrf),
        expires_at=now() + timedelta(minutes=settings.session_absolute_timeout_minutes),
        mfa_verified=mfa_satisfied,
        ip_address=meta.ip,
        user_agent=meta.user_agent,
    )
    db.add(sess)
    db.flush()
    return IssuedSession(token, csrf, sess)


def rotate_session(db: Session, sess: UserSession) -> IssuedSession:
    """New token and CSRF secret after a privilege change (prevents session fixation)."""
    token, csrf = security.new_token(), security.new_token()
    sess.token_hash = security.token_hash(token)
    sess.csrf_hash = security.token_hash(csrf)
    db.flush()
    return IssuedSession(token, csrf, sess)


def revoke_sessions(db: Session, user_id: uuid.UUID, reason: str, *, except_id: uuid.UUID | None = None) -> int:
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now(), revoked_reason=reason)
    )
    if except_id is not None:
        stmt = stmt.where(UserSession.id != except_id)
    return db.execute(stmt).rowcount or 0  # type: ignore[attr-defined]


def load_session(db: Session, token: str) -> tuple[UserSession, User] | None:
    settings = get_settings()
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == security.token_hash(token))
    ).first()
    if row is None:
        return None
    sess, user = row
    t = now()
    idle_limit = sess.last_seen_at + timedelta(minutes=settings.session_idle_timeout_minutes)
    if sess.revoked_at is not None or sess.expires_at <= t or idle_limit <= t:
        if sess.revoked_at is None:
            sess.revoked_at, sess.revoked_reason = t, "expired"
        return None
    if not user.is_active or (user.locked_until and user.locked_until > t):
        return None
    if (t - sess.last_seen_at).total_seconds() > 60:
        sess.last_seen_at = t
    return sess, user


def session_state(db: Session, user: User, sess: UserSession, roles: list[str]) -> str:
    if not sess.mfa_verified:
        return "mfa_required" if has_confirmed_mfa(db, user.id) else "mfa_enrollment_required"
    if user.must_change_password:
        return "password_change_required"
    return "authenticated"


def build_current_user(db: Session, user: User, sess: UserSession) -> CurrentUser:
    roles = role_codes(db, user.id)
    return CurrentUser(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        roles=roles,
        permissions=permission_codes(db, user.id),
        scopes=scopes_for(db, user.id),
        session_id=sess.id,
        state=session_state(db, user, sess, roles),
        department_id=user.department_id,
        mfa_enrolled=has_confirmed_mfa(db, user.id),
    )


def user_context(db: Session, user_id: uuid.UUID) -> CurrentUser:
    """Permissions and scopes of a user as of now, for background jobs acting on their behalf."""
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("The requesting user is no longer active.")
    return CurrentUser(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        roles=role_codes(db, user.id),
        permissions=permission_codes(db, user.id),
        scopes=scopes_for(db, user.id),
        session_id=uuid.UUID(int=0),
        state="authenticated",
        department_id=user.department_id,
    )


# --- Login -------------------------------------------------------------------------------


def _login_event(
    db: Session,
    user: User | None,
    username: str,
    meta: RequestMeta,
    ok: bool,
    reason: str | None,
    suspicious: bool = False,
) -> None:
    db.add(
        LoginEvent(
            user_id=user.id if user else None,
            username_attempted=username[:100],
            success=ok,
            reason=reason,
            ip_address=meta.ip,
            user_agent=meta.user_agent,
            suspicious=suspicious,
        )
    )


def _is_suspicious(db: Session, user: User, meta: RequestMeta) -> list[str]:
    reasons: list[str] = []
    t = now()
    prior_success = db.execute(
        select(func.count())
        .select_from(LoginEvent)
        .where(
            LoginEvent.user_id == user.id,
            LoginEvent.success.is_(True),
            LoginEvent.occurred_at > t - timedelta(days=90),
        )
    ).scalar_one()
    if prior_success and meta.ip:
        seen_ip = db.execute(
            select(func.count())
            .select_from(LoginEvent)
            .where(
                LoginEvent.user_id == user.id,
                LoginEvent.success.is_(True),
                LoginEvent.ip_address == meta.ip,
                LoginEvent.occurred_at > t - timedelta(days=90),
            )
        ).scalar_one()
        if not seen_ip:
            reasons.append("new_network_address")
    recent_failures = db.execute(
        select(func.count())
        .select_from(LoginEvent)
        .where(
            LoginEvent.user_id == user.id,
            LoginEvent.success.is_(False),
            LoginEvent.occurred_at > t - timedelta(hours=1),
        )
    ).scalar_one()
    if recent_failures >= 3:
        reasons.append("recent_failed_attempts")
    return reasons


def login(db: Session, username: str, password: str, meta: RequestMeta) -> tuple[IssuedSession, User, str]:
    """Authenticate; failures are recorded in an independent transaction before raising."""
    from app.db.session import get_session_factory

    settings = get_settings()
    uname = username.strip().lower()
    hit(f"login-ip:{meta.ip or 'unknown'}", settings.login_rate_limit_per_minute, fail_closed=True)
    hit(f"login-user:{uname}", settings.login_rate_limit_per_minute, fail_closed=True)

    user = db.execute(select(User).where(User.username == uname)).scalar_one_or_none()
    if user is None:
        security.verify_password(security.DUMMY_PASSWORD_HASH, password)
        _fail(None, uname, meta, "unknown_user")
        raise AuthenticationError()

    password_ok = security.verify_password(user.password_hash, password)
    t = now()
    if user.locked_until and user.locked_until > t:
        _fail(user.id, uname, meta, "locked")
        if password_ok:
            raise AccountLockedError()
        raise AuthenticationError()
    if user.approval_status != "approved":
        _fail(user.id, uname, meta, f"access_request_{user.approval_status}")
        if password_ok and user.approval_status == "pending":
            raise AccessPendingError()
        if password_ok:
            raise AccessPendingError(
                "Your access request was not approved. Contact the district administration.",
                code="access_request_rejected",
            )
        raise AuthenticationError()
    if not user.is_active:
        _fail(user.id, uname, meta, "inactive")
        raise AuthenticationError()
    if not password_ok:
        # Count failures and lock in a separate transaction so it persists.
        with get_session_factory()() as s2, s2.begin():
            u2 = s2.get(User, user.id, with_for_update=True)
            assert u2 is not None
            u2.failed_login_count += 1
            locked = u2.failed_login_count >= settings.lockout_threshold
            if locked:
                u2.locked_until = t + timedelta(minutes=settings.lockout_minutes)
                u2.failed_login_count = 0
            _login_event(s2, u2, uname, meta, False, "bad_password")
            audit.record(
                s2,
                action="auth.login",
                outcome="failure",
                actor=Actor(u2.id, u2.username),
                resource_type="user",
                resource_id=u2.id,
                details={"reason": "bad_password"},
                meta=meta,
            )
            if locked:
                audit.record(
                    s2,
                    action="auth.account_locked",
                    actor=Actor(u2.id, u2.username),
                    resource_type="user",
                    resource_id=u2.id,
                    details={"minutes": settings.lockout_minutes},
                    meta=meta,
                )
        raise AuthenticationError()

    reasons = _is_suspicious(db, user, meta)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = t
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    roles = role_codes(db, user.id)
    enrolled = has_confirmed_mfa(db, user.id)
    mfa_satisfied = not enrolled and not mfa_required_for(roles)
    issued = issue_session(db, user, meta, mfa_satisfied=mfa_satisfied)
    _login_event(db, user, uname, meta, True, None, suspicious=bool(reasons))
    audit.record(
        db,
        action="auth.login",
        actor=Actor(user.id, user.username),
        resource_type="user",
        resource_id=user.id,
        details={"mfa_pending": not mfa_satisfied},
        meta=meta,
    )
    if reasons:
        audit.record(
            db,
            action="auth.suspicious_login",
            outcome="warning",
            actor=Actor(user.id, user.username),
            resource_type="user",
            resource_id=user.id,
            details={"reasons": reasons},
            meta=meta,
        )
        from app.modules.notifications.service import notify

        notify(
            db,
            user.id,
            "security",
            "Unusual sign-in to your account",
            "A sign-in was detected from a new network address or after failed attempts. "
            "If this was not you, change your password and inform the administrator.",
            None,
        )
    return issued, user, session_state(db, user, issued.session, roles)


def _fail(user_id: uuid.UUID | None, uname: str, meta: RequestMeta, reason: str) -> None:
    from app.db.session import get_session_factory

    with get_session_factory()() as s2, s2.begin():
        u = s2.get(User, user_id) if user_id else None
        _login_event(s2, u, uname, meta, False, reason)
        audit.record(
            s2,
            action="auth.login",
            outcome="failure",
            actor=Actor(user_id, uname if user_id else None),
            resource_type="user",
            resource_id=user_id,
            details={"reason": reason},
            meta=meta,
        )


# --- MFA -----------------------------------------------------------------------------------


def start_mfa_enrollment(db: Session, user: User) -> tuple[str, str]:
    if has_confirmed_mfa(db, user.id):
        raise ConflictError("Multi-factor authentication is already set up for this account.")
    db.execute(
        update(MfaCredential)
        .where(
            MfaCredential.user_id == user.id,
            MfaCredential.confirmed_at.is_(None),
            MfaCredential.revoked_at.is_(None),
        )
        .values(revoked_at=now())
    )
    secret = security.new_totp_secret()
    db.add(MfaCredential(user_id=user.id, method="totp", secret_encrypted=security.encrypt_text(secret) or ""))
    db.flush()
    return secret, security.totp_provisioning_uri(secret, user.username)


def _check_code(db: Session, user: User, code: str, *, confirmed: bool) -> MfaCredential:
    hit(f"mfa:{user.id}", 5, fail_closed=True)
    cond = MfaCredential.confirmed_at.is_not(None) if confirmed else MfaCredential.confirmed_at.is_(None)
    cred = db.execute(
        select(MfaCredential)
        .where(MfaCredential.user_id == user.id, MfaCredential.revoked_at.is_(None), cond)
        .order_by(MfaCredential.created_at.desc())
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()
    if cred is None:
        raise InvalidCodeError("No pending verification for this account.")
    secret = security.decrypt_text(cred.secret_encrypted) or ""
    step = security.totp_matching_step(secret, code.strip())
    if step is None or (cred.last_used_step is not None and step <= cred.last_used_step):
        raise InvalidCodeError()
    cred.last_used_step = step
    return cred


def confirm_mfa(db: Session, user: User, sess: UserSession, code: str, meta: RequestMeta) -> IssuedSession:
    cred = _check_code(db, user, code, confirmed=False)
    cred.confirmed_at = now()
    sess.mfa_verified = True
    audit.record(
        db,
        action="auth.mfa_enrolled",
        actor=Actor(user.id, user.username),
        resource_type="user",
        resource_id=user.id,
        meta=meta,
    )
    return rotate_session(db, sess)


def verify_mfa(db: Session, user: User, sess: UserSession, code: str, meta: RequestMeta) -> IssuedSession:
    try:
        _check_code(db, user, code, confirmed=True)
    except InvalidCodeError:
        audit.record_independent(
            action="auth.mfa_verify",
            outcome="failure",
            actor=Actor(user.id, user.username),
            resource_type="user",
            resource_id=user.id,
            meta=meta,
        )
        raise
    sess.mfa_verified = True
    audit.record(
        db,
        action="auth.mfa_verify",
        actor=Actor(user.id, user.username),
        resource_type="user",
        resource_id=user.id,
        meta=meta,
    )
    return rotate_session(db, sess)


def change_password(
    db: Session, user: User, sess: UserSession, current: str, new: str, meta: RequestMeta
) -> IssuedSession:
    if not security.verify_password(user.password_hash, current):
        audit.record_independent(
            action="auth.password_change",
            outcome="failure",
            actor=Actor(user.id, user.username),
            resource_type="user",
            resource_id=user.id,
            meta=meta,
        )
        raise AuthenticationError("The current password is incorrect.")
    if security.verify_password(user.password_hash, new):
        raise AppError("The new password must be different from the current password.", code="password_reused")
    try:
        security.validate_password_policy(new, username=user.username, full_name=user.full_name)
    except security.WeakPasswordError as exc:
        raise AppError(str(exc), code="weak_password") from exc
    user.password_hash = security.hash_password(new)
    user.password_changed_at = now()
    user.must_change_password = False
    revoked = revoke_sessions(db, user.id, "password_changed", except_id=sess.id)
    audit.record(
        db,
        action="auth.password_change",
        actor=Actor(user.id, user.username),
        resource_type="user",
        resource_id=user.id,
        details={"other_sessions_revoked": revoked},
        meta=meta,
    )
    return rotate_session(db, sess)


__all__ = ["and_"]
