# ruff: noqa: UP045 -- keep Pydantic model loading compatible with Python 3.9 tools.
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FactoryEventIn(StrictSchema):
    lane_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    milestone_code: Optional[str] = Field(default=None, min_length=1, max_length=160)
    event_type: Literal[
        "queued",
        "work_started",
        "handoff",
        "pickup",
        "engineering_complete",
        "beta_complete",
        "owner_accepted",
        "closed",
        "defect_opened",
        "defect_closed",
        "gate_opened",
        "gate_closed",
        "rework_started",
        "first_pass_complete",
    ]
    lifecycle_state: Optional[
        Literal[
            "ACTIVE",
            "ASSIGNED",
            "ELIGIBLE_IDLE",
            "WAITING_INTEGRATION",
            "HUMAN_GATE",
            "PROVIDER_GATE",
            "DEPENDENCY_BLOCKED",
            "RATE_LIMITED",
            "UNSAFE_STOP",
        ]
    ] = None
    queue_depth: int = Field(default=0, ge=0, le=10000)
    idempotency_key: str = Field(min_length=1, max_length=200)
    occurred_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("lifecycle_state", mode="before")
    @classmethod
    def normalize_lifecycle_state(cls, value: object) -> object:
        aliases = {
            "active": "ACTIVE",
            "queued": "ASSIGNED",
            "idle": "ELIGIBLE_IDLE",
            "handoff": "WAITING_INTEGRATION",
            "blocked": "DEPENDENCY_BLOCKED",
        }
        return aliases.get(value, value) if isinstance(value, str) else value

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return value


class FactoryEventResponse(StrictSchema):
    id: str
    duplicate: bool


class FactoryLaneResponse(StrictSchema):
    lane_code: str
    milestone_code: Optional[str]
    lifecycle_state: str
    queue_depth: int
    active_since: Optional[datetime]
    last_handoff_at: Optional[datetime]
    last_event_at: datetime


class FactoryMetricsResponse(StrictSchema):
    engineering_percent: float
    beta_percent: float
    owner_percent: float
    closed_percent: float
    weighted_delivery_percent: float
    delivery_1d_percent: float
    delivery_3d_percent: float
    delivery_7d_percent: float
    open_defects: int
    open_gates: int
    utilization_percent: float
    pickup_latency_seconds: Optional[float]
    queue_depth: int
    oldest_handoff_seconds: Optional[float]
    rework_rate_percent: float
    first_pass_yield_percent: float


class FactoryOverviewResponse(StrictSchema):
    roadmap_digest: str
    roadmap_milestones: int
    metrics: FactoryMetricsResponse
    lanes: list[FactoryLaneResponse]
    generated_at: datetime


class FactoryLaneDrilldownResponse(StrictSchema):
    lane: FactoryLaneResponse
    events: list[dict[str, Any]]
