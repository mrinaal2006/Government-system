"""Readiness against real services, and a Celery round trip through Redis."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import clear_cached_singletons


def test_readiness_ok_against_real_services(migrated: Settings) -> None:
    clear_cached_singletons()
    r = TestClient(create_app()).get("/api/v1/health/ready")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert {k: v["status"] for k, v in body["components"].items()} == {
        "database": "ok",
        "postgis": "ok",
        "migrations": "ok",
        "redis": "ok",
    }


def test_readiness_reports_redis_outage_without_leaking_details(
    migrated: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIS_PORT", "1")  # nothing listens here
    clear_cached_singletons()
    try:
        r = TestClient(create_app()).get("/api/v1/health/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["components"]["redis"] == {
            "status": "unavailable",
            "latency_ms": body["components"]["redis"]["latency_ms"],
            "reason": "unreachable",
        }
        assert body["components"]["database"]["status"] == "ok"
        assert "Connection refused" not in r.text and "127.0.0.1" not in r.text
    finally:
        monkeypatch.undo()
        clear_cached_singletons()


def test_readiness_detects_schema_behind_head(migrated: Settings) -> None:
    from alembic import command

    from tests.integration.conftest import alembic_config

    cfg = alembic_config()
    command.downgrade(cfg, "-1")
    clear_cached_singletons()
    try:
        r = TestClient(create_app()).get("/api/v1/health/ready")
        assert r.status_code == 503
        assert r.json()["components"]["migrations"]["reason"] == "schema_not_at_head"
    finally:
        command.upgrade(cfg, "head")
        clear_cached_singletons()


def test_celery_round_trip_through_redis(migrated: Settings) -> None:
    from celery.contrib.testing.worker import start_worker

    import app.worker.tasks  # noqa: F401
    from app.worker.celery_app import celery_app

    celery_app.conf.broker_url = migrated.celery_broker_url
    celery_app.conf.result_backend = migrated.celery_result_backend_url
    with start_worker(celery_app, perform_ping_check=False, pool="solo", loglevel="WARNING"):
        result = celery_app.send_task("system.ping").get(timeout=20)
    assert result["status"] == "pong"
