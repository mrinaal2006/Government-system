"""Citizen self-service portal API (/api/v1/citizen/*).

Separate from officer authentication: its own accounts, session cookie and CSRF cookie.
A citizen session grants access only to the citizen's own grievances. The whole router
answers 404 unless the portal is enabled (CITIZEN_PORTAL_ENABLED).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import SAFE_METHODS, CsrfError, NotAuthenticatedError
from app.core import security
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.request_meta import RequestMeta
from app.db.session import get_db
from app.modules.administration.models import IssueCategory
from app.modules.administration.router import UnitLevel, list_units
from app.modules.audit import service as audit
from app.modules.citizen_portal import service as svc
from app.modules.citizen_portal.models import CitizenAccount, CitizenSession

SESSION_COOKIE = "dgi_csession"
CSRF_COOKIE = "dgi_ccsrf"


def portal_enabled() -> None:
    if not get_settings().citizen_portal_active:
        raise NotFoundError("Not found.")


router = APIRouter(prefix="/citizen", tags=["citizen"], dependencies=[Depends(portal_enabled)])
DbDep = Annotated[Session, Depends(get_db)]


def citizen_session(request: Request, db: DbDep) -> tuple[CitizenSession, CitizenAccount]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise NotAuthenticatedError()
    loaded = svc.load_session(db, token)
    if loaded is None:
        raise NotAuthenticatedError("Your session has expired. Please sign in again.")
    if request.method not in SAFE_METHODS:
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not security.constant_time_equals(security.token_hash(supplied), loaded[0].csrf_hash):
            raise CsrfError()
    return loaded


CitizenCtx = Annotated[tuple[CitizenSession, CitizenAccount], Depends(citizen_session)]


def _set_cookies(response: Response, issued: svc.IssuedCitizenSession) -> None:
    s = get_settings()
    max_age = s.session_absolute_timeout_minutes * 60
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        max_age=max_age,
        httponly=True,
        secure=s.cookies_secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE, issued.csrf, max_age=max_age, httponly=False, secure=s.cookies_secure, samesite="strict", path="/"
    )


def _clear_cookies(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=s.cookies_secure, httponly=True, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=s.cookies_secure, samesite="strict")


def _origin(request: Request) -> None:
    from app.modules.iam.router import _origin_ok

    _origin_ok(request)


# --- Account -----------------------------------------------------------------------------------


class RegisterIn(BaseModel):
    mobile: str = Field(min_length=10, max_length=16)
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr | None = None
    password: str = Field(min_length=1, max_length=256)
    consent: bool


class MobileIn(BaseModel):
    mobile: str = Field(min_length=10, max_length=16)


class VerifyIn(MobileIn):
    code: str = Field(pattern=r"^\d{6}$")


class LoginIn(MobileIn):
    password: str = Field(min_length=1, max_length=256)


def _code_response(code: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "message": "If the number can receive a code, one has been sent. It is valid for 10 minutes."
    }
    if code is not None:
        out["development_otp"] = code  # only returned in development/test with the console provider
    return out


@router.get("/config")
def config() -> dict[str, Any]:
    return {"consent_version": svc.CONSENT_VERSION, "otp_ttl_minutes": int(svc.OTP_TTL.total_seconds() // 60)}


@router.post("/register", status_code=202)
def register(body: RegisterIn, request: Request, db: DbDep) -> dict[str, Any]:
    _origin(request)
    _account, code = svc.register(db, body.model_dump(), RequestMeta.from_request(request))
    return _code_response(code)


@router.post("/otp/resend", status_code=202)
def resend(body: MobileIn, request: Request, db: DbDep) -> dict[str, Any]:
    _origin(request)
    return _code_response(svc.resend_otp(db, body.mobile))


@router.post("/verify")
def verify(body: VerifyIn, request: Request, db: DbDep) -> dict[str, Any]:
    _origin(request)
    svc.verify_mobile(db, body.mobile, body.code, RequestMeta.from_request(request))
    return {"verified": True}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: DbDep) -> dict[str, Any]:
    _origin(request)
    account, issued = svc.login(db, body.mobile, body.password, RequestMeta.from_request(request))
    _set_cookies(response, issued)
    return svc.profile(account)


@router.post("/logout", status_code=204)
def logout(ctx: CitizenCtx, request: Request, response: Response, db: DbDep) -> None:
    sess, account = ctx
    sess.revoked_at = svc.now()
    audit.record(
        db,
        action="citizen.logout",
        actor=svc._actor(account),
        resource_type="citizen_account",
        resource_id=account.id,
        meta=RequestMeta.from_request(request),
    )
    _clear_cookies(response)


@router.get("/me")
def me(ctx: CitizenCtx) -> dict[str, Any]:
    return svc.profile(ctx[1])


# --- Reference data needed to file a grievance -------------------------------------------------


@router.get("/reference/categories")
def categories(ctx: CitizenCtx, db: DbDep) -> list[dict[str, Any]]:
    rows = db.execute(
        select(IssueCategory)
        .where(IssueCategory.is_active.is_(True), IssueCategory.parent_id.is_(None))
        .order_by(IssueCategory.name_en)
    ).scalars()
    return [{"id": str(c.id), "name_en": c.name_en, "name_local": c.name_local} for c in rows]


@router.get("/reference/units/{level}")
def units(
    level: UnitLevel, ctx: CitizenCtx, db: DbDep, parent_id: uuid.UUID | None = None, q: str | None = None
) -> list[dict[str, Any]]:
    keep = (
        "id",
        "name_en",
        "name_local",
        "district_id",
        "subdivision_id",
        "block_id",
        "gram_panchayat_id",
        "municipality_id",
        "ward_number",
    )
    return [
        {k: v for k, v in r.items() if k in keep}
        for r in list_units(db, level, parent_id=parent_id, q=q, limit=2000)
        if r.get("is_active", True)
    ]


# --- Grievances -------------------------------------------------------------------------------


class LocationIn(BaseModel):
    district_id: uuid.UUID | None = None
    subdivision_id: uuid.UUID | None = None
    block_id: uuid.UUID | None = None
    gram_panchayat_id: uuid.UUID | None = None
    village_id: uuid.UUID | None = None
    municipality_id: uuid.UUID | None = None
    ward_id: uuid.UUID | None = None


class GrievanceIn(BaseModel):
    subject: str = Field(min_length=5, max_length=300)
    description: str = Field(min_length=20, max_length=10000)
    category_id: uuid.UUID | None = None
    location: LocationIn = Field(default_factory=LocationIn)
    location_text: str | None = Field(default=None, max_length=500)
    address: str | None = Field(default=None, max_length=500)


@router.post("/grievances", status_code=201)
def file_grievance(body: GrievanceIn, ctx: CitizenCtx, request: Request, db: DbDep) -> dict[str, Any]:
    g = svc.submit_grievance(db, ctx[1], body.model_dump(), RequestMeta.from_request(request))
    return {"id": str(g.id), "reference_no": g.reference_no, "status_label": svc.PUBLIC_STATUS.get(g.status, g.status)}


@router.get("/grievances")
def my_grievances(ctx: CitizenCtx, db: DbDep) -> list[dict[str, Any]]:
    return svc.list_own(db, ctx[1])


@router.get("/grievances/{grievance_id}")
def my_grievance(grievance_id: uuid.UUID, ctx: CitizenCtx, db: DbDep) -> dict[str, Any]:
    return svc.detail_own(db, ctx[1], grievance_id)
