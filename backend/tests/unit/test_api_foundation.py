"""API foundation: error envelope, request IDs, security headers, health and info."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.main import create_app
from app.modules.system import router as system_router
from app.modules.system.service import CheckResult


class _Payload(BaseModel):
    mobile_number: int


def _app(**settings: object) -> FastAPI:
    app = create_app(Settings(**settings))  # type: ignore[arg-type]
    probe = APIRouter()

    @probe.post("/api/v1/_probe/validate")
    def validate(_: _Payload) -> dict[str, str]:
        return {}

    @probe.get("/api/v1/_probe/missing")
    def missing() -> None:
        raise NotFoundError()

    @probe.get("/api/v1/_probe/crash")
    def crash() -> None:
        raise RuntimeError("database password is hunter2")

    app.include_router(probe)
    return app


@pytest.fixture
def client(env: pytest.MonkeyPatch) -> TestClient:
    return TestClient(_app(), raise_server_exceptions=False)


def test_liveness(client: TestClient) -> None:
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_liveness_supports_head(client: TestClient) -> None:
    assert client.head("/api/v1/health/live").status_code == 200


def test_request_id_generated_and_returned(client: TestClient) -> None:
    r = client.get("/api/v1/health/live")
    rid = r.headers["x-request-id"]
    assert len(rid) == 32


def test_safe_incoming_request_id_is_propagated(client: TestClient) -> None:
    r = client.get("/api/v1/health/live", headers={"X-Request-ID": "trace-abc-12345"})
    assert r.headers["x-request-id"] == "trace-abc-12345"


@pytest.mark.parametrize("bad", ["short", "x" * 65, "evil\r\ninjected-line", "has space here"])
def test_unsafe_incoming_request_id_is_replaced(client: TestClient, bad: str) -> None:
    try:
        r = client.get("/api/v1/health/live", headers={"X-Request-ID": bad})
    except Exception:  # noqa: BLE001 - httpx itself refuses CR/LF in headers, which is fine
        return
    assert r.headers["x-request-id"] != bad


def test_security_headers(client: TestClient) -> None:
    r = client.get("/api/v1/health/live")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "strict-transport-security" not in r.headers  # only in production


def test_hsts_in_production(env: pytest.MonkeyPatch) -> None:
    strong = "x9Kq2LmP7vR4tZ8wB3nY6cF1"
    app = create_app(
        Settings(
            app_env="production",  # type: ignore[arg-type]
            database_password=strong,  # type: ignore[arg-type]
            redis_password=strong,  # type: ignore[arg-type]
            deployment_district_name="Configured District",
        )
    )
    r = TestClient(app).get("/api/v1/health/live")
    assert "max-age=31536000" in r.headers["strict-transport-security"]
    # API docs and the OpenAPI schema are not served in production by default.
    assert TestClient(app).get("/api/docs").status_code == 404
    assert TestClient(app).get("/api/v1/openapi.json").status_code == 404


def test_untrusted_host_is_rejected(client: TestClient) -> None:
    r = client.get("/api/v1/health/live", headers={"Host": "attacker.example"})
    assert r.status_code == 400


def test_not_found_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/_probe/missing")
    assert r.status_code == 404
    body = r.json()["error"]
    assert body["code"] == "not_found"
    assert body["request_id"] == r.headers["x-request-id"]


def test_unknown_route_uses_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_validation_errors_do_not_echo_submitted_values(client: TestClient) -> None:
    r = client.post("/api/v1/_probe/validate", json={"mobile_number": "98765-SECRET"})
    assert r.status_code == 422
    assert "98765-SECRET" not in r.text
    detail = r.json()["error"]["details"][0]
    assert detail["location"] == ["body", "mobile_number"]
    assert "input" not in detail


def test_unhandled_errors_are_generic_and_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        r = client.get("/api/v1/_probe/crash")
    assert r.status_code == 500
    assert "hunter2" not in r.text
    assert r.json()["error"]["code"] == "internal_error"
    assert any(rec.message == "unhandled_exception" for rec in caplog.records)


def test_readiness_ok_when_all_checks_pass(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        system_router.service,
        "check_database",
        lambda *_: [CheckResult(n, True, 1.0) for n in ("database", "postgis", "migrations")],
    )
    monkeypatch.setattr(
        system_router.service, "check_redis", lambda *_: CheckResult("redis", True, 1.0)
    )
    monkeypatch.setattr(system_router, "get_engine", lambda: None)
    monkeypatch.setattr(system_router, "get_redis", lambda: None)
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert set(body["components"]) == {"database", "postgis", "migrations", "redis"}


def test_readiness_503_when_a_dependency_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        system_router.service,
        "check_database",
        lambda *_: [
            CheckResult("database", True, 1.0),
            CheckResult("postgis", True, 1.0),
            CheckResult("migrations", False, 1.0, "schema_not_at_head"),
        ],
    )
    monkeypatch.setattr(
        system_router.service,
        "check_redis",
        lambda *_: CheckResult("redis", False, 2.0, "unreachable"),
    )
    monkeypatch.setattr(system_router, "get_engine", lambda: None)
    monkeypatch.setattr(system_router, "get_redis", lambda: None)
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["components"]["migrations"]["reason"] == "schema_not_at_head"
    assert body["components"]["redis"]["status"] == "unavailable"


def test_system_info_reports_unconfigured_identity_as_null(client: TestClient) -> None:
    r = client.get("/api/v1/system/info")
    assert r.status_code == 200
    body = r.json()
    assert body["deployment"]["district_name"] is None
    assert body["environment"] == "development"


def test_system_info_reports_configured_identity(env: pytest.MonkeyPatch) -> None:
    app = _app(deployment_district_name="Configured District", deployment_state_name="State")
    body = TestClient(app).get("/api/v1/system/info").json()
    assert body["deployment"]["district_name"] == "Configured District"
    assert body["deployment"]["state_name"] == "State"


def test_access_log_omits_query_string(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.access"):
        client.get("/api/v1/health/live?citizen=SensitiveName")
    records = [r for r in caplog.records if r.name == "app.access"]
    assert records
    assert records[-1].path == "/api/v1/health/live"  # type: ignore[attr-defined]
    assert "SensitiveName" not in json.dumps(records[-1].__dict__, default=str)
