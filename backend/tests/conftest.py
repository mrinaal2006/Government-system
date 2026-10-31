"""Shared test configuration.

Unit tests need no services. Integration tests (``-m integration``) use the
PostgreSQL/Redis started by docker-compose.dev.yml and ALWAYS target the
``<DATABASE_NAME>_test`` database, which they migrate down and up repeatedly.
Connection secrets are read from the repository's .env (created by
scripts/init-dev-env.sh) unless already present in the environment.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def integration_environment() -> dict[str, str]:
    dotenv = _load_dotenv(REPO_ROOT / ".env")

    def pick(key: str, default: str = "") -> str:
        return os.environ.get(key) or dotenv.get(key) or default

    base_name = pick("DATABASE_NAME", "dgimews")
    return {
        "APP_ENV": "test",
        "LOG_FORMAT": "console",
        "DATABASE_HOST": pick("TEST_DATABASE_HOST", "127.0.0.1"),
        "DATABASE_PORT": pick("DEV_DB_PORT", "55432"),
        "DATABASE_NAME": f"{base_name}_test",
        "DATABASE_USER": pick("DATABASE_APP_USER", "dgimews_app"),
        "DATABASE_PASSWORD": pick("DATABASE_APP_PASSWORD"),
        "DATABASE_APP_ROLE": pick("DATABASE_APP_USER", "dgimews_app"),
        "DATABASE_MIGRATION_USER": pick("DATABASE_MIGRATION_USER", "dgimews_migrator"),
        "DATABASE_MIGRATION_PASSWORD": pick("DATABASE_MIGRATION_PASSWORD"),
        "REDIS_HOST": pick("TEST_REDIS_HOST", "127.0.0.1"),
        "REDIS_PORT": pick("DEV_REDIS_PORT", "56379"),
        "REDIS_PASSWORD": pick("REDIS_PASSWORD"),
        # Isolate from development data in Redis DBs 0-2.
        "REDIS_CACHE_DB": "10",
        "REDIS_BROKER_DB": "11",
        "REDIS_RESULT_DB": "12",
    }


def clear_cached_singletons() -> None:
    from app.db.session import get_engine, get_session_factory
    from app.infra.redis import get_redis

    if get_engine.cache_info().currsize:
        get_engine().dispose()
    for fn in (get_settings, get_engine, get_session_factory, get_redis):
        fn.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Set environment variables for a test; settings caches are reset around it."""
    for key in list(os.environ):
        if key.startswith(("DATABASE_", "REDIS_", "DEPLOYMENT_")) or key in {
            "APP_ENV",
            "EXPOSE_API_DOCS",
            "ALLOWED_HOSTS",
        }:
            monkeypatch.delenv(key, raising=False)
    return monkeypatch
