"""DEVELOPMENT-ONLY synthetic demonstration data.

    python -m app.cli load-demo-data

Refuses to run unless APP_ENV=development. Everything created is labelled as
synthetic: the district is "Demo District (synthetic)", geometry is a grid of squares
at 0°N 0°E (open ocean, so it cannot be mistaken for a real place) registered under
a dataset named "SYNTHETIC DEMO GEOMETRY - NOT REAL BOUNDARIES", every grievance
subject starts with "[DEMO]", departments/categories/SLA policies carry "(demo)".
Demo grievances are created through the real service layer, so histories, SLA
events, AI suggestions, risk assessments and alerts are produced by the actual code.
"""

from __future__ import annotations

import os
import random
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core import security
from app.core.config import Environment, get_settings
from app.db.session import get_session_factory
from app.modules.administration.models import Department, GrievanceSource, IssueCategory
from app.modules.geography.models import (
    Block,
    BoundaryDataset,
    District,
    GramPanchayat,
    Municipality,
    Subdivision,
    Village,
    Ward,
)
from app.modules.iam.models import MfaCredential, Role, User, UserRole, UserScopeAssignment
from app.modules.intelligence.models import ClassificationRule
from app.modules.performance.models import SlaPolicy

DEMO_DISTRICT = "Demo District (synthetic)"


def _square(x: float, y: float, size: float) -> str:
    return f"SRID=4326;MULTIPOLYGON((({x} {y},{x + size} {y},{x + size} {y + size},{x} {y + size},{x} {y})))"


