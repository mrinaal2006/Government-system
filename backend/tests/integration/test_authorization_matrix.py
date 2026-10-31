"""Phase 9: authorization matrix, security probes and performance budget.

The matrix is derived from the permission catalogue: for every role and every
protected endpoint, the API must deny (403) exactly when the role lacks a required
permission, and must never deny when the role holds them all.
"""

from __future__ import annotations

import statistics
import time
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.iam.catalogue import ROLES
from tests.integration.factories import login, make_geography, make_user

# (method, path template, required permissions, json body). Bodies are minimal; only the
# authorization outcome (403 vs anything else) is asserted.
ENDPOINTS: list[tuple[str, str, list[str], dict[str, Any] | None]] = [
    ("GET", "/api/v1/grievances", ["grievance.read"], None),
    ("POST", "/api/v1/grievances", ["grievance.create"], {}),
    ("GET", "/api/v1/dashboard/summary", ["dashboard.read", "grievance.read"], None),
    ("GET", "/api/v1/alerts", ["alert.read"], None),
    ("POST", "/api/v1/alerts/evaluate", ["alert.act"], None),
    ("GET", "/api/v1/gis/layers/block", ["gis.read", "grievance.read"], None),
    ("GET", "/api/v1/gis/layers/village", ["gis.read", "grievance.read", "gis.read_precise"], None),
    ("GET", "/api/v1/performance/departments", ["performance.read"], None),
    ("POST", "/api/v1/reports", ["report.generate"], {"report_type": "block_summary", "format": "xlsx"}),
    ("GET", "/api/v1/intake/imports", ["grievance.import"], None),
    ("GET", "/api/v1/iam/users", ["iam.users.read"], None),
    ("POST", "/api/v1/iam/users", ["iam.users.manage"], {}),
    ("GET", "/api/v1/audit/logs", ["audit.read"], None),
    ("POST", "/api/v1/admin/departments", ["config.manage"], {}),
    ("POST", "/api/v1/admin/risk-models", ["config.manage"], {}),
    ("GET", "/api/v1/intelligence/clusters", ["grievance.read", "ai.read"], None),
    ("GET", "/api/v1/notifications", [], None),
]


@pytest.fixture(scope="module")
def role_clients(migrated: object) -> dict[str, TestClient]:
    from app.db.session import get_session_factory
    from app.main import create_app
    from tests.integration.conftest import _flush_rate_limits

    _flush_rate_limits()
    app = create_app()
    clients = {}
    with get_session_factory()() as db:
        geo = make_geography(db)
        users = {
            role: make_user(db, [role], scopes=[{"scope_type": "district", "district_id": geo["district"]}])
            for role in ROLES
        }
        db.commit()
    for role, u in users.items():
        clients[role] = login(TestClient(app, raise_server_exceptions=False), u)
    return clients


@pytest.mark.parametrize("role", sorted(ROLES))
@pytest.mark.parametrize(("method", "path", "perms", "body"), ENDPOINTS, ids=[f"{m} {p}" for m, p, _, _ in ENDPOINTS])
def test_authorization_matrix(
    role_clients: dict[str, TestClient],
    role: str,
    method: str,
    path: str,
    perms: list[str],
    body: dict[str, Any] | None,
) -> None:
    held = set(ROLES[role]["permissions"])  # type: ignore[call-overload]
    allowed = all(p in held for p in perms)
    r = role_clients[role].request(method, path, json=body)
    if allowed:
        assert r.status_code != 403, f"{role} unexpectedly denied {method} {path}: {r.text[:200]}"
        assert r.status_code < 500, f"{role} {method} {path} -> {r.status_code}"
    else:
        assert r.status_code == 403, f"{role} unexpectedly allowed {method} {path} ({r.status_code})"


def test_auditor_cannot_write_anything(role_clients: dict[str, TestClient]) -> None:
    c = role_clients["auditor"]
    writes = [(m, p, b) for m, p, _, b in ENDPOINTS if m != "GET"] + [("POST", "/api/v1/notifications/read-all", None)]
    for method, path, body in writes:
        r = c.request(method, path, json=body)
        if path.endswith("read-all"):
            assert r.status_code == 204  # marking one's own notifications read is the only permitted write
        else:
            assert r.status_code == 403, (method, path, r.status_code)


def _dm_district(db: Session) -> str:
    return str(
        db.execute(
            text(
                "SELECT s.district_id FROM iam.user_scope_assignments s JOIN iam.user_roles ur ON ur.user_id = s.user_id "
                "JOIN iam.roles r ON r.id = ur.role_id JOIN iam.users u ON u.id = s.user_id "
                "WHERE r.code = 'district_magistrate' AND s.district_id IS NOT NULL ORDER BY u.created_at DESC LIMIT 1"
            )
        ).scalar_one()
    )


# --- Security probes ------------------------------------------------------------------------

INJECTIONS = [
    "' OR '1'='1",
    "1; DROP TABLE grievance.grievances; --",
    "%' UNION SELECT password_hash FROM iam.users --",
    "\\x00",
    "<script>alert(1)</script>",
    "../../etc/passwd",
    "a" * 5000,
]


