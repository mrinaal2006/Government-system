"""Phases 4-8 end to end against real PostgreSQL/PostGIS, Redis and Garage. TEST DATA only."""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditLog
from app.modules.grievances.models import Complainant, Grievance, GrievanceStatusHistory
from app.modules.notifications.models import Notification
from tests.integration.factories import csrf, login, make_geography, make_user

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@dataclass
class World:
    geo: dict[str, Any]
    users: dict[str, Any]
    source_id: str
    app: Any

    def client(self, who: str) -> TestClient:
        c = TestClient(self.app, raise_server_exceptions=False)
        return login(c, self.users[who])


@pytest.fixture
def world(migrated: object, db_session: Session) -> World:
    from app.main import create_app
    from tests.integration.conftest import _flush_rate_limits

    _flush_rate_limits()
    geo = make_geography(db_session)
    d, dep = geo["district"], geo["department"]
    users = {
        "dm": make_user(
            db_session,
            ["district_magistrate"],
            scopes=[{"scope_type": "district", "district_id": d}],
        ),
        "deo": make_user(db_session, ["data_entry_operator"], scopes=[{"scope_type": "own"}]),
        "officer": make_user(
            db_session,
            ["department_officer"],
            scopes=[{"scope_type": "assigned"}],
            department_id=dep,
        ),
        "officer2": make_user(
            db_session,
            ["department_officer"],
            scopes=[{"scope_type": "assigned"}],
            department_id=dep,
        ),
        "head": make_user(
            db_session,
            ["department_head"],
            scopes=[{"scope_type": "department", "department_id": dep}],
        ),
        "bdo_b": make_user(
            db_session,
            ["block_development_officer"],
            scopes=[{"scope_type": "block", "block_id": geo["block_b"]}],
        ),
        "auditor": make_user(db_session, ["auditor"], scopes=[{"scope_type": "district", "district_id": d}]),
        "admin": make_user(db_session, ["super_admin"]),
    }
    src = db_session.execute(text("SELECT id FROM ref.grievance_sources WHERE code = 'MANUAL'")).scalar_one()
    db_session.commit()
    return World(geo, users, str(src), create_app())


