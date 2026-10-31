"""Phase 1 foundation: reference schema, administrative geography, org master data.

Revision ID: 0001_reference_foundation
Revises:
Create Date: 2026-10-31

Creates:
* schema ``ref`` (owned by the migration role)
* trigger function ``public.dgimews_set_updated_at()``
* ``ref.boundary_datasets`` and the administrative unit tables
* ``ref.departments``, ``ref.issue_categories``, ``ref.grievance_sources``
* grants: the runtime role gets SELECT/INSERT/UPDATE (no DELETE: reference rows are
  deactivated, not deleted) and no DDL rights.

Extensions (postgis, pgcrypto, pg_trgm, citext) are installed by the superuser init
script; this migration only verifies they exist, because the migration role is
deliberately not a superuser.
"""

import logging
from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings

revision: str = "0001_reference_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")

SCHEMA = "ref"
REQUIRED_EXTENSIONS = ("postgis", "pgcrypto", "pg_trgm", "citext")
CODE_PATTERN = r"^[A-Z][A-Z0-9_]{1,49}$"
LGD_CODE_PATTERN = r"^[0-9]{1,16}$"
UNIT_TABLES = (
    "districts",
    "subdivisions",
    "blocks",
    "municipalities",
    "gram_panchayats",
    "villages",
    "wards",
)
TRIGGER_TABLES = (
    "boundary_datasets",
    *UNIT_TABLES,
    "departments",
    "issue_categories",
    "grievance_sources",
)


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def _is_active() -> sa.Column:
    return sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"))


def _fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        [f"{SCHEMA}.{target}.id"],
        name=f"fk_{table}_{column}_{target}",
        ondelete="RESTRICT",
    )


def _unit_columns() -> list[sa.Column]:
    return [
        _uuid_pk(),
        *_timestamps(),
        _is_active(),
        sa.Column(
            "lgd_code",
            sa.String(16),
            nullable=True,
            comment="Local Government Directory code, when assigned",
        ),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column(
            "name_local",
            sa.String(200),
            nullable=True,
            comment="Name in the official local language/script",
        ),
        sa.Column(
            "boundary",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False
            ),
            nullable=True,
        ),
        sa.Column("geometry_dataset_id", postgresql.UUID(as_uuid=True), nullable=True),
    ]


def _unit_constraints(table: str) -> list[sa.Constraint]:
    return [
        sa.PrimaryKeyConstraint("id", name=f"pk_{table}"),
        sa.CheckConstraint(
            f"lgd_code IS NULL OR lgd_code ~ '{LGD_CODE_PATTERN}'",
            name=f"ck_{table}_lgd_code_format",
        ),
        sa.CheckConstraint("length(btrim(name_en)) > 0", name=f"ck_{table}_name_en_not_blank"),
        sa.CheckConstraint(
            "boundary IS NULL OR geometry_dataset_id IS NOT NULL",
            name=f"ck_{table}_boundary_requires_dataset",
        ),
        sa.CheckConstraint(
            "boundary IS NULL OR ST_IsValid(boundary)", name=f"ck_{table}_boundary_is_valid"
        ),
        _fk(table, "geometry_dataset_id", "boundary_datasets"),
    ]


def _unit_indexes(table: str) -> None:
    op.create_index(
        f"uq_{table}_lgd_code",
        table,
        ["lgd_code"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("lgd_code IS NOT NULL"),
    )
    op.create_index(
        f"ix_{table}_boundary", table, ["boundary"], schema=SCHEMA, postgresql_using="gist"
    )
    op.create_index(
        f"ix_{table}_name_en_trgm",
        table,
        ["name_en"],
        schema=SCHEMA,
        postgresql_using="gin",
        postgresql_ops={"name_en": "gin_trgm_ops"},
    )


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _verify_extensions() -> None:
    bind = op.get_bind()
    installed = set(bind.execute(sa.text("SELECT extname FROM pg_extension")).scalars())
    missing = [ext for ext in REQUIRED_EXTENSIONS if ext not in installed]
    if missing:
        raise RuntimeError(
            "Missing PostgreSQL extensions "
            f"{missing}. Run infra/postgres/init/01-roles-and-extensions.sh as superuser first."
        )


def _grant_runtime_role() -> None:
    bind = op.get_bind()
    role = get_settings().database_app_role
    if not bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).scalar():
        log.warning("Runtime role %r does not exist; skipping grants on schema %s", role, SCHEMA)
        return
    quoted = bind.dialect.identifier_preparer.quote(role)
    op.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {quoted}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA {SCHEMA} TO {quoted}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} GRANT SELECT, INSERT, UPDATE ON TABLES TO {quoted}"
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION public.dgimews_set_updated_at() TO {quoted}")
    # Read-only access so the readiness probe can confirm the schema is at head.
    op.execute(f"GRANT SELECT ON public.alembic_version TO {quoted}")


