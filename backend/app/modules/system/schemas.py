from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ComponentStatus(BaseModel):
    status: Literal["ok", "unavailable"]
    latency_ms: float = Field(description="Time taken by the check, in milliseconds")
    reason: str | None = Field(default=None, description="Non-sensitive reason code on failure")


class ReadinessResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    checked_at: str = Field(description="UTC ISO-8601 timestamp of the check")
    components: dict[str, ComponentStatus]


class DeploymentIdentity(BaseModel):
    district_name: str | None = Field(description="Configured district; null if not configured")
    district_name_local: str | None
    state_name: str | None
    state_name_local: str | None


class SystemInfoResponse(BaseModel):
    application: str
    version: str
    environment: str
    deployment: DeploymentIdentity