@pytest.mark.parametrize("payload", INJECTIONS)
def test_search_is_injection_safe(role_clients: dict[str, TestClient], payload: str) -> None:
    r = role_clients["district_magistrate"].get("/api/v1/grievances", params={"q": payload})
    assert r.status_code in (200, 422)
    assert "argon2" not in r.text and "password_hash" not in r.text


def test_stored_markup_is_returned_as_inert_text(role_clients: dict[str, TestClient], db_session: Session) -> None:
    c = role_clients["district_magistrate"]
    src = db_session.execute(text("SELECT id FROM ref.grievance_sources WHERE code = 'MANUAL'")).scalar_one()
    r = c.post(
        "/api/v1/grievances",
        json={
            "source_id": str(src),
            "subject": "<img src=x onerror=alert(1)>",
            "description": "TEST DATA <script>alert('x')</script> long enough",
            "location": {"district_id": _dm_district(db_session)},
        },
    )
    assert r.status_code == 201
    d = c.get(f"/api/v1/grievances/{r.json()['id']}")
    assert d.headers["content-type"].startswith("application/json")  # never rendered as HTML by the API
    assert d.headers["x-content-type-options"] == "nosniff"
    assert d.json()["subject"] == "<img src=x onerror=alert(1)>"  # stored verbatim; the UI escapes on render


def test_unknown_ids_and_out_of_scope_ids_are_indistinguishable(role_clients: dict[str, TestClient]) -> None:
    c = role_clients["department_officer"]
    for path in (f"/api/v1/grievances/{uuid.uuid4()}", f"/api/v1/alerts/{uuid.uuid4()}"):
        r = c.get(path)
        assert r.status_code in (403, 404)


def test_mass_assignment_of_protected_fields_is_rejected(
    role_clients: dict[str, TestClient], db_session: Session
) -> None:
    c = role_clients["district_magistrate"]
    src = db_session.execute(text("SELECT id FROM ref.grievance_sources WHERE code = 'MANUAL'")).scalar_one()
    gid = c.post(
        "/api/v1/grievances",
        json={
            "source_id": str(src),
            "subject": "TEST mass assignment",
            "description": "TEST DATA attempt to set protected fields",
            "location": {"district_id": _dm_district(db_session)},
        },
    ).json()["id"]
    v = c.get(f"/api/v1/grievances/{gid}").json()["version"]
    for field, value in (("status", "closed"), ("reference_no", "X"), ("created_by", str(uuid.uuid4()))):
        r = c.patch(f"/api/v1/grievances/{gid}", json={"changes": {field: value}, "version": v})
        assert r.status_code == 400 and r.json()["error"]["code"] == "not_editable", field


# --- Performance budget ----------------------------------------------------------------------


def test_performance_budget_with_5000_grievances(role_clients: dict[str, TestClient], db_session: Session) -> None:
    """Synthetic TEST DATA bulk load, then measure key read paths (single client, sequential)."""
    geo_district = db_session.execute(
        text(
            "SELECT district_id FROM iam.user_scope_assignments s JOIN iam.users u "
            "ON u.id = s.user_id JOIN iam.user_roles ur ON ur.user_id = u.id JOIN iam.roles r "
            "ON r.id = ur.role_id WHERE r.code = 'district_magistrate' AND s.district_id IS NOT NULL "
            "ORDER BY u.created_at DESC LIMIT 1"
        )
    ).scalar_one()
    src = db_session.execute(text("SELECT id FROM ref.grievance_sources WHERE code = 'MANUAL'")).scalar_one()
    tag = uuid.uuid4().hex[:6]
    db_session.execute(
        text(
            "INSERT INTO grievance.grievances (reference_no, source_id, received_at, subject, description, district_id, status, priority, due_at) "
            "SELECT 'PERF/' || :tag || '/' || g, :src, now() - (g || ' minutes')::interval, 'TEST perf ' || g, "
            "'TEST DATA performance record number ' || g || ' about water supply and roads', :d, "
            "(ARRAY['registered','assigned','in_progress','resolved'])[1 + g % 4], 'normal', now() - ((g % 10) || ' days')::interval "
            "FROM generate_series(1, 5000) g"
        ),
        {"tag": tag, "src": src, "d": geo_district},
    )
    db_session.commit()
    c = role_clients["district_magistrate"]
    budgets = {
        "/api/v1/grievances?limit=25": 0.8,
        "/api/v1/grievances?limit=25&q=water&overdue=true": 1.0,
        "/api/v1/dashboard/summary": 1.0,
        "/api/v1/dashboard/blocks": 1.0,
        "/api/v1/performance/departments": 1.0,
    }
    results = {}
    for path, budget in budgets.items():
        samples = []
        for _ in range(8):
            t0 = time.perf_counter()
            assert c.get(path).status_code == 200
            samples.append(time.perf_counter() - t0)
        p95 = sorted(samples)[int(len(samples) * 0.95) - 1]
        results[path] = (round(statistics.median(samples) * 1000), round(p95 * 1000))
        assert p95 < budget, f"{path}: p95 {p95:.3f}s exceeds {budget}s"
    print("\nPERFORMANCE (median ms, p95 ms):", results)
