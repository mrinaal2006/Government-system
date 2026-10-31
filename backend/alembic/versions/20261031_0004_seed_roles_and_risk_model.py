"""Seed the specified roles, the permission catalogue and a PROVISIONAL risk model.

Revision ID: 0004_seed_roles_and_risk_model
Revises: 0003_operational_schemas
Create Date: 2026-10-31

* Roles are the nine named in the specification. The permission mapping is the
  initial proposal (see app/modules/iam/catalogue.py) awaiting administrative approval.
* Risk model version 1 is marked ``is_provisional``: its weights and thresholds are
  starting values to be reviewed and approved by the District Magistrate before use
  in decisions. They are not derived from any official policy.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_seed_roles_and_risk_model"
down_revision: str | None = "0003_operational_schemas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = [
    ("super_admin", "Super Administrator", 10),
    ("district_magistrate", "District Magistrate", 20),
    ("additional_district_magistrate", "Additional District Magistrate", 30),
    ("sub_divisional_officer", "Sub-Divisional Officer", 40),
    ("block_development_officer", "Block Development Officer", 50),
    ("department_head", "Department Head", 60),
    ("department_officer", "Department Officer", 70),
    ("data_entry_operator", "Data Entry Operator", 80),
    ("auditor", "Read-only Auditor", 90),
]
PERMISSIONS = [
    ("grievance.read", "View grievances within scope", False),
    ("grievance.create", "Register grievances", False),
    ("grievance.update", "Edit grievance classification, priority and location", False),
    ("grievance.assign", "Assign or reassign grievances", False),
    ("grievance.work", "Start work and submit resolutions on assigned grievances", False),
    ("grievance.verify", "Verify or return submitted resolutions; close grievances", False),
    ("grievance.reopen", "Reopen resolved or closed grievances", False),
    ("grievance.escalate", "Escalate grievances", False),
    ("grievance.comment", "Add comments and investigation notes", False),
    ("grievance.attach", "Upload attachments", False),
    ("grievance.link", "Link related or duplicate grievances", False),
    ("grievance.import", "Import grievances from authorised source files", False),
    ("citizen.read", "View complainant personal information", True),
    ("ai.read", "View AI suggestions, clusters and risk assessments", False),
    ("ai.review", "Accept, edit or reject AI suggestions and duplicate candidates", False),
    ("alert.read", "View early-warning alerts", False),
    ("alert.act", "Acknowledge, investigate, escalate or dismiss alerts", False),
    ("gis.read", "View maps aggregated to block level", False),
    ("gis.read_precise", "View maps at village/ward precision", False),
    ("dashboard.read", "View the command dashboard", False),
    ("performance.read", "View department and block performance", False),
    ("report.generate", "Generate reports", False),
    ("report.export", "Download generated reports", False),
    (
        "config.manage",
        "Manage departments, categories, sources, geography, SLA and risk settings",
        True,
    ),
    ("iam.users.read", "View user accounts", False),
    ("iam.users.manage", "Create and manage user accounts, roles and scopes", True),
    ("audit.read", "View audit logs", True),
    ("system.read", "View system status", False),
]
ROLE_PERMISSIONS = [
    ("super_admin", "iam.users.read"),
    ("super_admin", "iam.users.manage"),
    ("super_admin", "config.manage"),
    ("super_admin", "audit.read"),
    ("super_admin", "system.read"),
    ("district_magistrate", "grievance.read"),
    ("district_magistrate", "grievance.update"),
    ("district_magistrate", "grievance.assign"),
    ("district_magistrate", "grievance.work"),
    ("district_magistrate", "grievance.verify"),
    ("district_magistrate", "grievance.reopen"),
    ("district_magistrate", "grievance.escalate"),
    ("district_magistrate", "grievance.comment"),
    ("district_magistrate", "grievance.attach"),
    ("district_magistrate", "grievance.link"),
    ("district_magistrate", "citizen.read"),
    ("district_magistrate", "ai.read"),
    ("district_magistrate", "ai.review"),
    ("district_magistrate", "alert.read"),
    ("district_magistrate", "alert.act"),
    ("district_magistrate", "gis.read"),
    ("district_magistrate", "dashboard.read"),
    ("district_magistrate", "performance.read"),
    ("district_magistrate", "report.generate"),
    ("district_magistrate", "report.export"),
    ("district_magistrate", "system.read"),
    ("district_magistrate", "gis.read_precise"),
    ("district_magistrate", "grievance.create"),
    ("district_magistrate", "audit.read"),
    ("district_magistrate", "iam.users.read"),
    ("additional_district_magistrate", "grievance.read"),
    ("additional_district_magistrate", "grievance.update"),
    ("additional_district_magistrate", "grievance.assign"),
    ("additional_district_magistrate", "grievance.work"),
    ("additional_district_magistrate", "grievance.verify"),
    ("additional_district_magistrate", "grievance.reopen"),
    ("additional_district_magistrate", "grievance.escalate"),
    ("additional_district_magistrate", "grievance.comment"),
    ("additional_district_magistrate", "grievance.attach"),
    ("additional_district_magistrate", "grievance.link"),
    ("additional_district_magistrate", "citizen.read"),
    ("additional_district_magistrate", "ai.read"),
    ("additional_district_magistrate", "ai.review"),
    ("additional_district_magistrate", "alert.read"),
    ("additional_district_magistrate", "alert.act"),
    ("additional_district_magistrate", "gis.read"),
    ("additional_district_magistrate", "dashboard.read"),
    ("additional_district_magistrate", "performance.read"),
    ("additional_district_magistrate", "report.generate"),
    ("additional_district_magistrate", "report.export"),
    ("additional_district_magistrate", "system.read"),
    ("additional_district_magistrate", "gis.read_precise"),
    ("additional_district_magistrate", "grievance.create"),
    ("additional_district_magistrate", "iam.users.read"),
    ("sub_divisional_officer", "grievance.read"),
    ("sub_divisional_officer", "grievance.update"),
    ("sub_divisional_officer", "grievance.assign"),
    ("sub_divisional_officer", "grievance.work"),
    ("sub_divisional_officer", "grievance.verify"),
    ("sub_divisional_officer", "grievance.reopen"),
    ("sub_divisional_officer", "grievance.escalate"),
    ("sub_divisional_officer", "grievance.comment"),
    ("sub_divisional_officer", "grievance.attach"),
    ("sub_divisional_officer", "grievance.link"),
    ("sub_divisional_officer", "citizen.read"),
    ("sub_divisional_officer", "ai.read"),
    ("sub_divisional_officer", "ai.review"),
    ("sub_divisional_officer", "alert.read"),
    ("sub_divisional_officer", "alert.act"),
    ("sub_divisional_officer", "gis.read"),
    ("sub_divisional_officer", "dashboard.read"),
    ("sub_divisional_officer", "performance.read"),
    ("sub_divisional_officer", "report.generate"),
    ("sub_divisional_officer", "report.export"),
    ("sub_divisional_officer", "system.read"),
    ("sub_divisional_officer", "gis.read_precise"),
    ("block_development_officer", "grievance.read"),
    ("block_development_officer", "grievance.update"),
    ("block_development_officer", "grievance.assign"),
    ("block_development_officer", "grievance.work"),
    ("block_development_officer", "grievance.verify"),
    ("block_development_officer", "grievance.reopen"),
    ("block_development_officer", "grievance.escalate"),
    ("block_development_officer", "grievance.comment"),
    ("block_development_officer", "grievance.attach"),
    ("block_development_officer", "grievance.link"),
    ("block_development_officer", "citizen.read"),
    ("block_development_officer", "ai.read"),
    ("block_development_officer", "ai.review"),
    ("block_development_officer", "alert.read"),
    ("block_development_officer", "alert.act"),
    ("block_development_officer", "gis.read"),
    ("block_development_officer", "dashboard.read"),
    ("block_development_officer", "performance.read"),
    ("block_development_officer", "report.generate"),
    ("block_development_officer", "report.export"),
    ("block_development_officer", "system.read"),
    ("block_development_officer", "gis.read_precise"),
    ("department_head", "grievance.read"),
    ("department_head", "grievance.update"),
    ("department_head", "grievance.assign"),
    ("department_head", "grievance.work"),
    ("department_head", "grievance.verify"),
    ("department_head", "grievance.escalate"),
    ("department_head", "grievance.comment"),
    ("department_head", "grievance.attach"),
    ("department_head", "grievance.link"),
    ("department_head", "citizen.read"),
    ("department_head", "ai.read"),
    ("department_head", "ai.review"),
    ("department_head", "alert.read"),
    ("department_head", "alert.act"),
    ("department_head", "gis.read"),
    ("department_head", "dashboard.read"),
    ("department_head", "performance.read"),
    ("department_head", "report.generate"),
    ("department_head", "report.export"),
    ("department_head", "system.read"),
    ("department_officer", "grievance.read"),
    ("department_officer", "grievance.work"),
    ("department_officer", "grievance.comment"),
    ("department_officer", "grievance.attach"),
    ("department_officer", "citizen.read"),
    ("department_officer", "ai.read"),
    ("department_officer", "system.read"),
    ("data_entry_operator", "grievance.read"),
    ("data_entry_operator", "grievance.create"),
    ("data_entry_operator", "grievance.comment"),
    ("data_entry_operator", "grievance.attach"),
    ("data_entry_operator", "grievance.import"),
    ("data_entry_operator", "system.read"),
    ("auditor", "grievance.read"),
    ("auditor", "ai.read"),
    ("auditor", "alert.read"),
    ("auditor", "gis.read"),
    ("auditor", "dashboard.read"),
    ("auditor", "performance.read"),
    ("auditor", "audit.read"),
    ("auditor", "iam.users.read"),
    ("auditor", "system.read"),
]
RISK_MODEL_V1 = {
    "risk_factors": {
        "overdue": 30,
        "overdue_per_day": 1,
        "overdue_per_day_cap": 20,
        "reopened_each": 15,
        "reopened_cap": 30,
        "escalation_level_each": 10,
        "escalation_cap": 30,
        "essential_service": 15,
        "in_cluster": 10,
        "priority_urgent": 10,
        "priority_high": 5,
    },
    "levels": {"watch": 25, "high": 50, "critical": 75},
    "alerts": {
        "overdue_backlog": {"min_overdue": 10, "high": 25, "critical": 50},
        "repeated_unresolved": {"min_reopened": 2, "high": 3},
        "area_concentration": {"window_days": 14, "min_count": 5, "high": 10, "critical": 20},
        "essential_service": {"window_days": 7, "min_count": 3, "critical": 10},
        "escalation_history": {"window_days": 30, "min_escalations": 3, "high": 6},
        "volume_spike": {
            "recent_days": 7,
            "baseline_weeks": 4,
            "min_count": 5,
            "ratio": 2.0,
            "critical_ratio": 3.0,
        },
    },
    "cluster": {"window_days": 14, "min_count": 3},
    "duplicate": {"similarity_threshold": 0.55, "window_days": 30},
    "recommended_actions": {
        "overdue_backlog": [
            "Review overdue grievances with the department head",
            "Confirm officer availability and reassign where needed",
            "Set a review date for clearing the backlog",
        ],
        "repeated_unresolved": [
            "Order a field verification of the reported resolution",
            "Review the resolution evidence before closure",
        ],
        "area_concentration": [
            "Arrange a site inspection in the affected area",
            "Coordinate the responsible departments for a joint review",
        ],
        "essential_service": [
            "Confirm service restoration status with the department",
            "Consider a public communication on expected restoration",
        ],
        "escalation_history": [
            "Review the escalation chain and pending decisions",
            "Hold a review meeting with the concerned officers",
        ],
        "volume_spike": [
            "Verify whether the increase reflects a new underlying problem",
            "Ask the department for a situation report",
        ],
    },
}


def upgrade() -> None:
    bind = op.get_bind()
    for code, name, rank in ROLES:
        bind.execute(
            sa.text("INSERT INTO iam.roles (code, name, rank) VALUES (:c, :n, :r) ON CONFLICT (code) DO NOTHING"),
            {"c": code, "n": name, "r": rank},
        )
    for code, desc, sensitive in PERMISSIONS:
        bind.execute(
            sa.text(
                "INSERT INTO iam.permissions (code, description, is_sensitive) VALUES (:c, :d, :s) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"c": code, "d": desc, "s": sensitive},
        )
    for role, perm in ROLE_PERMISSIONS:
        bind.execute(
            sa.text(
                "INSERT INTO iam.role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM iam.roles r, iam.permissions p WHERE r.code = :r AND p.code = :p "
                "ON CONFLICT DO NOTHING"
            ),
            {"r": role, "p": perm},
        )
    bind.execute(
        sa.text(
            "INSERT INTO intel.risk_models (version, parameters, is_active, is_provisional, notes) "
            "VALUES (1, CAST(:p AS jsonb), true, true, :n)"
        ),
        {
            "p": __import__("json").dumps(RISK_MODEL_V1),
            "n": "Provisional starting values; require review and approval by the District Magistrate.",
        },
    )


def downgrade() -> None:
    op.execute("DELETE FROM intel.risk_models WHERE version = 1")
    op.execute("DELETE FROM iam.user_roles")
    op.execute("DELETE FROM iam.role_permissions")
    op.execute("DELETE FROM iam.permissions")
    op.execute("DELETE FROM iam.roles")
