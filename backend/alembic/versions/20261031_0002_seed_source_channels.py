"""Register the grievance source channels named in the project specification.

Revision ID: 0002_seed_source_channels
Revises: 0001_reference_foundation
Create Date: 2026-10-31

These rows describe *channels* (configuration), not grievances or operational data.
Every channel is registered with integration_mode = 'not_configured': no live
external integration exists until one is built, documented and authorised.
Administrators may rename channels or add local-language names later.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_seed_source_channels"
down_revision: str | None = "0001_reference_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHANNELS = (
    (
        "CM_HELPLINE",
        "CM Helpline",
        "helpline",
        "Complaints received through the State Chief Minister's Helpline.",
    ),
    (
        "GOVT_PORTAL",
        "Government grievance portal",
        "government_portal",
        "Complaints from government grievance portals. Each portal gets its own adapter configuration.",
    ),
    (
        "BLOCK_OFFICE",
        "Block office",
        "administrative_office",
        "Complaints received at block development offices.",
    ),
    (
        "NEWSPAPER",
        "Newspaper",
        "print_media",
        "Public issues reported in newspapers and recorded by authorised staff.",
    ),
    (
        "SOCIAL_MEDIA",
        "Social media",
        "social_media",
        "Public issues reported on social media and recorded by authorised staff.",
    ),
    (
        "MANUAL",
        "Manual submission",
        "manual",
        "Complaints submitted in person or in writing and entered by authorised operators.",
    ),
    (
        "DEPARTMENT_RECORD",
        "Department record",
        "departmental_record",
        "Complaint records maintained by line departments.",
    ),
)


def upgrade() -> None:
    table = sa.table(
        "grievance_sources",
        sa.column("code", sa.String),
        sa.column("name_en", sa.String),
        sa.column("channel_type", sa.String),
        sa.column("integration_mode", sa.String),
        sa.column("description", sa.Text),
        schema="ref",
    )
    rows = [
        {
            "code": c,
            "name_en": n,
            "channel_type": t,
            "integration_mode": "not_configured",
            "description": d,
        }
        for c, n, t, d in CHANNELS
    ]
    stmt = postgresql.insert(table).values(rows).on_conflict_do_nothing(index_elements=["code"])
    op.execute(stmt)


def downgrade() -> None:
    codes = ", ".join(f"'{c[0]}'" for c in CHANNELS)
    op.execute(f"DELETE FROM ref.grievance_sources WHERE code IN ({codes})")
