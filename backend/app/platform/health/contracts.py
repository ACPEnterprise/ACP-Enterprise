from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class HealthState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    NOT_READY = "NOT_READY"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ComponentHealth(BaseModel):
    component: str
    state: HealthState
    required: bool
    classification: str
    reason: str
    observed_at: datetime
    safe_facts: dict[str, str | int | bool | None] = Field(default_factory=dict)


class SystemReadiness(BaseModel):
    state: HealthState
    application: str
    version: str
    environment: str
    observed_at: datetime
    components: list[ComponentHealth]
