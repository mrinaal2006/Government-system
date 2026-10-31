"""Dependency health checks.

Each check returns only a status and latency. Failure details are logged
server-side and never returned to the caller, so the readiness endpoint cannot be
used to fingerprint infrastructure.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import redis
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

logger = logging.getLogger("app.health")

BACKEND_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    latency_ms: float
    reason: str | None = None  # short, non-sensitive reason code


def _timed(name: str, fn: Callable[[], str | None]) -> CheckResult:
    started = time.perf_counter()
    try:
        reason = fn()
        ok = reason is None
    except Exception as exc:  # noqa: BLE001 - every failure must map to "unavailable"
        logger.warning(
            "health_check_failed",
            extra={"check": name, "error_type": type(exc).__name__, "error": str(exc)[:500]},
        )
        ok, reason = False, "unreachable"
    latency = round((time.perf_counter() - started) * 1000, 2)
    if not ok and reason != "unreachable":
        logger.warning("health_check_failed", extra={"check": name, "reason": reason})
    return CheckResult(name, ok, latency, reason)


def expected_migration_heads() -> set[str]:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return set(ScriptDirectory.from_config(cfg).get_heads())


def check_database(engine: Engine, timeout_s: float) -> list[CheckResult]:
    results: list[CheckResult] = []
    timeout_ms = int(timeout_s * 1000)

    def database() -> str | None:
        with engine.connect() as conn:
            conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
            conn.execute(text("SELECT 1")).scalar_one()
        return None

    def postgis() -> str | None:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT postgis_lib_version()")).scalar_one()
        return None if version else "extension_missing"

    def migrations() -> str | None:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT version_num FROM public.alembic_version")).scalars()
            current = set(rows)
        return None if current == expected_migration_heads() else "schema_not_at_head"

    results.append(_timed("database", database))
    if results[0].ok:
        results.append(_timed("postgis", postgis))
        results.append(_timed("migrations", migrations))
    else:
        results.append(CheckResult("postgis", False, 0.0, "database_unavailable"))
        results.append(CheckResult("migrations", False, 0.0, "database_unavailable"))
    return results


def check_redis(client: redis.Redis) -> CheckResult:
    def ping() -> str | None:
        return None if client.ping() else "no_pong"

    return _timed("redis", ping)
