"""Health and public system metadata endpoints (unauthenticated by design).

* ``/health/live``  - process is up; no dependency checks (for container restarts).
* ``/health/ready`` - PostgreSQL, PostGIS, migration head and Redis are usable
  (for load balancer routing). Returns 503 when any component is unavailable.
* ``/system/info``  - application version and the configured deployment identity
  shown in the official header. Contains no confidential data.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.db.session import get_engine
from app.infra.redis import get_redis
from app.modules.system import service
from app.modules.system.schemas import (
    ComponentStatus,
    DeploymentIdentity,
    LivenessResponse,
    ReadinessResponse,
    SystemInfoResponse,
)

router = APIRouter(tags=["system"])
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="health")


@router.api_route(
    "/health/live",
    methods=["GET", "HEAD"],
    response_model=LivenessResponse,
    summary="Liveness probe",
)
def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"model": ReadinessResponse, "description": "A dependency is unavailable"}},
)
def readiness(settings: Annotated[Settings, Depends(get_app_settings)]) -> JSONResponse:
    timeout = settings.health_check_timeout_seconds
    db_future = _executor.submit(service.check_database, get_engine(), timeout)
    redis_future = _executor.submit(service.check_redis, get_redis())

    results = []
    try:
        results.extend(db_future.result(timeout=timeout + 1))
    except TimeoutError:
        results.extend(
            service.CheckResult(n, False, timeout * 1000, "timeout")
            for n in ("database", "postgis", "migrations")
        )
    try:
        results.append(redis_future.result(timeout=timeout + 1))
    except TimeoutError:
        results.append(service.CheckResult("redis", False, timeout * 1000, "timeout"))

    healthy = all(r.ok for r in results)
    body = ReadinessResponse(
        status="ok" if healthy else "unavailable",
        checked_at=datetime.now(UTC).isoformat(),
        components={
            r.name: ComponentStatus(
                status="ok" if r.ok else "unavailable", latency_ms=r.latency_ms, reason=r.reason
            )
            for r in results
        },
    )
    return JSONResponse(body.model_dump(), status_code=200 if healthy else 503)


@router.get("/system/info", response_model=SystemInfoResponse, summary="Deployment metadata")
def system_info(s: Annotated[Settings, Depends(get_app_settings)]) -> SystemInfoResponse:
    return SystemInfoResponse(
        application=s.app_name,
        version=s.app_version,
        environment=s.app_env.value,
        deployment=DeploymentIdentity(
            district_name=s.deployment_district_name,
            district_name_local=s.deployment_district_name_local,
            state_name=s.deployment_state_name,
            state_name_local=s.deployment_state_name_local,
        ),
    )
