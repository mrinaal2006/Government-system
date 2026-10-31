"""Alembic environment.

Migrations connect with the migration role (DATABASE_MIGRATION_USER), which owns
the schemas. The runtime application role only receives DML privileges.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.db.base import SCHEMA_REFERENCE
from app.db.models import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
MANAGED_SCHEMAS = {SCHEMA_REFERENCE}


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    # Ignore PostGIS-owned objects (e.g. public.spatial_ref_sys) and unmanaged schemas.
    if type_ == "table":
        return obj.schema in MANAGED_SCHEMAS
    return True


def include_name(name, type_, parent_names):  # type: ignore[no-untyped-def]
    if type_ == "schema":
        return name in MANAGED_SCHEMAS
    return True


def _configure_kwargs() -> dict[str, object]:
    return {
        "target_metadata": target_metadata,
        "include_schemas": True,
        "include_object": include_object,
        "include_name": include_name,
        "compare_type": True,
        "version_table_schema": "public",
    }


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().migration_database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_configure_kwargs(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, **_configure_kwargs())
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(
        get_settings().migration_database_url,
        poolclass=pool.NullPool,
        connect_args={"options": "-c timezone=UTC"},
    )
    with engine.connect() as conn:
        context.configure(connection=conn, **_configure_kwargs())
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
