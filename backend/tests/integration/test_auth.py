"""Phase 2: authentication, sessions, CSRF, MFA, lockout, authorisation, audit."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.audit.models import AuditLog
from app.modules.iam.catalogue import PERMISSIONS, ROLES
from app.modules.iam.models import LoginEvent, User, UserSession
from app.modules.notifications.models import Notification
from tests.integration.factories import PASSWORD, csrf, login, make_user


def _audit(db: Session, action: str, user_id: object) -> list[AuditLog]:
    db.expire_all()
    return list(
        db.execute(select(AuditLog).where(AuditLog.action == action, AuditLog.resource_id == str(user_id))).scalars()
    )


def test_login_sets_hardened_cookies_and_returns_permissions(client: TestClient, db_session: Session) -> None:
    u = make_user(db_session, ["department_officer"], scopes=[{"scope_type": "assigned"}])
    db_session.commit()
    r = client.post("/api/v1/auth/login", json={"username": u.username, "password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookie if c.startswith("dgi_session="))
    assert "HttpOnly" in session_cookie and "SameSite=strict" in session_cookie
    assert not next(c for c in cookie if c.startswith("dgi_csrf=")).count("HttpOnly")
    body = r.json()
    assert body["state"] == "authenticated"
    assert "grievance.work" in body["user"]["permissions"]
    assert "citizen.read" in body["user"]["permissions"]
    # Only a hash of the token is stored.
    token = client.cookies.get("dgi_session")
    assert db_session.execute(select(UserSession).where(UserSession.token_hash == token)).first() is None


def test_failed_logins_are_generic_and_recorded(client: TestClient, db_session: Session) -> None:
    u = make_user(db_session, ["auditor"], mfa=False)
    db_session.commit()
    bad = client.post("/api/v1/auth/login", json={"username": u.username, "password": "wrong-password"})
    unknown = client.post("/api/v1/auth/login", json={"username": "test.nobody.x", "password": "wrong-password"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json()["error"]["message"] == unknown.json()["error"]["message"] == "Invalid username or password."
    db_session.expire_all()
    events = db_session.execute(select(LoginEvent).where(LoginEvent.user_id == u.id)).scalars().all()
    assert [e.reason for e in events] == ["bad_password"]
    assert _audit(db_session, "auth.login", u.id)[0].outcome == "failure"


def test_account_lockout_after_threshold(client: TestClient, db_session: Session) -> None:
    u = make_user(db_session, ["auditor"], mfa=False)
    db_session.commit()
    for _ in range(get_settings().lockout_threshold):
        assert (
            client.post("/api/v1/auth/login", json={"username": u.username, "password": "nope-nope"}).status_code == 401
        )
    r = client.post("/api/v1/auth/login", json={"username": u.username, "password": PASSWORD})
    assert r.status_code == 423
    assert _audit(db_session, "auth.account_locked", u.id)
    # Wrong password while locked does not reveal the lock.
    assert client.post("/api/v1/auth/login", json={"username": u.username, "password": "nope"}).status_code == 401


def test_login_rate_limit(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "login_rate_limit_per_minute", 3)
    codes = [
        client.post("/api/v1/auth/login", json={"username": "test.rl", "password": "x"}).status_code for _ in range(5)
    ]
    assert codes[:3] == [401, 401, 401]
    assert codes[3:] == [429, 429]


def test_csrf_required_for_state_changes(client: TestClient, db_session: Session) -> None:
    u = make_user(db_session, ["department_officer"], scopes=[{"scope_type": "assigned"}])
    db_session.commit()
    client.post("/api/v1/auth/login", json={"username": u.username, "password": PASSWORD})
    assert client.post("/api/v1/notifications/read-all").json()["error"]["code"] == "csrf_failed"
    assert client.post("/api/v1/notifications/read-all", headers={"X-CSRF-Token": "forged"}).status_code == 403
    assert client.post("/api/v1/notifications/read-all", headers=csrf(client)).status_code == 204


def test_unauthenticated_and_expired_sessions(client: TestClient, db_session: Session) -> None:
    assert client.get("/api/v1/notifications").status_code == 401
    u = make_user(db_session, ["department_officer"], scopes=[{"scope_type": "assigned"}])
    db_session.commit()
    login(client, u)
    assert client.get("/api/v1/notifications").status_code == 200
    db_session.execute(
        update(UserSession)
        .where(UserSession.user_id == u.id)
        .values(last_seen_at=datetime.now(UTC) - timedelta(hours=2))
    )
    db_session.commit()
    r = client.get("/api/v1/notifications")
    assert r.status_code == 401 and "expired" in r.json()["error"]["message"]


def test_logout_revokes_session(client: TestClient, db_session: Session) -> None:
    u = make_user(db_session, ["department_officer"], scopes=[{"scope_type": "assigned"}])
    db_session.commit()
    login(client, u)
    token = client.cookies.get("dgi_session")
    assert client.post("/api/v1/auth/logout").status_code == 204
    client.cookies.set("dgi_session", token or "")
    assert client.get("/api/v1/notifications").status_code == 401


def test_privileged_user_must_enrol_mfa_and_change_password(client: TestClient, db_session: Session) -> None:
    u = make_user(db_session, ["super_admin"], mfa=False, must_change=True)
    db_session.commit()
    r = client.post("/api/v1/auth/login", json={"username": u.username, "password": PASSWORD})
    assert r.json()["state"] == "mfa_enrollment_required"
    assert r.json()["user"]["permissions"] == []
    blocked = client.get("/api/v1/iam/users")
    assert blocked.status_code == 403 and blocked.json()["error"]["details"][0]["state"] == "mfa_enrollment_required"
    setup = client.post("/api/v1/auth/mfa/setup", headers=csrf(client)).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    token_before = client.cookies.get("dgi_session")
    code = pyotp.TOTP(setup["secret"]).now()
    r = client.post("/api/v1/auth/mfa/confirm", json={"code": code}, headers=csrf(client))
    assert r.status_code == 200 and r.json()["state"] == "password_change_required"
    assert client.cookies.get("dgi_session") != token_before  # rotated after privilege change
    weak = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "short"},
        headers=csrf(client),
    )
    assert weak.json()["error"]["code"] == "weak_password"
    new_pw = "Another-Str0ng-Passphrase"
    r = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": new_pw},
        headers=csrf(client),
    )
    assert r.status_code == 200 and r.json()["state"] == "authenticated"
    assert client.get("/api/v1/iam/users", headers=csrf(client)).status_code == 200

    # Second sign-in requires the TOTP code; a replayed code is rejected.
    c2 = TestClient(client.app, raise_server_exceptions=False)
    r = c2.post("/api/v1/auth/login", json={"username": u.username, "password": new_pw})
    assert r.json()["state"] == "mfa_required"
    assert c2.post("/api/v1/auth/mfa/verify", json={"code": code}, headers=csrf(c2)).status_code == 400
    assert c2.post("/api/v1/auth/mfa/verify", json={"code": "000000"}, headers=csrf(c2)).status_code == 400


def test_permission_denied_is_enforced_and_audited(client: TestClient, db_session: Session) -> None:
    u = make_user(db_session, ["auditor"])
    db_session.commit()
    login(client, u)
    assert client.get("/api/v1/iam/users").status_code == 200  # auditors may read users
    r = client.post(
        "/api/v1/iam/users",
        json={
            "username": "test.x",
            "full_name": "x y",
            "roles": ["auditor"],
            "temporary_password": "Whatever-Passw0rd!",
        },
    )
    assert r.status_code == 403
    db_session.expire_all()
    denied = (
        db_session.execute(select(AuditLog).where(AuditLog.action == "access.denied", AuditLog.actor_user_id == u.id))
        .scalars()
        .all()
    )
    assert denied and denied[0].details["missing"] == ["iam.users.manage"]


def test_user_administration_flow(client: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, ["super_admin"])
    db_session.commit()
    login(client, admin)
    r = client.post(
        "/api/v1/iam/users",
        json={
            "username": "test.newofficer" + admin.username[-6:],
            "full_name": "TEST New Officer",
            "roles": ["department_officer"],
            "scopes": [{"scope_type": "assigned"}],
            "temporary_password": "Temp-Passw0rd-Long!",
        },
    )
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["must_change_password"] and new["roles"] == ["department_officer"]
    assert client.put(f"/api/v1/iam/users/{admin.id}/roles", json={"roles": ["auditor"]}).status_code == 409
    r = client.put(f"/api/v1/iam/users/{new['id']}/roles", json={"roles": ["not_a_role"]})
    assert r.status_code == 422
    r = client.patch(f"/api/v1/iam/users/{new['id']}", json={"is_active": False})
    assert r.json()["is_active"] is False
    r = client.post(
        "/api/v1/iam/users",
        json={
            "username": "test.weak" + admin.username[-6:],
            "full_name": "x y",
            "roles": ["auditor"],
            "temporary_password": "weak",
        },
    )
    assert r.json()["error"]["code"] == "weak_password"


def test_super_admin_cannot_read_citizen_data_and_auditor_is_read_only() -> None:
    assert "citizen.read" not in ROLES["super_admin"]["permissions"]  # type: ignore[operator]
    assert not any(p.startswith("grievance.") for p in ROLES["super_admin"]["permissions"])  # type: ignore[union-attr]
    auditor = set(ROLES["auditor"]["permissions"])  # type: ignore[call-overload]
    assert all(p.endswith(".read") for p in auditor), auditor
    assert "citizen.read" not in auditor


def test_catalogue_matches_database(db_session: Session) -> None:
    db_perms = set(db_session.execute(text("SELECT code FROM iam.permissions")).scalars())
    assert db_perms == set(PERMISSIONS)
    rows = db_session.execute(
        text(
            "SELECT r.code, p.code FROM iam.role_permissions rp JOIN iam.roles r ON r.id = rp.role_id "
            "JOIN iam.permissions p ON p.id = rp.permission_id"
        )
    ).all()
    assert {(r, p) for r, p in rows} == {(r, p) for r, d in ROLES.items() for p in d["permissions"]}  # type: ignore[attr-defined]


def test_suspicious_login_from_new_address_notifies_user(migrated: object, db_session: Session) -> None:
    from app.main import create_app

    u = make_user(db_session, ["department_officer"], scopes=[{"scope_type": "assigned"}])
    db_session.commit()
    app = create_app()
    for ip in ("10.10.0.1", "10.10.0.1", "10.99.0.7"):
        c = TestClient(app, client=(ip, 5000))
        assert c.post("/api/v1/auth/login", json={"username": u.username, "password": PASSWORD}).status_code == 200
    db_session.expire_all()
    flagged = (
        db_session.execute(select(LoginEvent).where(LoginEvent.user_id == u.id, LoginEvent.suspicious.is_(True)))
        .scalars()
        .all()
    )
    assert [str(e.ip_address) for e in flagged] == ["10.99.0.7"]
    assert db_session.execute(
        select(Notification).where(Notification.user_id == u.id, Notification.category == "security")
    ).first()


def test_audit_chain_verifies_and_detects_tampering(
    client: TestClient, db_session: Session, owner_engine: object
) -> None:
    admin = make_user(db_session, ["auditor"])
    db_session.commit()
    login(client, admin)
    assert client.get("/api/v1/audit/verify").json()["valid"] is True
    # The runtime role cannot modify audit rows at all.
    with pytest.raises(Exception, match="permission denied"):
        db_session.execute(text("UPDATE audit.audit_logs SET outcome = 'success' WHERE seq = 1"))
    db_session.rollback()
    # An owner-level tamper is detected by the hash chain.
    with owner_engine.begin() as conn:  # type: ignore[attr-defined]
        seq = conn.execute(text("SELECT min(seq) FROM audit.audit_logs")).scalar()
        conn.execute(
            text("UPDATE audit.audit_logs SET details = '{\"tampered\": true}' WHERE seq = :s"),
            {"s": seq},
        )
    result = client.get("/api/v1/audit/verify").json()
    assert result["valid"] is False and result["first_invalid_seq"] == seq
    with owner_engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(text("DELETE FROM audit.audit_logs"))  # reset chain for later tests (owner only)


def test_password_hashes_are_argon2id(db_session: Session) -> None:
    u = make_user(db_session, ["auditor"], mfa=False)
    h = db_session.execute(select(User.password_hash).where(User.id == u.id)).scalar_one()
    assert h.startswith("$argon2id$")


def test_login_origin_check(client: TestClient, db_session: Session) -> None:
    u = make_user(db_session, ["department_officer"], scopes=[{"scope_type": "assigned"}])
    db_session.commit()
    body = {"username": u.username, "password": PASSWORD}
    same = client.post("/api/v1/auth/login", json=body, headers={"Origin": "http://testserver"})
    assert same.status_code == 200
    cross = client.post("/api/v1/auth/login", json=body, headers={"Origin": "https://evil.example"})
    assert cross.status_code == 403 and cross.json()["error"]["code"] == "permission_denied"
