"""TEST DATA factories for integration tests. Every name is prefixed 'TEST'."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.modules.iam.models import MfaCredential, Role, User, UserRole, UserScopeAssignment

PASSWORD = "Test-Passw0rd-Strong!"


@dataclass
class TestUser:
    id: uuid.UUID
    username: str
    totp_secret: str | None = None


def unique(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def make_user(
    db: Session,
    roles: list[str],
    *,
    scopes: list[dict[str, object]] | None = None,
    mfa: bool | None = None,
    must_change: bool = False,
    department_id: uuid.UUID | None = None,
) -> TestUser:
    username = unique("test.")
    user = User(
        username=username,
        full_name="TEST User",
        password_hash=security.hash_password(PASSWORD),
        must_change_password=must_change,
        department_id=department_id,
    )
    db.add(user)
    db.flush()
    for rid in db.execute(select(Role.id).where(Role.code.in_(roles))).scalars():
        db.add(UserRole(user_id=user.id, role_id=rid))
    for s in scopes or []:
        db.add(UserScopeAssignment(user_id=user.id, **s))
    secret = None
    needs_mfa = mfa if mfa is not None else any(r in get_settings().mfa_required_roles for r in roles)
    if needs_mfa:
        secret = security.new_totp_secret()
        from datetime import UTC, datetime

        db.add(
            MfaCredential(
                user_id=user.id,
                secret_encrypted=security.encrypt_text(secret) or "",
                confirmed_at=datetime.now(UTC),
            )
        )
    db.flush()
    return TestUser(user.id, username, secret)


def login(client: TestClient, user: TestUser, password: str = PASSWORD) -> TestClient:
    r = client.post("/api/v1/auth/login", json={"username": user.username, "password": password})
    assert r.status_code == 200, r.text
    if r.json()["state"] == "mfa_required":
        assert user.totp_secret
        code = pyotp.TOTP(user.totp_secret).now()
        r = client.post("/api/v1/auth/mfa/verify", json={"code": code}, headers=csrf(client))
        assert r.status_code == 200, r.text
    client.headers.update(csrf(client))
    return client


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get(get_settings().csrf_cookie_name) or ""}


def make_geography(db: Session) -> dict[str, uuid.UUID]:
    """Synthetic TEST DATA administrative units (no geometry)."""
    tag = uuid.uuid4().hex[:6]
    d = db.execute(
        text("INSERT INTO ref.districts (name_en, state_name_en) VALUES (:n, 'TEST STATE') RETURNING id"),
        {"n": f"TEST DISTRICT {tag}"},
    ).scalar_one()
    sd = db.execute(
        text("INSERT INTO ref.subdivisions (name_en, district_id) VALUES (:n, :d) RETURNING id"),
        {"n": f"TEST SUBDIV {tag}", "d": d},
    ).scalar_one()
    b1 = db.execute(
        text("INSERT INTO ref.blocks (name_en, district_id, subdivision_id) VALUES (:n, :d, :s) RETURNING id"),
        {"n": f"TEST BLOCK A {tag}", "d": d, "s": sd},
    ).scalar_one()
    b2 = db.execute(
        text("INSERT INTO ref.blocks (name_en, district_id) VALUES (:n, :d) RETURNING id"),
        {"n": f"TEST BLOCK B {tag}", "d": d},
    ).scalar_one()
    gp = db.execute(
        text("INSERT INTO ref.gram_panchayats (name_en, block_id) VALUES (:n, :b) RETURNING id"),
        {"n": f"TEST GP {tag}", "b": b1},
    ).scalar_one()
    v1 = db.execute(
        text(
            "INSERT INTO ref.villages (name_en, district_id, block_id, gram_panchayat_id, subdivision_id) "
            "VALUES (:n, :d, :b, :g, :s) RETURNING id"
        ),
        {"n": f"Testpur{tag}", "d": d, "b": b1, "g": gp, "s": sd},
    ).scalar_one()
    dep = db.execute(
        text("INSERT INTO ref.departments (code, name_en) VALUES (:c, :n) RETURNING id"),
        {"c": f"TEST_DEPT_{tag.upper()}", "n": f"TEST Department {tag}"},
    ).scalar_one()
    dep2 = db.execute(
        text("INSERT INTO ref.departments (code, name_en) VALUES (:c, :n) RETURNING id"),
        {"c": f"TEST_DEPT2_{tag.upper()}", "n": f"TEST Department 2 {tag}"},
    ).scalar_one()
    cat = db.execute(
        text(
            "INSERT INTO ref.issue_categories (code, name_en, default_department_id, is_essential_service) "
            "VALUES (:c, :n, :d, true) RETURNING id"
        ),
        {"c": f"TEST_WATER_{tag.upper()}", "n": f"TEST Water supply {tag}", "d": dep},
    ).scalar_one()
    return {
        "district": d,
        "subdivision": sd,
        "block": b1,
        "block_b": b2,
        "gp": gp,
        "village": v1,
        "department": dep,
        "department_b": dep2,
        "category": cat,
        "tag": tag,
    }  # type: ignore[dict-item]
