"""Authorization dependencies used by every protected endpoint.

* ``current_user``: valid, unexpired session cookie, fully authenticated (MFA and
  password-change requirements satisfied), and CSRF token checked for unsafe methods.
* ``require(*permissions)``: additionally checks permissions; denials are audited.
Resource-level scope is applied in each service query (see app/modules/iam/scope.py).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.errors import AppError, PermissionDeniedError
from app.core.request_meta import RequestMeta
from app.db.session import get_db
from app.modules.audit import service as audit
from app.modules.iam import service as iam
from app.modules.iam.models import User, UserSession

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class NotAuthenticatedError(AppError):
    status_code = 401
    code = "not_authenticated"
    message = "Please sign in to continue."


class CsrfError(AppError):
    status_code = 403
    code = "csrf_failed"
    message = "The request could not be verified. Reload the page and try again."


class StepRequiredError(AppError):
    status_code = 403
    code = "additional_step_required"


def _check_csrf(request: Request, sess: UserSession) -> None:
    if request.method in SAFE_METHODS:
        return
    supplied = request.headers.get("x-csrf-token", "")
    if not supplied or not security.constant_time_equals(security.token_hash(supplied), sess.csrf_hash):
        raise CsrfError()


def session_context(request: Request, db: Annotated[Session, Depends(get_db)]) -> tuple[UserSession, User]:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise NotAuthenticatedError()
    loaded = iam.load_session(db, token)
    if loaded is None:
        db.commit()  # persist expiry marking
        raise NotAuthenticatedError("Your session has expired. Please sign in again.")
    _check_csrf(request, loaded[0])
    return loaded


SessionCtx = Annotated[tuple[UserSession, User], Depends(session_context)]


def any_state_user(ctx: SessionCtx, db: Annotated[Session, Depends(get_db)]) -> iam.CurrentUser:
    sess, user = ctx
    return iam.build_current_user(db, user, sess)


def current_user(cu: Annotated[iam.CurrentUser, Depends(any_state_user)]) -> iam.CurrentUser:
    if cu.state != "authenticated":
        raise StepRequiredError(
            {
                "mfa_required": "Multi-factor verification is required.",
                "mfa_enrollment_required": "Set up multi-factor authentication to continue.",
                "password_change_required": "Change your password to continue.",
            }.get(cu.state, "Additional verification is required."),
            details=[{"state": cu.state}],
        )
    return cu


CurrentUserDep = Annotated[iam.CurrentUser, Depends(current_user)]


def require(*permissions: str) -> Callable[..., iam.CurrentUser]:
    def dependency(request: Request, cu: CurrentUserDep) -> iam.CurrentUser:
        missing = [p for p in permissions if p not in cu.permissions]
        if missing:
            audit.record_independent(
                action="access.denied",
                outcome="denied",
                actor=cu.actor,
                resource_type="endpoint",
                resource_id=f"{request.method} {request.url.path}",
                details={"missing": missing},
                meta=RequestMeta.from_request(request),
            )
            raise PermissionDeniedError()
        return cu

    return dependency


def require_any(*permissions: str) -> Callable[..., iam.CurrentUser]:
    def dependency(request: Request, cu: CurrentUserDep) -> iam.CurrentUser:
        if not any(p in cu.permissions for p in permissions):
            audit.record_independent(
                action="access.denied",
                outcome="denied",
                actor=cu.actor,
                resource_type="endpoint",
                resource_id=f"{request.method} {request.url.path}",
                details={"any_of": list(permissions)},
                meta=RequestMeta.from_request(request),
            )
            raise PermissionDeniedError()
        return cu

    return dependency


DbDep = Annotated[Session, Depends(get_db)]
