"""Allow the runtime role to remove expired grievance clusters during recomputation.

Revision ID: 0006_cluster_refresh_grant
Revises: 0005_alert_link_refresh_grant
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.config import get_settings

revision: str = "0006_cluster_refresh_grant"
down_revision: str | None = "0005_alert_link_refresh_grant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _role() -> str | None:
    bind = op.get_bind()
    role = get_settings().database_app_role
    if not bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).scalar():
        return None
    return bind.dialect.identifier_preparer.quote(role)


def upgrade() -> None:
    if q := _role():
        op.execute(f"GRANT DELETE ON intel.grievance_clusters TO {q}")


def downgrade() -> None:
    if q := _role():
        op.execute(f"REVOKE DELETE ON intel.grievance_clusters FROM {q}")