def register(c: TestClient, w: World, **over: Any) -> dict[str, Any]:
    body = {
        "source_id": w.source_id,
        "subject": "TEST No water supply for a week",
        "description": f"TEST DATA. The hand pump near the school in Testpur{w.geo['tag']} has not given water for seven "
        "days and residents are walking two kilometres.",
        "category_id": str(w.geo["category"]),
        "priority": "high",
        "location": {"village_id": str(w.geo["village"])},
        "complainant": {"name": "TEST Citizen", "mobile": "9876543210", "consent_recorded": True},
    }
    body.update(over)
    r = c.post("/api/v1/grievances", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def detail(c: TestClient, gid: str) -> dict[str, Any]:
    r = c.get(f"/api/v1/grievances/{gid}")
    assert r.status_code == 200, r.text
    return r.json()


def act(c: TestClient, gid: str, action: str, note: str | None = None) -> Any:
    v = detail(c, gid)["version"]
    return c.post(f"/api/v1/grievances/{gid}/transition", json={"action": action, "version": v, "note": note})


def test_registration_derives_location_encrypts_pii_and_has_immutable_reference(
    world: World, db_session: Session
) -> None:
    deo = world.client("deo")
    g = register(deo, world)
    assert g["reference_no"].startswith("DGI/") and g["status"] == "registered"
    assert g["due_at"] is None  # no SLA policy configured: nothing invented
    row = db_session.get(Grievance, uuid.UUID(g["id"]))
    assert row is not None
    assert row.block_id == world.geo["block"] and row.district_id == world.geo["district"]
    assert row.department_id == world.geo["department"]  # configured category default
    c = db_session.get(Complainant, row.complainant_id)
    assert c is not None and "9876543210" not in (c.mobile_encrypted or "") and c.mobile_hash
    with pytest.raises(Exception, match="immutable"):
        db_session.execute(text("UPDATE grievance.grievances SET reference_no = 'X' WHERE id = :i"), {"i": row.id})
    db_session.rollback()
    with pytest.raises(Exception, match="permission denied"):
        db_session.execute(
            text("DELETE FROM grievance.grievance_status_history WHERE grievance_id = :i"),
            {"i": row.id},
        )
    db_session.rollback()
    with pytest.raises(Exception, match="permission denied"):
        db_session.execute(
            text("UPDATE grievance.grievance_status_history SET reason = 'x' WHERE grievance_id = :i"),
            {"i": row.id},
        )
    db_session.rollback()


def test_inconsistent_location_is_rejected(world: World) -> None:
    deo = world.client("deo")
    r = deo.post(
        "/api/v1/grievances",
        json={
            "source_id": world.source_id,
            "subject": "TEST mismatch",
            "description": "TEST DATA description long enough",
            "location": {
                "village_id": str(world.geo["village"]),
                "block_id": str(world.geo["block_b"]),
            },
        },
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "location_mismatch"


def test_full_lifecycle_with_history_concurrency_and_separation_of_duties(world: World, db_session: Session) -> None:
    deo, dm, officer = world.client("deo"), world.client("dm"), world.client("officer")
    g = register(deo, world)
    gid = g["id"]
    officer_id = str(world.users["officer"].id)
    stale = detail(dm, gid)["version"]
    r = dm.post(f"/api/v1/grievances/{gid}/assign", json={"officer_id": officer_id, "version": stale})
    assert r.status_code == 200 and r.json()["status"] == "assigned"
    # Concurrency: the same stale version is now rejected.
    r = dm.post(f"/api/v1/grievances/{gid}/assign", json={"officer_id": officer_id, "version": stale})
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale_version"
    # The assigned officer now sees it (assigned scope) and gets a notification.
    assert any(i["id"] == gid for i in officer.get("/api/v1/grievances").json()["items"])
    assert db_session.execute(
        select(Notification).where(
            Notification.user_id == world.users["officer"].id, Notification.category == "assignment"
        )
    ).first()
    # Another officer cannot see it at all.
    assert world.client("officer2").get(f"/api/v1/grievances/{gid}").status_code == 404
    assert act(officer, gid, "start_work").status_code == 200
    assert act(officer, gid, "submit_resolution", "short").json()["error"]["code"] == "reason_required"
    assert act(officer, gid, "submit_resolution", "TEST Pump repaired and water restored on site.").status_code == 200
    assert act(officer, gid, "accept_resolution").status_code == 403  # lacks grievance.verify
    assert act(dm, gid, "return_resolution", "TEST Please attach a photograph of the repaired pump.").status_code == 200
    assert act(officer, gid, "submit_resolution", "TEST Photograph attached; pump working.").status_code == 200
    assert act(dm, gid, "accept_resolution").json()["status"] == "resolved"
    assert act(dm, gid, "close").json()["status"] == "closed"
    assert act(dm, gid, "reopen").json()["error"]["code"] == "reason_required"
    assert act(dm, gid, "reopen", "TEST Residents report the pump failed again.").json()["status"] == "reopened"
    assert act(dm, gid, "close").status_code == 409  # invalid transition
    hist = dm.get(f"/api/v1/grievances/{gid}/history").json()
    assert [h["to_status"] for h in hist["status_history"]] == [
        "registered",
        "assigned",
        "in_progress",
        "resolution_submitted",
        "in_progress",
        "resolution_submitted",
        "resolved",
        "closed",
        "reopened",
    ]
    assert len(hist["assignments"]) == 1 and {c["kind"] for c in hist["comments"]} >= {
        "resolution",
        "verification",
    }
    assert detail(dm, gid)["reopened_count"] == 1


def test_submitter_cannot_verify_own_resolution(world: World) -> None:
    dm = world.client("dm")
    gid = register(world.client("deo"), world)["id"]
    v = detail(dm, gid)["version"]
    dm.post(
        f"/api/v1/grievances/{gid}/assign",
        json={"officer_id": str(world.users["dm"].id), "version": v},
    )
    act(dm, gid, "start_work")
    act(dm, gid, "submit_resolution", "TEST Resolved by the same officer.")
    r = act(dm, gid, "accept_resolution")
    assert r.status_code == 403 and "someone other" in r.json()["error"]["message"]


def test_scope_isolation_and_role_limits(world: World) -> None:
    gid = register(world.client("deo"), world)["id"]
    bdo_b = world.client("bdo_b")
    assert bdo_b.get(f"/api/v1/grievances/{gid}").status_code == 404
    assert all(i["id"] != gid for i in bdo_b.get("/api/v1/grievances").json()["items"])
    assert world.client("head").get(f"/api/v1/grievances/{gid}").status_code == 200  # department scope
    admin = world.client("admin")
    assert admin.get("/api/v1/grievances").status_code == 403  # super admin: no grievance access
    auditor = world.client("auditor")
    d = detail(auditor, gid)
    assert d["complainant"]["masked"] is True and d["complainant"]["mobile"] == "********10"
    assert auditor.post(f"/api/v1/grievances/{gid}/comments", json={"body": "x"}).status_code == 403
    assert d["allowed_actions"] == []


def test_pii_access_is_audited(world: World, db_session: Session) -> None:
    dm = world.client("dm")
    gid = register(world.client("deo"), world)["id"]
    d = detail(dm, gid)
    assert d["complainant"] == {
        "masked": False,
        "name": "TEST Citizen",
        "mobile": "9876543210",
        "email": None,
        "address": None,
        "consent_recorded": True,
    }
    db_session.expire_all()
    assert db_session.execute(
        select(AuditLog).where(AuditLog.action == "citizen.viewed", AuditLog.resource_id == gid)
    ).first()


def test_attachments_are_validated_stored_and_downloadable(world: World) -> None:
    deo = world.client("deo")
    gid = register(deo, world)["id"]
    r = deo.post(
        f"/api/v1/grievances/{gid}/attachments",
        files={"file": ("../../etc/photo.png", PNG, "image/png")},
    )
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["filename"] == "photo.png" and att["scan_status"] == "not_scanned"
    dl = deo.get(f"/api/v1/grievances/{gid}/attachments/{att['id']}")
    assert dl.status_code == 200 and dl.content == PNG and "attachment;" in dl.headers["content-disposition"]
    bad = deo.post(
        f"/api/v1/grievances/{gid}/attachments",
        files={"file": ("photo.pdf", PNG, "application/pdf")},
    )
    assert bad.json()["error"]["code"] == "file_type_not_allowed"
    exe = deo.post(
        f"/api/v1/grievances/{gid}/attachments",
        files={"file": ("x.png", b"MZ\x90\x00" + b"\x00" * 50, "image/png")},
    )
    assert exe.json()["error"]["code"] == "file_type_not_allowed"


def test_duplicate_detection_and_review(world: World) -> None:
    deo, dm = world.client("deo"), world.client("dm")
    first = register(deo, world)
    second = register(deo, world, subject="TEST Hand pump broken")
    assert first["id"] in [d["grievance_id"] for d in second["possible_duplicates"]]
    intel = dm.get(f"/api/v1/grievances/{second['id']}/intelligence").json()
    dup = next(d for d in intel["duplicates"] if d["candidate_grievance_id"] == first["id"])
    assert dup["evidence"]
    r = dm.post(f"/api/v1/intelligence/duplicates/{dup['id']}/review", json={"confirm": True})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    assert detail(dm, second["id"])["duplicate_of_id"] == first["id"]


def test_ai_suggestions_are_explainable_versioned_and_need_review(world: World, db_session: Session) -> None:
    from app.modules.intelligence import service as intel

    admin, dm = world.client("admin"), world.client("dm")
    other_cat = db_session.execute(
        text(
            "INSERT INTO ref.issue_categories (code, name_en, default_department_id) VALUES "
            "(:c, 'TEST Roads', :d) RETURNING id"
        ),
        {"c": f"TEST_ROAD_{world.geo['tag'].upper()}", "d": world.geo["department_b"]},
    ).scalar_one()
    db_session.commit()
    r = admin.post(
        "/api/v1/admin/classification-rules",
        json={"category_id": str(other_cat), "keyword": "pothole", "weight": 2},
    )
    assert r.status_code == 201
    gid = register(
        world.client("deo"),
        world,
        category_id=None,
        description=f"TEST DATA. Large pothole on the main road near Testpur{world.geo['tag']} market causing accidents.",
    )["id"]
    before = detail(dm, gid)
    with db_session.begin():
        intel.analyse(db_session, uuid.UUID(gid))
    after = detail(dm, gid)
    assert after["status"] == before["status"] and after["category"] is None  # AI changed nothing
    data = dm.get(f"/api/v1/grievances/{gid}/intelligence").json()
    cat = next(c for c in data["classifications"] if c["task"] == "category" and c["verification_status"] == "pending")
    assert cat["prediction"]["category_id"] == str(other_cat)
    assert cat["model_id"] == "keyword-rules" and cat["model_version"] != "empty" and cat["confidence"] == 1.0
    assert cat["evidence"][0]["matched_keywords"] == ["pothole"] and cat["input_ref"].startswith(
        f"grievance:{gid}:sha256:"
    )
    loc = next(c for c in data["classifications"] if c["task"] == "location")
    assert loc["prediction"]["village_id"] == str(world.geo["village"])
    assert any(c["task"] == "summary" for c in data["classifications"])
    r = dm.post(f"/api/v1/intelligence/classifications/{cat['id']}/review", json={"decision": "accept"})
    assert r.status_code == 200 and r.json()["verification_status"] == "accepted"
    assert detail(dm, gid)["category"]["id"] == str(other_cat)
    assert (
        dm.post(f"/api/v1/intelligence/classifications/{cat['id']}/review", json={"decision": "accept"}).status_code
        == 409
    )


def test_import_records_provenance_and_prevents_duplicates(world: World, db_session: Session) -> None:
    from app.modules.intake import service as intake

    deo = world.client("deo")
    tag = world.geo["tag"]
    csv_text = (
        "external_id,received_at,subject,description,priority,village_name,complainant_mobile\n"
        f"EXT-{tag}-1,2026-10-01,TEST road,TEST DATA imported complaint number one about drainage,high,Testpur{tag},9000000001\n"
        f"EXT-{tag}-2,01/10/2026,TEST light,TEST DATA imported complaint number two about street lights,normal,Nowhere{tag},\n"
        f"EXT-{tag}-1,2026-10-01,TEST dup,TEST DATA duplicate external id within the same file,,,\n"
        f",2026-10-01,TEST missing,TEST DATA row without an external identifier,,,\n"
    ).encode()
    files = {"file": ("export.csv", csv_text, "text/csv")}
    r = deo.post("/api/v1/intake/imports", data={"source_code": "CM_HELPLINE"}, files=files)
    assert r.status_code == 202, r.text
    batch_id = r.json()["id"]
    assert (
        deo.post("/api/v1/intake/imports", data={"source_code": "CM_HELPLINE"}, files=files).json()["error"]["code"]
        == "duplicate_file"
    )
    with db_session.begin():
        b = intake.process_batch(db_session, uuid.UUID(batch_id))
    assert (b.status, b.total_rows, b.created_count, b.duplicate_count, b.failed_count) == (
        "completed",
        4,
        2,
        1,
        1,
    )
    assert any("not found" in w for e in b.errors for w in e.get("warnings", []))
    g = db_session.execute(
        select(Grievance).where(Grievance.import_batch_id == b.id, Grievance.village_id.is_not(None))
    ).scalar_one()
    assert g.created_by == world.users["deo"].id and g.priority == "high"
    with pytest.raises(Exception, match=r"unique|duplicate"):
        db_session.execute(
            text(
                "INSERT INTO grievance.grievance_external_references (grievance_id, source_id, external_id) "
                "SELECT :g, source_id, external_id FROM grievance.grievance_external_references "
                "WHERE external_id = :e"
            ),
            {"g": g.id, "e": f"EXT-{tag}-1"},
        )
    db_session.rollback()


def test_sla_breach_escalates_and_notifies(world: World, db_session: Session) -> None:
    from app.modules.performance import service as perf

    admin, dm = world.client("admin"), world.client("dm")
    r = admin.post(
        "/api/v1/admin/sla-policies",
        json={
            "name": f"TEST water {world.geo['tag']}",
            "category_id": str(world.geo["category"]),
            "resolution_hours": 48,
        },
    )
    assert r.status_code == 201
    g = register(world.client("deo"), world)
    assert g["due_at"] is not None
    db_session.execute(
        text("UPDATE grievance.grievances SET due_at = now() - interval '1 hour' WHERE id = :i"),
        {"i": g["id"]},
    )
    db_session.commit()
    with db_session.begin():
        result = perf.scan_sla(db_session)
    assert result["breached"] >= 1
    d = detail(dm, g["id"])
    assert d["overdue"] and d["escalation_level"] == 1 and d["escalations"][0]["trigger"] == "sla_breach"
    assert any(e["event_type"] == "breached" for e in d["sla_events"])
    with db_session.begin():
        perf.scan_sla(db_session)  # idempotent: no second escalation
    assert detail(dm, g["id"])["escalation_level"] == 1
    assert db_session.execute(
        select(Notification).where(Notification.user_id == world.users["dm"].id, Notification.category == "escalation")
    ).first()
    assert dm.get("/api/v1/grievances", params={"overdue": True}).json()["total"] >= 1
    r = dm.post(
        f"/api/v1/grievances/{g['id']}/escalate",
        json={"reason": "TEST manual escalation to DM", "version": d["version"]},
    )
    assert r.json()["escalation_level"] == 2


def test_early_warning_alerts_explain_and_require_reasons(world: World, db_session: Session) -> None:
    from app.modules.early_warning import service as ew

    dm = world.client("dm")
    deo = world.client("deo")
    ids = [
        register(
            deo,
            world,
            description=f"TEST DATA overdue item {i} {uuid.uuid4().hex} for backlog check",
        )["id"]
        for i in range(10)
    ]
    db_session.execute(
        text("UPDATE grievance.grievances SET due_at = now() - interval '2 days' WHERE id = ANY(:i)"),
        {"i": [uuid.UUID(x) for x in ids]},
    )
    db_session.commit()
    with db_session.begin():
        ew.evaluate(db_session)
    alerts = dm.get("/api/v1/alerts").json()["items"]
    a = next(
        x for x in alerts if x["alert_type"] == "overdue_backlog" and x["department_id"] == str(world.geo["department"])
    )
    assert a["reasons"] and a["recommended_actions"] and a["risk_model_version"] == 1
    full = dm.get(f"/api/v1/alerts/{a['id']}").json()
    assert set(ids) <= {g["id"] for g in full["grievances"]}
    with db_session.begin():
        ew.evaluate(db_session)  # re-detection updates, no duplicate
    assert len([x for x in dm.get("/api/v1/alerts").json()["items"] if x["id"] == a["id"]]) == 1
    assert dm.post(f"/api/v1/alerts/{a['id']}/actions", json={"action": "dismiss", "reason": "no"}).status_code == 422
    assert (
        dm.post(
            f"/api/v1/alerts/{a['id']}/actions",
            json={"action": "acknowledge", "reason": "TEST seen"},
        ).json()["status"]
        == "acknowledged"
    )
    assert (
        world.client("auditor")
        .post(
            f"/api/v1/alerts/{a['id']}/actions",
            json={"action": "dismiss", "reason": "TEST auditor"},
        )
        .status_code
        == 403
    )
    assert world.client("bdo_b").get(f"/api/v1/alerts/{a['id']}").status_code in (403, 404)
    r = dm.post(
        f"/api/v1/alerts/{a['id']}/actions",
        json={"action": "dismiss", "reason": "TEST backlog reviewed in meeting"},
    )
    assert r.json()["status"] == "dismissed"
    assert [x["action"] for x in dm.get(f"/api/v1/alerts/{a['id']}").json()["actions"]] == [
        "acknowledge",
        "dismiss",
    ]


def test_dashboard_kpis_match_their_filtered_records(world: World) -> None:
    dm = world.client("dm")
    register(world.client("deo"), world)
    kpis = {k["key"]: k for k in dm.get("/api/v1/dashboard/summary").json()["kpis"]}
    for key in ("total", "pending", "overdue", "resolved", "today", "high_risk"):
        params = kpis[key]["filter"]
        listed = dm.get("/api/v1/grievances", params=params).json()["total"]
        assert listed == kpis[key]["value"], key
    assert dm.get("/api/v1/dashboard/trends?granularity=month").status_code == 200
    assert world.client("officer").get("/api/v1/dashboard/summary").status_code == 403


def test_gis_layers_respect_provenance_and_precision(world: World, db_session: Session) -> None:
    ds = db_session.execute(
        text(
            "INSERT INTO ref.boundary_datasets (name, publisher, dataset_version, source_reference, "
            "acquired_on) VALUES (:n, 'pytest', '1', 'TEST synthetic', current_date) RETURNING id"
        ),
        {"n": f"TEST synthetic {world.geo['tag']}"},
    ).scalar_one()
    db_session.execute(
        text(
            "UPDATE ref.blocks SET boundary = 'SRID=4326;MULTIPOLYGON(((80 25,80.1 25,80.1 25.1,80 25.1,80 25)))', "
            "geometry_dataset_id = :ds WHERE id = :b"
        ),
        {"ds": ds, "b": world.geo["block"]},
    )
    db_session.commit()
    register(world.client("deo"), world)
    dm = world.client("dm")
    layer = dm.get("/api/v1/gis/layers/block", params={"district_id": str(world.geo["district"])}).json()
    feat = next(f for f in layer["features"] if f["properties"]["id"] == str(world.geo["block"]))
    assert feat["geometry"]["type"] == "MultiPolygon" and feat["properties"]["total"] >= 1
    assert any(s["name"].startswith("TEST synthetic") for s in layer["sources"])
    assert all(f["properties"]["id"] != str(world.geo["block_b"]) for f in layer["features"])  # no geometry, not drawn
    assert world.client("head").get("/api/v1/gis/layers/village").status_code == 403
    assert dm.get("/api/v1/gis/layers/village").status_code == 200


def test_reports_generate_with_scope_and_pii_controls(world: World, db_session: Session) -> None:
    from openpyxl import load_workbook

    from app.modules.reports import service as reports

    dm, auditor = world.client("dm"), world.client("auditor")
    register(world.client("deo"), world, subject='=HYPERLINK("http://evil")  TEST injection')
    assert (
        auditor.post(
            "/api/v1/reports",
            json={
                "report_type": "grievance_register",
                "format": "xlsx",
                "parameters": {"include_pii": True},
            },
        ).status_code
        == 403
    )
    jobs = {}
    for rtype, fmt, pii in (
        ("grievance_register", "xlsx", True),
        ("executive_summary", "pdf", False),
        ("department_performance", "xlsx", False),
    ):
        r = dm.post(
            "/api/v1/reports",
            json={"report_type": rtype, "format": fmt, "parameters": {"include_pii": pii}},
        )
        assert r.status_code == 202
        jobs[rtype] = r.json()["id"]
        with db_session.begin():
            job = reports.generate(db_session, uuid.UUID(jobs[rtype]))
        assert job.status == "completed", job.error
    dl = dm.get(f"/api/v1/reports/{jobs['grievance_register']}/download")
    assert dl.status_code == 200
    ws = load_workbook(io.BytesIO(dl.content)).active
    values = [c.value for row in ws.iter_rows() for c in row if c.value]
    assert "Complainant mobile" in values and any(str(v).startswith("'=HYPERLINK") for v in values)
    pdf = dm.get(f"/api/v1/reports/{jobs['executive_summary']}/download")
    assert pdf.content.startswith(b"%PDF")
    assert world.client("head").get(f"/api/v1/reports/{jobs['executive_summary']}/download").status_code == 404


def test_performance_endpoints(world: World) -> None:
    head = world.client("head")
    register(world.client("deo"), world)
    rows = head.get("/api/v1/performance/departments").json()
    mine = next(r for r in rows if r["id"] == str(world.geo["department"]))
    assert mine["received"] >= 1 and "sla_compliance_pct" in mine
    assert world.client("officer").get("/api/v1/performance/departments").status_code == 403


def test_history_is_append_only_for_runtime_role(world: World, db_session: Session) -> None:
    gid = register(world.client("deo"), world)["id"]
    n = db_session.execute(
        select(GrievanceStatusHistory).where(GrievanceStatusHistory.grievance_id == uuid.UUID(gid))
    ).all()
    assert len(n) == 1
    with pytest.raises(Exception, match="permission denied"):
        db_session.execute(text("DELETE FROM grievance.grievances WHERE id = :i"), {"i": gid})
    db_session.rollback()


def test_dev_adapter_is_labelled_and_development_only(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Environment, get_settings
    from app.modules.intake.adapters import AdapterError, DevelopmentAdapter

    with pytest.raises(AdapterError):
        DevelopmentAdapter()  # integration tests run with APP_ENV=test
    monkeypatch.setattr(get_settings(), "app_env", Environment.DEVELOPMENT)
    rec = next(DevelopmentAdapter(1).records())
    assert "SYNTHETIC" in rec.description and rec.external_id.startswith("DEV-")


__all__ = ["UTC", "csrf", "datetime", "timedelta"]


def test_cluster_recompute_and_evaluate_endpoint(world: World, db_session: Session) -> None:
    """Regression: recomputing clusters deletes expired ones (needs DELETE grant)."""
    from app.modules.intelligence import service as intel

    deo, dm = world.client("deo"), world.client("dm")
    for i in range(3):
        register(
            deo, world, description=f"TEST DATA cluster member {i} {uuid.uuid4().hex} water problem in the village"
        )
    db_session.execute(
        text(
            "INSERT INTO intel.grievance_clusters (cluster_key, unit_level, unit_id, window_start, "
            "window_end, grievance_count, open_count, method_version) VALUES (:k, 'block', :u, "
            "now() - interval '40 days', now() - interval '20 days', 1, 1, 'test')"
        ),
        {"k": f"TEST-expired-{world.geo['tag']}", "u": world.geo["block"]},
    )
    db_session.commit()
    with db_session.begin():
        assert intel.compute_clusters(db_session) >= 1
    assert (
        db_session.execute(
            text("SELECT count(*) FROM intel.grievance_clusters WHERE cluster_key = :k"),
            {"k": f"TEST-expired-{world.geo['tag']}"},
        ).scalar()
        == 0
    )
    db_session.commit()
    r = dm.post("/api/v1/alerts/evaluate")
    assert r.status_code == 200, r.text
    clusters = dm.get("/api/v1/intelligence/clusters").json()
    assert any(c["unit_id"] == str(world.geo["village"]) for c in clusters)


def test_deferred_malware_scan_holds_files_until_clean(
    world: World, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MALWARE_SCAN_MODE=deferred: upload is pending, undownloadable until the worker marks it clean;
    an infected file is deleted from storage, audited and the uploader notified."""
    from app.core.config import get_settings
    from app.infra import malware, storage
    from app.modules.grievances import service as gsvc
    from app.modules.grievances.models import GrievanceAttachment

    settings = get_settings()
    monkeypatch.setattr(settings, "malware_scanner", "clamav")
    monkeypatch.setattr(settings, "malware_scan_mode", "deferred")
    monkeypatch.setattr(gsvc, "enqueue_attachment_scan", lambda _id: None)  # worker driven explicitly below
    deo = world.client("deo")
    gid = register(deo, world)["id"]

    def upload() -> str:
        r = deo.post(f"/api/v1/grievances/{gid}/attachments", files={"file": ("p.png", PNG, "image/png")})
        assert r.status_code == 201 and r.json()["scan_status"] == "pending", r.text
        return r.json()["id"]

    clean_id, bad_id = upload(), upload()
    assert deo.get(f"/api/v1/grievances/{gid}/attachments/{clean_id}").status_code == 403

    verdicts = {clean_id: malware.ScanResult("clean"), bad_id: malware.ScanResult("infected", "Test-Signature")}
    for att_id, verdict in verdicts.items():
        monkeypatch.setattr(malware, "scan", lambda _data, v=verdict: v)
        with db_session.begin():
            assert gsvc.scan_pending_attachment(db_session, uuid.UUID(att_id)) == verdict.status

    assert deo.get(f"/api/v1/grievances/{gid}/attachments/{clean_id}").content == PNG
    assert deo.get(f"/api/v1/grievances/{gid}/attachments/{bad_id}").status_code == 403
    bad = db_session.get(GrievanceAttachment, uuid.UUID(bad_id))
    assert bad is not None and bad.scan_status == "infected"
    with pytest.raises(Exception, match=r"NoSuchKey|not exist|Not Found"):
        storage.get_bytes(bad.storage_key)
    assert db_session.execute(
        select(Notification).where(Notification.user_id == world.users["deo"].id, Notification.category == "security")
    ).first()
    # Scanner outage keeps the file pending and raises so the task is retried.
    db_session.commit()
    third = upload()
    monkeypatch.setattr(malware, "scan", lambda _d: malware.ScanResult("error", "down"))
    with pytest.raises(RuntimeError), db_session.begin():
        gsvc.scan_pending_attachment(db_session, uuid.UUID(third))
    db_session.expire_all()
    third_row = db_session.get(GrievanceAttachment, uuid.UUID(third))
    assert third_row is not None and third_row.scan_status == "pending"