def load_demo_data() -> int:
    settings = get_settings()
    if settings.app_env != Environment.DEVELOPMENT:
        print("Refusing: demo data may only be loaded when APP_ENV=development.")
        return 2
    rng = random.Random(20261031)  # noqa: S311 - deterministic synthetic data, not security
    password = os.environ.get("DGI_DEMO_PASSWORD") or ("Demo-" + secrets.token_urlsafe(9) + "-9a")
    with get_session_factory()() as db, db.begin():
        if db.execute(select(District.id).where(District.name_en == DEMO_DISTRICT)).first():
            print("Demo data already loaded.")
            return 0
        ds = BoundaryDataset(
            name="SYNTHETIC DEMO GEOMETRY - NOT REAL BOUNDARIES",
            publisher="DG-IMEWS development fixture",
            dataset_version="demo-1",
            source_reference="app/demo.py (generated)",
            acquired_on=date.today(),
            verification_notes="Synthetic squares at 0N 0E for demonstration only.",
        )
        db.add(ds)
        db.flush()
        district = District(
            name_en=DEMO_DISTRICT,
            name_local="डेमो ज़िला (कृत्रिम)",
            state_name_en="Demo State (synthetic)",
            boundary=_square(0, 0, 1.0),
            geometry_dataset_id=ds.id,
        )
        db.add(district)
        db.flush()
        subs = [Subdivision(name_en=f"Demo Subdivision {n}", district_id=district.id) for n in ("North", "South")]
        db.add_all(subs)
        db.flush()
        blocks, gps, villages = [], [], []
        block_names = ["Amritpur", "Bhimnagar", "Chandganj", "Devgarh"]
        village_names = iter(
            [
                "Kesarpur",
                "Lalpura",
                "Madhoganj",
                "Nayagaon",
                "Oriyapur",
                "Palasi",
                "Ramnagar",
                "Sitapura",
                "Tilakpur",
                "Udaypur Khurd",
                "Vishnupura",
                "Yashpur",
                "Zorawarganj",
                "Gopalpur",
                "Harinagar",
                "Indrapuri",
            ]
        )
        for i, name in enumerate(block_names):
            bx, by = (i % 2) * 0.5, (i // 2) * 0.5
            b = Block(
                name_en=f"{name} (demo)",
                district_id=district.id,
                subdivision_id=subs[i // 2].id,
                boundary=_square(bx, by, 0.5),
                geometry_dataset_id=ds.id,
            )
            db.add(b)
            db.flush()
            blocks.append(b)
            for j in range(2):
                gp = GramPanchayat(
                    name_en=f"{name} GP {j + 1} (demo)",
                    block_id=b.id,
                    boundary=_square(bx + j * 0.25, by, 0.25),
                    geometry_dataset_id=ds.id,
                )
                db.add(gp)
                db.flush()
                gps.append(gp)
                for k in range(2):
                    vx, vy = bx + j * 0.25 + k * 0.125, by + 0.125
                    v = Village(
                        name_en=next(village_names),
                        district_id=district.id,
                        subdivision_id=subs[i // 2].id,
                        block_id=b.id,
                        gram_panchayat_id=gp.id,
                        boundary=_square(vx, by, 0.125),
                        location=f"SRID=4326;POINT({vx + 0.06} {vy})",
                        geometry_dataset_id=ds.id,
                    )
                    db.add(v)
                    villages.append(v)
        db.flush()
        muni = Municipality(
            name_en="Demo Nagar Palika (synthetic)", district_id=district.id, body_type="municipal_council"
        )
        db.add(muni)
        db.flush()
        for w in ("1", "2", "3"):
            db.add(Ward(name_en=f"Ward {w}", ward_number=w, municipality_id=muni.id))

        deps = {
            code: Department(code=code, name_en=name)
            for code, name in (
                ("DEMO_WATER", "Water Supply (demo)"),
                ("DEMO_ROADS", "Public Works - Roads (demo)"),
                ("DEMO_POWER", "Electricity Distribution (demo)"),
                ("DEMO_HEALTH", "Health Services (demo)"),
                ("DEMO_REVENUE", "Revenue (demo)"),
            )
        }
        db.add_all(deps.values())
        db.flush()
        cat_spec = [
            (
                "DEMO_WATER_SUPPLY",
                "Drinking water supply (demo)",
                "DEMO_WATER",
                True,
                ["water", "hand pump", "pipeline", "tap", "tanker"],
            ),
            ("DEMO_ROADS", "Roads and bridges (demo)", "DEMO_ROADS", False, ["road", "pothole", "bridge", "culvert"]),
            (
                "DEMO_ELECTRICITY",
                "Electricity supply (demo)",
                "DEMO_POWER",
                True,
                ["electricity", "transformer", "power cut", "voltage"],
            ),
            (
                "DEMO_HEALTH",
                "Health services (demo)",
                "DEMO_HEALTH",
                True,
                ["hospital", "doctor", "medicine", "ambulance"],
            ),
            (
                "DEMO_LAND",
                "Land records (demo)",
                "DEMO_REVENUE",
                False,
                ["land record", "mutation", "khatauni", "boundary dispute"],
            ),
        ]
        cats: dict[str, IssueCategory] = {}
        for code, name, dep, essential, keywords in cat_spec:
            c = IssueCategory(
                code=code, name_en=name, default_department_id=deps[dep].id, is_essential_service=essential
            )
            db.add(c)
            db.flush()
            cats[code] = c
            for kw in keywords:
                db.add(ClassificationRule(category_id=c.id, keyword=kw, weight=1))
        for name, cat, prio, hours in (
            ("Demo: urgent grievances (not official)", None, "urgent", 48),
            ("Demo: drinking water (not official)", "DEMO_WATER_SUPPLY", None, 72),
            ("Demo: electricity (not official)", "DEMO_ELECTRICITY", None, 72),
            ("Demo: default (not official)", None, None, 240),
        ):
            db.add(
                SlaPolicy(
                    name=name,
                    category_id=cats[cat].id if cat else None,
                    priority=prio,
                    resolution_hours=hours,
                    legal_reference="Synthetic demonstration value",
                )
            )
        db.flush()

        roles = {r[0]: r[1] for r in db.execute(select(Role.code, Role.id)).all()}
        users: dict[str, User] = {}

        def make(
            username: str, full_name: str, role: str, scopes: list[dict[str, Any]], dep: str | None = None
        ) -> None:
            u = User(
                username=username,
                full_name=full_name,
                designation=f"{full_name} (demo account)",
                password_hash=security.hash_password(password),
                must_change_password=False,
                department_id=deps[dep].id if dep else None,
            )
            db.add(u)
            db.flush()
            db.add(UserRole(user_id=u.id, role_id=roles[role]))
            for s in scopes:
                db.add(UserScopeAssignment(user_id=u.id, **s))
            users[username] = u

        dsc = [{"scope_type": "district", "district_id": district.id}]
        make("demo.admin", "Demo System Administrator", "super_admin", [])
        make("demo.dm", "Demo District Magistrate", "district_magistrate", dsc)
        make("demo.adm", "Demo Additional District Magistrate", "additional_district_magistrate", dsc)
        make(
            "demo.sdo",
            "Demo Sub-Divisional Officer (North)",
            "sub_divisional_officer",
            [{"scope_type": "subdivision", "subdivision_id": subs[0].id}],
        )
        make(
            "demo.bdo",
            "Demo BDO Amritpur",
            "block_development_officer",
            [{"scope_type": "block", "block_id": blocks[0].id}],
        )
        for dep in ("DEMO_WATER", "DEMO_ROADS", "DEMO_POWER", "DEMO_HEALTH", "DEMO_REVENUE"):
            short = dep.split("_")[1].lower()
            make(
                f"demo.head.{short}",
                f"Demo Head - {deps[dep].name_en}",
                "department_head",
                [{"scope_type": "department", "department_id": deps[dep].id}],
                dep,
            )
            for n in (1, 2):
                make(
                    f"demo.officer.{short}{n}",
                    f"Demo Officer {n} - {deps[dep].name_en}",
                    "department_officer",
                    [{"scope_type": "assigned"}],
                    dep,
                )
        make("demo.deo", "Demo Data Entry Operator", "data_entry_operator", [{"scope_type": "own"}])
        make("demo.auditor", "Demo Auditor", "auditor", dsc)
        totp: dict[str, str] = {}
        for uname in ("demo.admin", "demo.dm", "demo.adm", "demo.auditor"):
            secret = security.new_totp_secret()
            db.add(
                MfaCredential(
                    user_id=users[uname].id,
                    secret_encrypted=security.encrypt_text(secret) or "",
                    confirmed_at=datetime.now(UTC),
                )
            )
            totp[uname] = secret
        db.flush()
        district_id = district.id
        village_ids = [v.id for v in villages]
        cat_ids = {k: v.id for k, v in cats.items()}
        dep_users = {
            dep.split("_")[1].lower(): [users[f"demo.officer.{dep.split('_')[1].lower()}{n}"].id for n in (1, 2)]
            for dep in deps
        }
        user_ids = {k: v.id for k, v in users.items()}
        _create_demo_grievances(db, rng, district_id, village_ids, cat_ids, dep_users, user_ids)
    print("\n=== DEMO DATA LOADED (synthetic, development only) ===")
    print(f"Password for every demo.* account: {password}")
    print("Accounts: demo.dm, demo.adm, demo.sdo, demo.bdo, demo.head.<water|roads|power|health|revenue>,")
    print("          demo.officer.<dept><1|2>, demo.deo, demo.auditor, demo.admin")
    print("MFA is required for demo.admin, demo.dm, demo.adm and demo.auditor. Either add these TOTP secrets to an")
    print("authenticator app, or get the current code with:  python -m app.cli demo-totp <username>")
    for account, secret_value in totp.items():
        print(f"  {account}: {secret_value}")
    return 0


TEMPLATES = {
    "DEMO_WATER_SUPPLY": [
        (
            "No drinking water for {d} days",
            "The hand pump near the primary school in {v} has stopped working. "
            "Residents fetch water from far away. Please repair the pump.",
        ),
        (
            "Pipeline leakage",
            "The water pipeline in {v} is leaking near the market and the tap supply is irregular for {d} days.",
        ),
    ],
    "DEMO_ROADS": [
        ("Pothole on main road", "Large pothole on the main road of {v} is causing accidents for two-wheelers."),
        ("Culvert damaged", "The culvert on the road from {v} to the block office is broken after rain."),
    ],
    "DEMO_ELECTRICITY": [
        ("Transformer failure", "The transformer serving {v} burnt out {d} days ago; no electricity since."),
        ("Low voltage", "Low voltage and frequent power cut in {v} in the evenings."),
    ],
    "DEMO_HEALTH": [
        ("Doctor absent", "The doctor at the health sub-centre near {v} has been absent for {d} days."),
        ("No medicine stock", "Essential medicine not available at the hospital serving {v}."),
    ],
    "DEMO_LAND": [
        ("Mutation pending", "Mutation of land record for a plot in {v} is pending for months."),
        ("Boundary dispute", "Boundary dispute between neighbours in {v} needs measurement by the revenue staff."),
    ],
}


def _create_demo_grievances(
    db: Any,
    rng: random.Random,
    district_id: uuid.UUID,
    village_ids: list[uuid.UUID],
    cat_ids: dict[str, uuid.UUID],
    dep_users: dict[str, list[uuid.UUID]],
    user_ids: dict[str, uuid.UUID],
) -> None:
    from app.core.request_meta import RequestMeta
    from app.modules.grievances import service as gsvc
    from app.modules.iam.service import user_context
    from app.modules.intelligence import service as intel
    from app.modules.performance import service as perf

    meta = RequestMeta.system()
    real_now = gsvc.now
    dep_for_cat = {
        "DEMO_WATER_SUPPLY": "water",
        "DEMO_ROADS": "roads",
        "DEMO_ELECTRICITY": "power",
        "DEMO_HEALTH": "health",
        "DEMO_LAND": "revenue",
    }
    created: list[uuid.UUID] = []
    hotspot = village_ids[0]
    sources = list(db.execute(select(GrievanceSource.id)).scalars())
    vnames = {r[0]: r[1] for r in db.execute(select(Village.id, Village.name_en)).all()}
    deo, dm = user_context(db, user_ids["demo.deo"]), user_context(db, user_ids["demo.dm"])
    plan: list[tuple[int, str, uuid.UUID]] = []
    for _ in range(110):
        plan.append((rng.randint(1, 90), rng.choice(list(cat_ids)), rng.choice(village_ids)))
    for _ in range(9):  # an emerging cluster: recent water complaints in one village
        plan.append((rng.randint(0, 6), "DEMO_WATER_SUPPLY", hotspot))
    for days_ago, cat, village in sorted(plan, key=lambda p: -p[0]):
        when = real_now() - timedelta(days=days_ago, hours=rng.randint(0, 20))
        gsvc.now = perf.now = lambda w=when: w  # type: ignore[misc]  # backdate registration (demo only)
        subject, body = rng.choice(TEMPLATES[cat])
        g = gsvc.register(
            db,
            deo,
            source_id=rng.choice(sources),
            subject=f"[DEMO] {subject.format(d=rng.randint(2, 9))}",
            description="[SYNTHETIC DEMO RECORD] " + body.format(v=vnames[village], d=rng.randint(2, 9)),
            received_at=when,
            category_id=cat_ids[cat] if rng.random() > 0.2 else None,
            subcategory_id=None,
            department_id=None,
            priority=rng.choices(["low", "normal", "high", "urgent"], [2, 6, 3, 1])[0],
            location=gsvc.LocationInput(village_id=village),
            location_text=None,
            complainant=gsvc.ComplainantInput(
                name="Synthetic Demo Person", mobile=f"90000{rng.randint(10000, 99999)}", consent_recorded=True
            ),
            meta=meta,
        )
        gsvc.now = perf.now = real_now
        created.append(g.id)
        # Backdate each workflow step after registration so trends look realistic (demo only).
        step_time = [when]

        def later(hours_min: int = 6, hours_max: int = 96, st: list[datetime] = step_time) -> None:
            st[0] = min(st[0] + timedelta(hours=rng.randint(hours_min, hours_max)), real_now())
            gsvc.now = perf.now = lambda w=st[0]: w  # type: ignore[misc]

        dept = dep_for_cat[cat]
        roll = rng.random()
        if days_ago < 1 or roll < 0.15:
            gsvc.now = perf.now = real_now
            continue
        officer_id = rng.choice(dep_users[dept])
        officer = user_context(db, officer_id)
        later()
        gsvc.assign(db, dm, g.id, officer_id, g.version, "Demo assignment", meta)
        if roll < 0.3:
            continue
        later()
        gsvc.transition(db, officer, g.id, "start_work", g.version, None, meta)
        if roll < 0.5:
            continue
        later()
        gsvc.transition(
            db, officer, g.id, "submit_resolution", g.version, "Demo: action taken and reported by officer.", meta
        )
        if roll < 0.6:
            continue
        later()
        gsvc.transition(db, dm, g.id, "accept_resolution", g.version, "Demo verification", meta)
        later()
        if roll < 0.9:
            gsvc.transition(db, dm, g.id, "close", g.version, None, meta)
        elif roll < 0.95:
            gsvc.transition(db, dm, g.id, "reopen", g.version, "Demo: complainant reports the problem persists.", meta)
    gsvc.now = perf.now = real_now
    db.flush()
    for gid in created:
        intel.analyse(db, gid)
    perf.scan_sla(db)
    from app.modules.early_warning import service as ew

    intel.compute_clusters(db)
    intel.assess_all_open(db)
    ew.evaluate(db)
    perf.take_snapshots(db)
    _ = district_id


def demo_totp(username: str) -> int:
    if get_settings().app_env != Environment.DEVELOPMENT:
        print("Refusing: development only.")
        return 2
    import pyotp

    with get_session_factory()() as db:
        cred = db.execute(
            select(MfaCredential)
            .join(User, User.id == MfaCredential.user_id)
            .where(
                User.username == username,
                User.username.startswith("demo."),
                MfaCredential.revoked_at.is_(None),
                MfaCredential.confirmed_at.is_not(None),
            )
        ).scalar_one_or_none()
        if cred is None:
            print("No demo MFA credential for that user.")
            return 1
        print(pyotp.TOTP(security.decrypt_text(cred.secret_encrypted) or "").now())
    return 0
