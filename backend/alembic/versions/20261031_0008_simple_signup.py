"""Simple sign-up: remove the administrator-approval workflow for access requests.

Accounts created by sign-up are now active immediately (see app/modules/iam/signup.py),
so the approval columns added in 0007 are no longer used. Any request still pending or
rejected stays as an inactive account that an administrator can activate or leave.

Revision ID: 0008_simple_signup
Revises: 0007_signup
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_simple_signup"
down_revision = "0007_signup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_users_approval_status_allowed", "users", schema="iam", type_="check")
    op.drop_constraint(op.f("fk_users_reviewed_by_users"), "users", schema="iam", type_="foreignkey")
    op.drop_index("ix_users_approval_status", table_name="users", schema="iam")
    for column in (
        "review_note",
        "reviewed_at",
        "reviewed_by",
        "access_request_note",
        "requested_role",
        "approval_status",
    ):
        op.drop_column("users", column, schema="iam")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("approval_status", sa.String(length=20), server_default=sa.text("'approved'"), nullable=False),
        schema="iam",
    )
    op.add_column("users", sa.Column("requested_role", sa.String(length=64), nullable=True), schema="iam")
    op.add_column("users", sa.Column("access_request_note", sa.Text(), nullable=True), schema="iam")
    op.add_column("users", sa.Column("reviewed_by", sa.UUID(), nullable=True), schema="iam")
    op.add_column("users", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True), schema="iam")
    op.add_column("users", sa.Column("review_note", sa.Text(), nullable=True), schema="iam")
    op.create_index("ix_users_approval_status", "users", ["approval_status"], unique=False, schema="iam")
    op.create_foreign_key(
        op.f("fk_users_reviewed_by_users"),
        "users",
        "users",
        ["reviewed_by"],
        ["id"],
        source_schema="iam",
        referent_schema="iam",
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_users_approval_status_allowed",
        "users",
        "approval_status IN ('approved', 'pending', 'rejected')",
        schema="iam",
    )
