"""Resource scope predicates.

A user may see a grievance if ANY of their scope assignments matches it. Users
with no scope assignments see nothing (deny by default). These predicates are
added to every grievance query in SQL, so out-of-scope rows are never loaded.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, false, or_

from app.modules.grievances.models import Grievance
from app.modules.iam.service import CurrentUser


def grievance_scope(user: CurrentUser) -> ColumnElement[bool]:
    clauses: list[ColumnElement[bool]] = []
    for s in user.scopes:
        if s.scope_type == "district" and s.district_id:
            clauses.append(Grievance.district_id == s.district_id)
        elif s.scope_type == "subdivision" and s.subdivision_id:
            clauses.append(Grievance.subdivision_id == s.subdivision_id)
        elif s.scope_type == "block" and s.block_id:
            clauses.append(Grievance.block_id == s.block_id)
        elif s.scope_type == "department" and s.department_id:
            clauses.append(Grievance.department_id == s.department_id)
        elif s.scope_type == "assigned":
            clauses.append(Grievance.assigned_officer_id == user.id)
        elif s.scope_type == "own":
            clauses.append(Grievance.created_by == user.id)
    return or_(*clauses) if clauses else false()


def unit_scope_ids(user: CurrentUser) -> dict[str, set[object]]:
    """Administrative units the user is scoped to (for alerts and maps)."""
    out: dict[str, set[object]] = {
        "district": set(),
        "subdivision": set(),
        "block": set(),
        "department": set(),
    }
    for s in user.scopes:
        if s.scope_type == "district" and s.district_id:
            out["district"].add(s.district_id)
        elif s.scope_type == "subdivision" and s.subdivision_id:
            out["subdivision"].add(s.subdivision_id)
        elif s.scope_type == "block" and s.block_id:
            out["block"].add(s.block_id)
        elif s.scope_type == "department" and s.department_id:
            out["department"].add(s.department_id)
    return out
