"""Permission catalogue and role definitions.

The roles are the nine named in the project specification. The role-to-permission
mapping below is the *initial* proposal for approval by the district administration;
it is loaded by migration 0004 and can be revised by a later migration.
A test asserts the database matches this module.

Design rules encoded here:
* Super Administrator manages users and configuration but holds NO grievance or
  citizen-data permissions (separation from citizen data).
* Auditor holds read-only permissions only (no permission whose code implies a write).
* ``citizen.read`` (complainant personal data) is held only by roles that act on
  grievances; everyone else sees masked values.
"""

from __future__ import annotations

PERMISSIONS: dict[str, str] = {
    # Grievances
    "grievance.read": "View grievances within scope",
    "grievance.create": "Register grievances",
    "grievance.update": "Edit grievance classification, priority and location",
    "grievance.assign": "Assign or reassign grievances",
    "grievance.work": "Start work and submit resolutions on assigned grievances",
    "grievance.verify": "Verify or return submitted resolutions; close grievances",
    "grievance.reopen": "Reopen resolved or closed grievances",
    "grievance.escalate": "Escalate grievances",
    "grievance.comment": "Add comments and investigation notes",
    "grievance.attach": "Upload attachments",
    "grievance.link": "Link related or duplicate grievances",
    "grievance.import": "Import grievances from authorised source files",
    "citizen.read": "View complainant personal information",
    # Intelligence
    "ai.read": "View AI suggestions, clusters and risk assessments",
    "ai.review": "Accept, edit or reject AI suggestions and duplicate candidates",
    "alert.read": "View early-warning alerts",
    "alert.act": "Acknowledge, investigate, escalate or dismiss alerts",
    "gis.read": "View maps aggregated to block level",
    "gis.read_precise": "View maps at village/ward precision",
    # Performance and reporting
    "dashboard.read": "View the command dashboard",
    "performance.read": "View department and block performance",
    "report.generate": "Generate reports",
    "report.export": "Download generated reports",
    # Administration
    "config.manage": "Manage departments, categories, sources, geography, SLA and risk settings",
    "iam.users.read": "View user accounts",
    "iam.users.manage": "Create and manage user accounts, roles and scopes",
    "audit.read": "View audit logs",
    "system.read": "View system status",
}

SENSITIVE_PERMISSIONS = {"citizen.read", "iam.users.manage", "config.manage", "audit.read"}

_GRIEVANCE_OFFICER = [
    "grievance.read",
    "grievance.update",
    "grievance.assign",
    "grievance.work",
    "grievance.verify",
    "grievance.reopen",
    "grievance.escalate",
    "grievance.comment",
    "grievance.attach",
    "grievance.link",
    "citizen.read",
    "ai.read",
    "ai.review",
    "alert.read",
    "alert.act",
    "gis.read",
    "dashboard.read",
    "performance.read",
    "report.generate",
    "report.export",
    "system.read",
]

ROLES: dict[str, dict[str, object]] = {
    "super_admin": {
        "name": "Super Administrator",
        "rank": 10,
        "permissions": [
            "iam.users.read",
            "iam.users.manage",
            "config.manage",
            "audit.read",
            "system.read",
        ],
    },
    "district_magistrate": {
        "name": "District Magistrate",
        "rank": 20,
        "permissions": [
            *_GRIEVANCE_OFFICER,
            "gis.read_precise",
            "grievance.create",
            "audit.read",
            "iam.users.read",
        ],
    },
    "additional_district_magistrate": {
        "name": "Additional District Magistrate",
        "rank": 30,
        "permissions": [
            *_GRIEVANCE_OFFICER,
            "gis.read_precise",
            "grievance.create",
            "iam.users.read",
        ],
    },
    "sub_divisional_officer": {
        "name": "Sub-Divisional Officer",
        "rank": 40,
        "permissions": [*_GRIEVANCE_OFFICER, "gis.read_precise"],
    },
    "block_development_officer": {
        "name": "Block Development Officer",
        "rank": 50,
        "permissions": [*_GRIEVANCE_OFFICER, "gis.read_precise"],
    },
    "department_head": {
        "name": "Department Head",
        "rank": 60,
        "permissions": [p for p in _GRIEVANCE_OFFICER if p != "grievance.reopen"],
    },
    "department_officer": {
        "name": "Department Officer",
        "rank": 70,
        "permissions": [
            "grievance.read",
            "grievance.work",
            "grievance.comment",
            "grievance.attach",
            "citizen.read",
            "ai.read",
            "system.read",
        ],
    },
    "data_entry_operator": {
        "name": "Data Entry Operator",
        "rank": 80,
        "permissions": [
            "grievance.read",
            "grievance.create",
            "grievance.comment",
            "grievance.attach",
            "grievance.import",
            "system.read",
        ],
    },
    "auditor": {
        "name": "Read-only Auditor",
        "rank": 90,
        "permissions": [
            "grievance.read",
            "ai.read",
            "alert.read",
            "gis.read",
            "dashboard.read",
            "performance.read",
            "audit.read",
            "iam.users.read",
            "system.read",
        ],
    },
}

READ_ONLY_PERMISSIONS = {p for p in PERMISSIONS if p.endswith((".read", ".read_precise"))}