def upgrade() -> None:
    _verify_extensions()
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.execute(
        f"COMMENT ON SCHEMA {SCHEMA} IS 'Reference and master data (geography, departments, categories, sources)'"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.dgimews_set_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $$
        """
    )

    # --- Provenance of geographic data -------------------------------------------------
    op.create_table(
        "boundary_datasets",
        _uuid_pk(),
        *_timestamps(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("publisher", sa.String(200), nullable=False),
        sa.Column("dataset_version", sa.String(50), nullable=False),
        sa.Column(
            "source_reference",
            sa.Text(),
            nullable=False,
            comment="URL, order number or document reference of the source",
        ),
        sa.Column("licence", sa.String(200), nullable=True),
        sa.Column("acquired_on", sa.Date(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_boundary_datasets"),
        sa.UniqueConstraint(
            "name", "dataset_version", name="uq_boundary_datasets_name_dataset_version"
        ),
        sa.CheckConstraint(
            "checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_boundary_datasets_checksum_format",
        ),
        schema=SCHEMA,
        comment="Provenance of verified geographic datasets",
    )

    # --- Administrative units -------------------------------------------------------------
    op.create_table(
        "districts",
        *_unit_columns(),
        sa.Column("state_name_en", sa.String(200), nullable=False),
        sa.Column("state_lgd_code", sa.String(16), nullable=True),
        *_unit_constraints("districts"),
        sa.UniqueConstraint("state_name_en", "name_en", name="uq_districts_state_name_en_name_en"),
        schema=SCHEMA,
    )
    _unit_indexes("districts")

    op.create_table(
        "subdivisions",
        *_unit_columns(),
        sa.Column("district_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_unit_constraints("subdivisions"),
        _fk("subdivisions", "district_id", "districts"),
        sa.UniqueConstraint("district_id", "name_en", name="uq_subdivisions_district_id_name_en"),
        schema=SCHEMA,
    )
    _unit_indexes("subdivisions")
    op.create_index("ix_subdivisions_district_id", "subdivisions", ["district_id"], schema=SCHEMA)

    op.create_table(
        "blocks",
        *_unit_columns(),
        sa.Column("district_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subdivision_id", postgresql.UUID(as_uuid=True), nullable=True),
        *_unit_constraints("blocks"),
        _fk("blocks", "district_id", "districts"),
        _fk("blocks", "subdivision_id", "subdivisions"),
        sa.UniqueConstraint("district_id", "name_en", name="uq_blocks_district_id_name_en"),
        schema=SCHEMA,
    )
    _unit_indexes("blocks")
    op.create_index("ix_blocks_district_id", "blocks", ["district_id"], schema=SCHEMA)
    op.create_index("ix_blocks_subdivision_id", "blocks", ["subdivision_id"], schema=SCHEMA)

    body_types = (
        "municipal_corporation",
        "municipal_council",
        "nagar_panchayat",
        "cantonment_board",
        "other",
    )
    op.create_table(
        "municipalities",
        *_unit_columns(),
        sa.Column("district_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subdivision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body_type", sa.String(40), nullable=False),
        *_unit_constraints("municipalities"),
        _fk("municipalities", "district_id", "districts"),
        _fk("municipalities", "subdivision_id", "subdivisions"),
        sa.UniqueConstraint("district_id", "name_en", name="uq_municipalities_district_id_name_en"),
        sa.CheckConstraint(
            _in("body_type", body_types), name="ck_municipalities_body_type_allowed"
        ),
        schema=SCHEMA,
    )
    _unit_indexes("municipalities")
    op.create_index(
        "ix_municipalities_district_id", "municipalities", ["district_id"], schema=SCHEMA
    )

    op.create_table(
        "gram_panchayats",
        *_unit_columns(),
        sa.Column("block_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_unit_constraints("gram_panchayats"),
        _fk("gram_panchayats", "block_id", "blocks"),
        sa.UniqueConstraint("block_id", "name_en", name="uq_gram_panchayats_block_id_name_en"),
        schema=SCHEMA,
    )
    _unit_indexes("gram_panchayats")
    op.create_index("ix_gram_panchayats_block_id", "gram_panchayats", ["block_id"], schema=SCHEMA)

    op.create_table(
        "villages",
        *_unit_columns(),
        sa.Column("district_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subdivision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("block_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("gram_panchayat_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("census_code", sa.String(16), nullable=True),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=True,
            comment="Representative point from a registered dataset; never estimated",
        ),
        *_unit_constraints("villages"),
        _fk("villages", "district_id", "districts"),
        _fk("villages", "subdivision_id", "subdivisions"),
        _fk("villages", "block_id", "blocks"),
        _fk("villages", "gram_panchayat_id", "gram_panchayats"),
        sa.CheckConstraint(
            "location IS NULL OR geometry_dataset_id IS NOT NULL",
            name="ck_villages_location_requires_dataset",
        ),
        schema=SCHEMA,
    )
    _unit_indexes("villages")
    op.create_index(
        "ix_villages_location", "villages", ["location"], schema=SCHEMA, postgresql_using="gist"
    )
    for col in ("district_id", "block_id", "gram_panchayat_id", "subdivision_id"):
        op.create_index(f"ix_villages_{col}", "villages", [col], schema=SCHEMA)
    op.create_index(
        "uq_villages_census_code",
        "villages",
        ["census_code"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("census_code IS NOT NULL"),
    )

    op.create_table(
        "wards",
        *_unit_columns(),
        sa.Column("municipality_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ward_number", sa.String(20), nullable=False),
        *_unit_constraints("wards"),
        _fk("wards", "municipality_id", "municipalities"),
        sa.UniqueConstraint(
            "municipality_id", "ward_number", name="uq_wards_municipality_id_ward_number"
        ),
        schema=SCHEMA,
    )
    _unit_indexes("wards")
    op.create_index("ix_wards_municipality_id", "wards", ["municipality_id"], schema=SCHEMA)

    # --- Organisation master data -------------------------------------------------------
    op.create_table(
        "departments",
        _uuid_pk(),
        *_timestamps(),
        _is_active(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("name_local", sa.String(200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_departments"),
        sa.UniqueConstraint("code", name="uq_departments_code"),
        sa.CheckConstraint(f"code ~ '{CODE_PATTERN}'", name="ck_departments_code_format"),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name="ck_departments_not_own_parent"
        ),
        _fk("departments", "parent_id", "departments"),
        schema=SCHEMA,
    )
    op.create_index("ix_departments_parent_id", "departments", ["parent_id"], schema=SCHEMA)
    op.create_index(
        "ix_departments_name_en_trgm",
        "departments",
        ["name_en"],
        schema=SCHEMA,
        postgresql_using="gin",
        postgresql_ops={"name_en": "gin_trgm_ops"},
    )

    op.create_table(
        "issue_categories",
        _uuid_pk(),
        *_timestamps(),
        _is_active(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("name_local", sa.String(200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_department_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_essential_service",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Set by administrators; used by the early-warning engine (Phase 6)",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_issue_categories"),
        sa.UniqueConstraint("code", name="uq_issue_categories_code"),
        sa.CheckConstraint(f"code ~ '{CODE_PATTERN}'", name="ck_issue_categories_code_format"),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name="ck_issue_categories_not_own_parent"
        ),
        _fk("issue_categories", "parent_id", "issue_categories"),
        _fk("issue_categories", "default_department_id", "departments"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_issue_categories_parent_id", "issue_categories", ["parent_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_issue_categories_default_department_id",
        "issue_categories",
        ["default_department_id"],
        schema=SCHEMA,
    )

    channel_types = (
        "helpline",
        "government_portal",
        "administrative_office",
        "print_media",
        "social_media",
        "manual",
        "departmental_record",
    )
    integration_modes = ("not_configured", "development_adapter", "file_import", "live_api")
    op.create_table(
        "grievance_sources",
        _uuid_pk(),
        *_timestamps(),
        _is_active(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("name_local", sa.String(200), nullable=True),
        sa.Column("channel_type", sa.String(40), nullable=False),
        sa.Column(
            "integration_mode",
            sa.String(40),
            nullable=False,
            server_default=sa.text("'not_configured'"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_grievance_sources"),
        sa.UniqueConstraint("code", name="uq_grievance_sources_code"),
        sa.CheckConstraint(f"code ~ '{CODE_PATTERN}'", name="ck_grievance_sources_code_format"),
        sa.CheckConstraint(
            _in("channel_type", channel_types), name="ck_grievance_sources_channel_type_allowed"
        ),
        sa.CheckConstraint(
            _in("integration_mode", integration_modes),
            name="ck_grievance_sources_integration_mode_allowed",
        ),
        schema=SCHEMA,
    )

    for table in TRIGGER_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_set_updated_at BEFORE UPDATE ON {SCHEMA}.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.dgimews_set_updated_at()"
        )

    _grant_runtime_role()


def downgrade() -> None:
    for table in reversed(TRIGGER_TABLES):
        op.drop_table(table, schema=SCHEMA)
    op.execute("DROP FUNCTION IF EXISTS public.dgimews_set_updated_at()")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
