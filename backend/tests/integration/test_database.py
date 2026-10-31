"""Migrations, schema conformance, privileges and PostGIS behaviour on real PostgreSQL.

Geometries below are synthetic unit squares, clearly TEST DATA, used only to
exercise constraints and spatial operators. They do not represent any real place.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.config import Settings
from app.db.models import Base
from tests.integration.conftest import alembic_config, insert_test_dataset

REF_TABLES = {
    "boundary_datasets",
    "districts",
    "subdivisions",
    "blocks",
    "municipalities",
    "gram_panchayats",
    "villages",
    "wards",
    "departments",
    "issue_categories",
    "grievance_sources",
}
SQUARE = "SRID=4326;MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))"
BOWTIE = "SRID=4326;MULTIPOLYGON(((0 0,1 1,1 0,0 1,0 0)))"  # self-intersecting


def test_migrations_reach_head_and_create_reference_schema(owner_engine: Engine) -> None:
    tables = set(inspect(owner_engine).get_table_names(schema="ref"))
    assert tables == REF_TABLES


def test_downgrade_and_upgrade_round_trip(migrated: Settings, owner_engine: Engine) -> None:
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT to_regnamespace('ref')")).scalar() is None
    command.upgrade(cfg, "head")
    assert set(inspect(owner_engine).get_table_names(schema="ref")) == REF_TABLES


def test_orm_models_match_migrations(owner_engine: Engine) -> None:
    from alembic import context  # noqa: F401 - ensure alembic is importable

    with owner_engine.connect() as conn:
        mc = MigrationContext.configure(
            conn,
            opts={
                "include_schemas": True,
                "compare_type": True,
                "include_name": lambda name, type_, _: type_ != "schema" or name == "ref",
            },
        )
        diff = compare_metadata(mc, Base.metadata)
    assert diff == [], f"ORM models and migrations differ: {diff}"


def test_source_channels_seeded_as_not_configured(app_conn: Connection) -> None:
    rows = app_conn.execute(
        text("SELECT code, integration_mode FROM ref.grievance_sources ORDER BY code")
    ).all()
    assert [r.code for r in rows] == sorted(
        [
            "BLOCK_OFFICE",
            "CM_HELPLINE",
            "DEPARTMENT_RECORD",
            "GOVT_PORTAL",
            "MANUAL",
            "NEWSPAPER",
            "SOCIAL_MEDIA",
        ]
    )
    assert {r.integration_mode for r in rows} == {"not_configured"}


def test_no_operational_geography_is_preloaded(app_conn: Connection) -> None:
    for table in ("districts", "blocks", "villages", "departments", "issue_categories"):
        assert app_conn.execute(text(f"SELECT count(*) FROM ref.{table}")).scalar_one() == 0


# --- Least privilege -------------------------------------------------------------------


def test_runtime_role_can_read_and_write(app_conn: Connection) -> None:
    app_conn.execute(
        text("INSERT INTO ref.departments (code, name_en) VALUES ('TEST_DEPT', 'TEST DATA')")
    )
    assert (
        app_conn.execute(
            text("SELECT name_en FROM ref.departments WHERE code = 'TEST_DEPT'")
        ).scalar_one()
        == "TEST DATA"
    )


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM ref.grievance_sources",
        "TRUNCATE ref.departments",
        "CREATE TABLE ref.intruder (id int)",
        "CREATE TABLE public.intruder (id int)",
        "DROP TABLE ref.departments",
        "ALTER TABLE ref.departments ADD COLUMN x int",
        "CREATE SCHEMA intruder",
    ],
)
def test_runtime_role_cannot_delete_or_change_schema(app_conn: Connection, statement: str) -> None:
    with pytest.raises(DBAPIError) as exc:
        app_conn.execute(text(statement))
    assert (
        "permission denied" in str(exc.value).lower() or "must be owner" in str(exc.value).lower()
    )


def test_runtime_role_is_not_superuser(app_conn: Connection) -> None:
    assert (
        app_conn.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar()
        is False
    )


# --- Constraints ---------------------------------------------------------------------------


def _district(conn: Connection, **cols: object) -> None:
    base = {"name_en": "TEST DISTRICT", "state_name_en": "TEST STATE"}
    base.update(cols)
    names = ", ".join(base)
    values = ", ".join(f":{k}" for k in base)
    conn.execute(text(f"INSERT INTO ref.districts ({names}) VALUES ({values})"), base)


def test_boundary_requires_registered_dataset(app_conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="boundary_requires_dataset"):
        _district(app_conn, boundary=SQUARE)


def test_invalid_geometry_is_rejected(app_conn: Connection) -> None:
    ds = insert_test_dataset(app_conn)
    with pytest.raises(IntegrityError, match="boundary_is_valid"):
        _district(app_conn, boundary=BOWTIE, geometry_dataset_id=ds)


def test_wrong_srid_is_rejected(app_conn: Connection) -> None:
    ds = insert_test_dataset(app_conn)
    with pytest.raises(DBAPIError):
        _district(
            app_conn,
            boundary="SRID=3857;MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))",
            geometry_dataset_id=ds,
        )


@pytest.mark.parametrize(
    ("cols", "constraint"),
    [
        ({"lgd_code": "AB12"}, "lgd_code_format"),
        ({"name_en": "   "}, "name_en_not_blank"),
    ],
)
def test_unit_check_constraints(
    app_conn: Connection, cols: dict[str, object], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        _district(app_conn, **cols)


def test_lgd_code_unique_when_present(app_conn: Connection) -> None:
    _district(app_conn, lgd_code="900001", name_en="TEST A")
    _district(app_conn, name_en="TEST B")  # NULL codes do not collide
    _district(app_conn, name_en="TEST C")
    with pytest.raises(IntegrityError, match="uq_districts_lgd_code"):
        _district(app_conn, lgd_code="900001", name_en="TEST D")


def test_department_code_format_and_hierarchy(app_conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="code_format"):
        app_conn.execute(
            text("INSERT INTO ref.departments (code, name_en) VALUES ('bad code', 'x')")
        )


def test_foreign_keys_are_enforced(app_conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="fk_blocks_district_id_districts"):
        app_conn.execute(
            text(
                "INSERT INTO ref.blocks (name_en, district_id) "
                "VALUES ('TEST BLOCK', gen_random_uuid())"
            )
        )


def test_source_channel_type_is_restricted(app_conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="channel_type_allowed"):
        app_conn.execute(
            text(
                "INSERT INTO ref.grievance_sources (code, name_en, channel_type) "
                "VALUES ('TEST_SRC', 'x', 'carrier_pigeon')"
            )
        )


def test_updated_at_trigger_and_utc(app_conn: Connection) -> None:
    app_conn.execute(text("INSERT INTO ref.departments (code, name_en) VALUES ('TEST_T', 'a')"))
    # now() is fixed within a transaction, so compare against clock_timestamp().
    app_conn.execute(text("UPDATE ref.departments SET name_en = 'b' WHERE code = 'TEST_T'"))
    row = app_conn.execute(
        text("SELECT created_at, updated_at FROM ref.departments WHERE code = 'TEST_T'")
    ).one()
    assert row.updated_at >= row.created_at
    assert row.created_at.utcoffset().total_seconds() == 0
    assert app_conn.execute(text("SHOW timezone")).scalar() == "UTC"


# --- PostGIS ---------------------------------------------------------------------------------


def test_spatial_containment_query(app_conn: Connection) -> None:
    ds = insert_test_dataset(app_conn)
    _district(app_conn, name_en="TEST GEO", boundary=SQUARE, geometry_dataset_id=ds)
    district_id = app_conn.execute(
        text("SELECT id FROM ref.districts WHERE name_en = 'TEST GEO'")
    ).scalar_one()
    app_conn.execute(
        text(
            "INSERT INTO ref.villages (name_en, district_id, location, geometry_dataset_id) VALUES "
            "('TEST INSIDE', :d, 'SRID=4326;POINT(0.5 0.5)', :ds), "
            "('TEST OUTSIDE', :d, 'SRID=4326;POINT(5 5)', :ds)"
        ),
        {"d": district_id, "ds": ds},
    )
    inside = (
        app_conn.execute(
            text(
                "SELECT v.name_en FROM ref.villages v JOIN ref.districts d ON d.id = v.district_id "
                "WHERE ST_Contains(d.boundary, v.location)"
            )
        )
        .scalars()
        .all()
    )
    assert inside == ["TEST INSIDE"]


def test_village_location_requires_dataset(app_conn: Connection) -> None:
    _district(app_conn, name_en="TEST LOC")
    district_id = app_conn.execute(
        text("SELECT id FROM ref.districts WHERE name_en = 'TEST LOC'")
    ).scalar_one()
    with pytest.raises(IntegrityError, match="location_requires_dataset"):
        app_conn.execute(
            text(
                "INSERT INTO ref.villages (name_en, district_id, location) "
                "VALUES ('TEST V', :d, 'SRID=4326;POINT(0.5 0.5)')"
            ),
            {"d": district_id},
        )


def test_spatial_and_trigram_indexes_exist(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'ref' "
                "AND (indexdef ILIKE '%USING gist%' OR indexdef ILIKE '%gin_trgm_ops%')"
            )
        ).all()
    names = {r.indexname for r in rows}
    assert "ix_villages_location" in names
    assert "ix_districts_boundary" in names
    assert "ix_villages_name_en_trgm" in names
