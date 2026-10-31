"""Sign-up: officer self-service accounts and the citizen portal."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core import security
from app.modules.audit.models import AuditLog
from app.modules.citizen_portal.models import CitizenAccount, OtpChallenge
from app.modules.grievances.models import Grievance
from app.modules.iam.models import Role, User, UserRole, UserScopeAssignment
from app.modules.notifications.models import Notification
from tests.integration.factories import csrf, login, make_geography, make_user, unique

PASSWORD = "Strong-Passw0rd-Signup!"  # must not contain the user's name

# --- Officer sign-up -----------------------------------------------------------------------------


def _signup(client: TestClient, **over: object) -> tuple[str, Any]:
    username = unique("test.su.")
    body = {
        "username": username,
        "full_name": "TEST Officer",
        "email": f"{username}@example.gov.in",
        "password": PASSWORD,
        **over,
    }
    return str(body["username"]), client.post("/api/v1/auth/signup", json=body)


def _roles(db: Session, username: str) -> set[str]:
    db.expire_all()
    return set(
        db.execute(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .join(User, User.id == UserRole.user_id)
            .where(User.username == username)
        ).scalars()
    )


def test_signup_options_are_public(client: TestClient) -> None:
    r = client.get("/api/v1/auth/signup/options")
    assert r.status_code == 200
    assert r.json() == {"officer_signup_enabled": True, "citizen_portal_enabled": True}


def test_first_signup_becomes_super_admin(client: TestClient, db_session: Session) -> None:
    db_session.execute(
        update(User)
        .where(
            User.id.in_(
                select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.code == "super_admin")
            )
        )
        .values(is_active=False)
    )
    db_session.commit()
    username, r = _signup(client)
    assert r.status_code == 201, r.text
    assert r.json()["state"] == "mfa_enrollment_required"  # Super Admin must enrol MFA before anything else
    assert _roles(db_session, username) == {"super_admin"}
    # The next person is an ordinary account.
    second, r2 = _signup(TestClient(client.app))
    assert r2.status_code == 201
    assert _roles(db_session, second) == {"data_entry_operator"}


def test_later_signup_is_signed_in_with_least_privilege(client: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, ["super_admin"])
    db_session.commit()
    username, r = _signup(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["state"] == "authenticated" and body["user"]["roles"] == ["data_entry_operator"]
    assert "grievance.create" in body["user"]["permissions"] and "citizen.read" not in body["user"]["permissions"]
    client.headers.update(csrf(client))
    # Signed in straight away, and sees only what it registered itself (nothing yet).
    assert client.get("/api/v1/auth/me").json()["user"]["username"] == username
    assert client.get("/api/v1/grievances").json()["total"] == 0
    assert client.get("/api/v1/iam/users").status_code == 403
    db_session.expire_all()
    uid = db_session.execute(select(User.id).where(User.username == username)).scalar_one()
    assert (
        db_session.execute(
            select(UserScopeAssignment.scope_type).where(UserScopeAssignment.user_id == uid)
        ).scalar_one()
        == "own"
    )
    assert db_session.execute(
        select(Notification).where(Notification.user_id == admin.id, Notification.category == "user_signed_up")
    ).first()
    assert db_session.execute(
        select(AuditLog).where(AuditLog.action == "iam.signed_up", AuditLog.resource_id == str(uid))
    ).first()
    # And can sign in again later with the same password.
    client.post("/api/v1/auth/logout")
    assert client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD}).status_code == 200


def test_signup_validation(client: TestClient, db_session: Session) -> None:
    _, weak = _signup(client, password="password")
    assert weak.status_code in (400, 422)
    _, bad_name = _signup(client, username="Not Valid!")
    assert bad_name.status_code == 422
    existing = make_user(db_session, ["auditor"], mfa=False)
    db_session.commit()
    _, dup = _signup(client, username=existing.username)
    assert dup.status_code == 409
    cross_origin = client.post(
        "/api/v1/auth/signup",
        json={"username": unique("test.su."), "full_name": "TEST X", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert cross_origin.status_code == 403


# --- Citizen portal ------------------------------------------------------------------------------


def _mobile() -> str:
    return "9" + "".join(secrets.choice("0123456789") for _ in range(9))


CITIZEN_PASSWORD = "Kx7-Monsoon-River-2026!"


def _register(client: TestClient, mobile: str) -> str:
    r = client.post(
        "/api/v1/citizen/register",
        json={"mobile": mobile, "name": "TEST Citizen", "password": CITIZEN_PASSWORD, "consent": True},
    )
    assert r.status_code == 202, r.text
    return str(r.json()["development_otp"])


def _citizen_login(client: TestClient, mobile: str) -> None:
    r = client.post("/api/v1/citizen/login", json={"mobile": mobile, "password": CITIZEN_PASSWORD})
    assert r.status_code == 200, r.text
    client.headers.update({"X-CSRF-Token": client.cookies.get("dgi_ccsrf") or ""})


def test_citizen_registration_stores_only_protected_data(client: TestClient, db_session: Session) -> None:
    mobile = _mobile()
    code = _register(client, mobile)
    acct = db_session.execute(
        select(CitizenAccount).where(CitizenAccount.mobile_hash == security.lookup_hash("+91" + mobile))
    ).scalar_one()
    assert mobile not in acct.mobile_encrypted and "TEST Citizen" not in acct.name_encrypted
    otp = db_session.execute(select(OtpChallenge).where(OtpChallenge.account_id == acct.id)).scalar_one()
    assert code not in otp.code_hash and acct.verified_at is None

    # Cannot sign in before verifying.
    r = client.post("/api/v1/citizen/login", json={"mobile": mobile, "password": CITIZEN_PASSWORD})
    assert r.status_code == 400 and r.json()["error"]["code"] == "mobile_not_verified"

    wrong = "000000" if code != "000000" else "111111"
    assert client.post("/api/v1/citizen/verify", json={"mobile": mobile, "code": wrong}).status_code == 400
    assert client.post("/api/v1/citizen/verify", json={"mobile": mobile, "code": code}).status_code == 200
    # Codes work once.
    assert client.post("/api/v1/citizen/verify", json={"mobile": mobile, "code": code}).status_code == 400
    # A verified number cannot be registered again.
    again = client.post(
        "/api/v1/citizen/register",
        json={"mobile": mobile, "name": "TEST Other", "password": CITIZEN_PASSWORD, "consent": True},
    )
    assert again.status_code == 409


def test_otp_attempts_are_limited(client: TestClient, db_session: Session) -> None:
    mobile = _mobile()
    code = _register(client, mobile)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        client.post("/api/v1/citizen/verify", json={"mobile": mobile, "code": wrong})
    # Even the right code is refused once the attempt budget is spent.
    assert client.post("/api/v1/citizen/verify", json={"mobile": mobile, "code": code}).status_code == 400


def test_citizen_requires_consent_and_valid_mobile(client: TestClient) -> None:
    base = {"name": "TEST Citizen", "password": CITIZEN_PASSWORD}
    assert (
        client.post("/api/v1/citizen/register", json={**base, "mobile": _mobile(), "consent": False}).status_code == 400
    )
    assert (
        client.post("/api/v1/citizen/register", json={**base, "mobile": "1234567890", "consent": True}).status_code
        == 400
    )


def test_citizen_files_and_tracks_only_own_grievances(client: TestClient, db_session: Session) -> None:
    geo = make_geography(db_session)
    db_session.commit()
    mobile = _mobile()
    code = _register(client, mobile)
    client.post("/api/v1/citizen/verify", json={"mobile": mobile, "code": code})

    assert client.get("/api/v1/citizen/me").status_code == 401
    _citizen_login(client, mobile)
    me = client.get("/api/v1/citizen/me").json()
    assert me["verified"] is True and mobile not in (me["mobile"] or "")

    units = client.get("/api/v1/citizen/reference/units/blocks", params={"parent_id": str(geo["district"])})
    assert units.status_code == 200 and {u["id"] for u in units.json()} >= {str(geo["block"])}

    body = {
        "subject": "TEST No drinking water",
        "description": "TEST DATA: the hand pump in the village has not worked for two weeks.",
        "category_id": str(geo["category"]),
        "location": {"village_id": str(geo["village"])},
    }
    no_csrf = client.post("/api/v1/citizen/grievances", json=body, headers={"X-CSRF-Token": ""})
    assert no_csrf.status_code == 403
    r = client.post("/api/v1/citizen/grievances", json=body)
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    assert r.json()["reference_no"].startswith("DGI/")

    db_session.expire_all()
    g = db_session.get(Grievance, gid)
    assert g is not None and g.citizen_account_id is not None and g.block_id == geo["block"]
    assert g.department_id == geo["department"]  # routed by the category default

    mine = client.get("/api/v1/citizen/grievances").json()
    assert [x["id"] for x in mine] == [gid]
    detail = client.get(f"/api/v1/citizen/grievances/{gid}").json()
    assert detail["status_label"] == "Received" and detail["timeline"]
    assert "assigned_officer" not in detail and "internal_notes" not in detail

    # A different citizen cannot see it.
    other = TestClient(client.app)
    m2 = _mobile()
    c2 = _register(other, m2)
    other.post("/api/v1/citizen/verify", json={"mobile": m2, "code": c2})
    _citizen_login(other, m2)
    assert other.get(f"/api/v1/citizen/grievances/{gid}").status_code == 404
    assert other.get("/api/v1/citizen/grievances").json() == []

    # A citizen session is not an officer session.
    assert client.get("/api/v1/grievances").status_code == 401

    assert client.post("/api/v1/citizen/logout").status_code == 204
    assert client.get("/api/v1/citizen/me").status_code == 401


def test_officers_see_portal_grievances(client: TestClient, db_session: Session) -> None:
    geo = make_geography(db_session)
    db_session.commit()
    mobile = _mobile()
    code = _register(client, mobile)
    client.post("/api/v1/citizen/verify", json={"mobile": mobile, "code": code})
    _citizen_login(client, mobile)
    r = client.post(
        "/api/v1/citizen/grievances",
        json={
            "subject": "TEST Street light",
            "description": "TEST DATA: the street light near the school is broken.",
            "category_id": str(geo["category"]),
            "location": {"village_id": str(geo["village"])},
        },
    )
    gid = r.json()["id"]
    src = db_session.execute(
        text(
            "SELECT s.code FROM grievance.grievances g JOIN ref.grievance_sources s ON s.id = g.source_id WHERE g.id = :i"
        ),
        {"i": gid},
    ).scalar_one()
    assert src == "CITIZEN_PORTAL"
    officer = TestClient(client.app)
    dm = make_user(
        db_session, ["district_magistrate"], scopes=[{"scope_type": "district", "district_id": geo["district"]}]
    )
    db_session.commit()
    login(officer, dm)
    assert officer.get(f"/api/v1/grievances/{gid}").status_code == 200
