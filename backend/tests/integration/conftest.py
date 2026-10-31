from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from tests.conftest import clear_cached_singletons, integration_environment

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def integration_settings() -> Iterator[Settings]:
    mp = pytest.MonkeyPatch()
    for key, value in integration_environment().items():
        mp.setenv(key, value)
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.database_name.endswith("_test"):
        pytest.exit("Refusing to run integration tests against a non-_test database", 2)
    if not settings.database_password.get_secret_value():
        pytest.skip("No database credentials; run scripts/init-dev-env.sh and start the dev stack")
    yield settings
    clear_cached_singletons()
    mp.undo()


@pytest.fixture(autouse=True)
def _keep_integration_settings(integration_settings: Settings) -> Iterator[None]:
    # The root conftest clears the settings cache around every test; re-prime it
    # from the (still monkeypatched) environment.
    yield


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def migrated(integration_settings: Settings) -> Settings:
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return integration_settings


@pytest.fixture(scope="session")
def owner_engine(migrated: Settings) -> Iterator[Engine]:
    engine = create_engine(migrated.migration_database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine(migrated: Settings) -> Iterator[Engine]:
    engine = create_engine(migrated.database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def app_conn(app_engine: Engine) -> Iterator[Connection]:
    """Runtime-role connection inside a transaction that is always rolled back."""
    with app_engine.connect() as conn:
        trans = conn.begin()
        try:
            yield conn
        finally:
            trans.rollback()


def insert_test_dataset(conn: Connection) -> str:
    """Insert a provenance row explicitly marked as TEST DATA."""
    return str(
        conn.execute(
            text(
                "INSERT INTO ref.boundary_datasets "
                "(name, publisher, dataset_version, source_reference, acquired_on) "
                "VALUES ('TEST DATA - synthetic', 'pytest', 't1', 'tests/integration', "
                "current_date) RETURNING id"
            )
        ).scalar_one()
    )


@pytest.fixture
def db_session(migrated: Settings) -> Iterator[Session]:
    """Runtime-role session that COMMITS (API tests need visible data). TEST DATA only."""
    from app.db.session import get_session_factory

    clear_cached_singletons()
    with get_session_factory()() as s:
        yield s
        s.commit()


@pytest.fixture
def client(migrated: Settings) -> Iterator[TestClient]:
    from app.main import create_app

    clear_cached_singletons()
    _flush_rate_limits()
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        yield c


def _flush_rate_limits() -> None:
    from app.infra.redis import get_redis

    r = get_redis()
    for key in r.scan_iter("rl:*", count=500):
        r.delete(key)
