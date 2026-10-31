"""Authentication endpoints (/auth) and user administration (/iam)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import delete, func, or_, select

from app.api.auth import DbDep, SessionCtx, any_state_user, require
from app.api.common import Page, clear_session_cookies, paging, set_session_cookies
from app.core import security
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.request_meta import RequestMeta
from app.modules.audit import service as audit
from app.modules.iam import service as iam
from app.modules.iam.catalogue import ROLES
from app.modules.iam.models import MfaCredential, Role, User, UserRole, UserScopeAssignment

router = APIRouter(tags=["auth"])
admin = APIRouter(prefix="/iam", tags=["iam"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class SessionInfo(BaseModel):
    state: str
    user: dict[str, object]


def _session_info(cu: iam.CurrentUser) -> SessionInfo:
    return SessionInfo(
        state=cu.state,
        user={
            "id": str(cu.id),
            "username": cu.username,
            "full_name": cu.full_name,
            "roles": cu.roles,
            "permissions": sorted(cu.permissions) if cu.state == "authenticated" else [],
            "mfa_enrolled": cu.mfa_enrolled,
        },
    )


def _origin_ok(request: Request) -> None:
    """Refuse cross-origin sign-in. The Origin must match the Host header (nginx) or be one
    of ALLOWED_HOSTS (edges such as Vercel may forward an internal Host to the function)."""
    from urllib.parse import urlsplit

    from app.api.deps import get_app_settings

    origin = request.headers.get("origin")
    if not origin:
        return
    parts = urlsplit(origin)
    if parts.netloc == request.headers.get("host", ""):
        return
    allowed = {h.lower() for h in get_app_settings(request).allowed_hosts if h != "*"}
    if (parts.hostname or "").lower() not in allowed:
        raise PermissionDeniedError("Cross-origin sign-in is not permitted.")


@router.post("/auth/login", response_model=SessionInfo)
def login(body: LoginRequest, request: Request, response: Response, db: DbDep) -> SessionInfo:
    _origin_ok(request)
    issued, user, _state = iam.login(db, body.username, body.password, RequestMeta.from_request(request))
    set_session_cookies(response, issued)
    return _session_info(iam.build_current_user(db, user, issued.session))


@router.post("/auth/logout", status_code=204)
def logout(ctx: SessionCtx, request: Request, response: Response, db: DbDep) -> None:
    sess, user = ctx
    sess.revoked_at, sess.revoked_reason = iam.now(), "logout"
    audit.record(
        db,
        action="auth.logout",
        actor=audit.Actor(user.id, user.username),
        resource_type="user",
        resource_id=user.id,
        meta=RequestMeta.from_request(request),
    )
    clear_session_cookies(response)


@router.get("/auth/me", response_model=SessionInfo)
def me(cu: Annotated[iam.CurrentUser, Depends(any_state_user)]) -> SessionInfo:
    return _session_info(cu)


class CodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


@router.post("/auth/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(ctx: SessionCtx, db: DbDep) -> MfaSetupResponse:
    sess, user = ctx
    if sess.mfa_verified is False and iam.has_confirmed_mfa(db, user.id):
        raise PermissionDeniedError("Verify your existing authenticator first.")
    secret, uri = iam.start_mfa_enrollment(db, user)
    return MfaSetupResponse(secret=secret, otpauth_uri=uri)


@router.post("/auth/mfa/confirm", response_model=SessionInfo)
def mfa_confirm(body: CodeRequest, ctx: SessionCtx, request: Request, response: Response, db: DbDep) -> SessionInfo:
    sess, user = ctx
    issued = iam.confirm_mfa(db, user, sess, body.code, RequestMeta.from_request(request))
    set_session_cookies(response, issued)
    return _session_info(iam.build_current_user(db, user, sess))


@router.post("/auth/mfa/verify", response_model=SessionInfo)
def mfa_verify(body: CodeRequest, ctx: SessionCtx, request: Request, response: Response, db: DbDep) -> SessionInfo:
    sess, user = ctx
    issued = iam.verify_mfa(db, user, sess, body.code, RequestMeta.from_request(request))
    set_session_cookies(response, issued)
    return _session_info(iam.build_current_user(db, user, sess))


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


@router.post("/auth/password", response_model=SessionInfo)
def change_password(
    body: PasswordChange, ctx: SessionCtx, request: Request, response: Response, db: DbDep
) -> SessionInfo:
    sess, user = ctx
    if not sess.mfa_verified:
        raise PermissionDeniedError("Complete multi-factor verification first.")
    issued = iam.change_password(
        db, user, sess, body.current_password, body.new_password, RequestMeta.from_request(request)
    )
    set_session_cookies(response, issued)
    return _session_info(iam.build_current_user(db, user, sess))


# --- User administration -------------------------------------------------------------


class ScopeIn(BaseModel):
    scope_type: Literal["district", "subdivision", "block", "department", "assigned", "own"]
    district_id: uuid.UUID | None = None
    subdivision_id: uuid.UUID | None = None
    block_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    designation: str | None
    email: str | None
    department_id: uuid.UUID | None
    is_active: bool
    locked: bool
    must_change_password: bool
    mfa_enrolled: bool
    last_login_at: datetime | None
    roles: list[str]
    scopes: list[ScopeIn]


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9._-]{3,64}$")
    full_name: str = Field(min_length=2, max_length=200)
    designation: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    department_id: uuid.UUID | None = None
    roles: list[str] = Field(min_length=1)
    scopes: list[ScopeIn] = Field(default_factory=list)
    temporary_password: str = Field(min_length=1, max_length=256)

    @field_validator("roles")
    @classmethod
    def _known_roles(cls, v: list[str]) -> list[str]:
        unknown = [r for r in v if r not in ROLES]
        if unknown:
            raise ValueError(f"unknown roles: {unknown}")
        return sorted(set(v))


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    designation: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    department_id: uuid.UUID | None = None
    is_active: bool | None = None


class RolesIn(BaseModel):
    roles: list[str]

    @field_validator("roles")
    @classmethod
    def _known(cls, v: list[str]) -> list[str]:
        return UserCreate._known_roles(v)


class ScopesIn(BaseModel):
    scopes: list[ScopeIn]


class PasswordReset(BaseModel):
    temporary_password: str = Field(min_length=1, max_length=256)


def _user_out(db: DbDep, u: User) -> UserOut:
    return UserOut(
        id=u.id,
        username=u.username,
        full_name=u.full_name,
        designation=u.designation,
        email=u.email,
        department_id=u.department_id,
        is_active=u.is_active,
        locked=bool(u.locked_until and u.locked_until > iam.now()),
        must_change_password=u.must_change_password,
        mfa_enrolled=iam.has_confirmed_mfa(db, u.id),
        last_login_at=u.last_login_at,
        roles=iam.role_codes(db, u.id),
        scopes=[ScopeIn(**s.__dict__) for s in iam.scopes_for(db, u.id)],
    )


def _get_user(db: DbDep, user_id: uuid.UUID) -> User:
    u = db.get(User, user_id)
    if u is None:
        raise NotFoundError("User not found.")
    return u


def _set_roles(db: DbDep, u: User, roles: list[str], actor: iam.CurrentUser) -> None:
    db.execute(delete(UserRole).where(UserRole.user_id == u.id))
    for rid in db.execute(select(Role.id).where(Role.code.in_(roles))).scalars():
        db.add(UserRole(user_id=u.id, role_id=rid, granted_by=actor.id))


def _set_scopes(db: DbDep, u: User, scopes: list[ScopeIn], actor: iam.CurrentUser) -> None:
    db.execute(delete(UserScopeAssignment).where(UserScopeAssignment.user_id == u.id))
    for s in scopes:
        db.add(UserScopeAssignment(user_id=u.id, granted_by=actor.id, **s.model_dump()))


def _validate_password(pw: str, username: str, full_name: str) -> None:
    try:
        security.validate_password_policy(pw, username=username, full_name=full_name)
    except security.WeakPasswordError as exc:
        raise AppError(str(exc), code="weak_password") from exc


UsersRead = Annotated[iam.CurrentUser, Depends(require("iam.users.read"))]
UsersManage = Annotated[iam.CurrentUser, Depends(require("iam.users.manage"))]


@admin.get("/users", response_model=Page[UserOut])
def list_users(
    cu: UsersRead, db: DbDep, pg: Annotated[tuple[int, int], Depends(paging)], q: str | None = None
) -> Page[UserOut]:
    stmt = select(User)
    if q:
        like = f"%{q.strip()[:100]}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.full_name.ilike(like)))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(User.username).limit(pg[0]).offset(pg[1])).scalars()
    return Page(items=[_user_out(db, u) for u in rows], total=total, limit=pg[0], offset=pg[1])


@admin.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, cu: UsersRead, db: DbDep) -> UserOut:
    return _user_out(db, _get_user(db, user_id))


@admin.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, cu: UsersManage, request: Request, db: DbDep) -> UserOut:
    if db.execute(select(User.id).where(User.username == body.username)).first():
        raise ConflictError("That username is already in use.")
    _validate_password(body.temporary_password, body.username, body.full_name)
    u = User(
        username=body.username,
        full_name=body.full_name,
        designation=body.designation,
        email=str(body.email) if body.email else None,
        department_id=body.department_id,
        password_hash=security.hash_password(body.temporary_password),
        must_change_password=True,
        created_by=cu.id,
    )
    db.add(u)
    db.flush()
    _set_roles(db, u, body.roles, cu)
    _set_scopes(db, u, body.scopes, cu)
    db.flush()
    audit.record(
        db,
        action="iam.user_created",
        actor=cu.actor,
        resource_type="user",
        resource_id=u.id,
        details={"username": u.username, "roles": body.roles, "scopes": len(body.scopes)},
        meta=RequestMeta.from_request(request),
    )
    return _user_out(db, u)


@admin.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate, cu: UsersManage, request: Request, db: DbDep) -> UserOut:
    u = _get_user(db, user_id)
    changes = body.model_dump(exclude_unset=True)
    if "is_active" in changes and u.id == cu.id and not changes["is_active"]:
        raise ConflictError("You cannot deactivate your own account.")
    for k, v in changes.items():
        setattr(u, k, str(v) if k == "email" and v else v)
    if changes.get("is_active") is False:
        iam.revoke_sessions(db, u.id, "deactivated")
    audit.record(
        db,
        action="iam.user_updated",
        actor=cu.actor,
        resource_type="user",
        resource_id=u.id,
        details={"fields": sorted(changes)},
        meta=RequestMeta.from_request(request),
    )
    db.flush()
    return _user_out(db, u)


@admin.put("/users/{user_id}/roles", response_model=UserOut)
def set_roles(user_id: uuid.UUID, body: RolesIn, cu: UsersManage, request: Request, db: DbDep) -> UserOut:
    u = _get_user(db, user_id)
    if u.id == cu.id:
        raise ConflictError("You cannot change your own roles.")
    before = iam.role_codes(db, u.id)
    _set_roles(db, u, body.roles, cu)
    iam.revoke_sessions(db, u.id, "roles_changed")
    audit.record(
        db,
        action="iam.roles_changed",
        actor=cu.actor,
        resource_type="user",
        resource_id=u.id,
        details={"before": before, "after": body.roles},
        meta=RequestMeta.from_request(request),
    )
    db.flush()
    return _user_out(db, u)


@admin.put("/users/{user_id}/scopes", response_model=UserOut)
def set_scopes(user_id: uuid.UUID, body: ScopesIn, cu: UsersManage, request: Request, db: DbDep) -> UserOut:
    u = _get_user(db, user_id)
    _set_scopes(db, u, body.scopes, cu)
    audit.record(
        db,
        action="iam.scopes_changed",
        actor=cu.actor,
        resource_type="user",
        resource_id=u.id,
        details={"scopes": [s.model_dump(mode="json") for s in body.scopes]},
        meta=RequestMeta.from_request(request),
    )
    db.flush()
    return _user_out(db, u)


@admin.post("/users/{user_id}/reset-password", response_model=UserOut)
def reset_password(user_id: uuid.UUID, body: PasswordReset, cu: UsersManage, request: Request, db: DbDep) -> UserOut:
    u = _get_user(db, user_id)
    _validate_password(body.temporary_password, u.username, u.full_name)
    u.password_hash = security.hash_password(body.temporary_password)
    u.must_change_password = True
    iam.revoke_sessions(db, u.id, "password_reset")
    audit.record(
        db,
        action="iam.password_reset",
        actor=cu.actor,
        resource_type="user",
        resource_id=u.id,
        meta=RequestMeta.from_request(request),
    )
    return _user_out(db, u)


@admin.post("/users/{user_id}/unlock", response_model=UserOut)
def unlock(user_id: uuid.UUID, cu: UsersManage, request: Request, db: DbDep) -> UserOut:
    u = _get_user(db, user_id)
    u.locked_until, u.failed_login_count = None, 0
    audit.record(
        db,
        action="iam.user_unlocked",
        actor=cu.actor,
        resource_type="user",
        resource_id=u.id,
        meta=RequestMeta.from_request(request),
    )
    return _user_out(db, u)


@admin.post("/users/{user_id}/mfa/reset", response_model=UserOut)
def reset_mfa(user_id: uuid.UUID, cu: UsersManage, request: Request, db: DbDep) -> UserOut:
    u = _get_user(db, user_id)
    db.query(MfaCredential).filter(MfaCredential.user_id == u.id, MfaCredential.revoked_at.is_(None)).update(
        {"revoked_at": iam.now()}
    )
    iam.revoke_sessions(db, u.id, "mfa_reset")
    audit.record(
        db,
        action="iam.mfa_reset",
        actor=cu.actor,
        resource_type="user",
        resource_id=u.id,
        meta=RequestMeta.from_request(request),
    )
    return _user_out(db, u)


class RoleOut(BaseModel):
    code: str
    name: str
    permissions: list[str]


@admin.get("/roles", response_model=list[RoleOut])
def list_roles(cu: UsersRead) -> list[RoleOut]:
    return [
        RoleOut(code=c, name=str(d["name"]), permissions=[str(p) for p in d["permissions"]])  # type: ignore[attr-defined]
        for c, d in ROLES.items()
    ]
