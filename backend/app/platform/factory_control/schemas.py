# ruff: noqa: UP045 -- keep Pydantic model loading compatible with Python 3.9 tools.
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FactoryEventIn(StrictSchema):
    tenant_company_id: Optional[UUID] = None
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
        "controller_sync",
        "engineering_reopened",
        "beta_reopened",
        "owner_acceptance_reopened",
        "milestone_reopened",
        "integration",
        "beta_deployment",
        "acceptance",
        "release",
        "roadmap_added",
        "roadmap_superseded",
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
    machine: Optional[str] = Field(default=None, min_length=1, max_length=120)
    current_assignment: Optional[str] = Field(
        default=None, min_length=1, max_length=200
    )
    next_queued_item: Optional[str] = Field(default=None, min_length=1, max_length=200)
    controlling_enterprise: Optional[Literal["OM1E", "OM2E", "LaptopE"]] = None
    self_refill_health: Optional[
        Literal[
            "SELF_REFILL_HEALTHY",
            "ELIGIBLE_IDLE",
            "WAITING_INTEGRATION",
            "HUMAN_GATE",
            "PROVIDER_GATE",
            "DEPENDENCY_BLOCKED",
            "RATE_LIMITED",
            "UNSAFE_STOP",
            "UNKNOWN",
        ]
    ] = None
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

    @model_validator(mode="after")
    def require_actionable_gate_evidence(self) -> FactoryEventIn:
        if self.event_type != "gate_opened":
            return self
        required = {
            "gate_id",
            "gate_type",
            "action",
            "why_blocked",
            "workflow",
            "estimated_owner_minutes",
            "resume_action",
            "engineering_prerequisites_resolved",
        }
        if not required.issubset(self.details):
            raise ValueError("gate_opened requires complete actionable gate evidence")
        if self.details.get("engineering_prerequisites_resolved") is not True:
            raise ValueError("owner gate cannot open before engineering prerequisites")
        minutes = self.details.get("estimated_owner_minutes")
        if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes < 1:
            raise ValueError("owner gate requires positive expected minutes")
        return self


class FactoryEventResponse(StrictSchema):
    id: str
    duplicate: bool


class FactorySnapshotIn(StrictSchema):
    snapshot_key: str = Field(min_length=1, max_length=200)
    tenant_company_id: Optional[UUID] = None
    captured_at: datetime
    protected_sha: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    beta_sha: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{40}$")

    @field_validator("captured_at")
    @classmethod
    def require_snapshot_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("captured_at must include a timezone")
        return value


class FactoryLiveLaneTarget(StrictSchema):
    lane_code: Literal["OM1E", "OM2E", "LaptopE"]
    worker_id: UUID
    controlling_enterprise: Literal["OM1E", "OM2E", "LaptopE"]
    lifecycle_state: Literal[
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
    self_refill_health: Literal[
        "SELF_REFILL_HEALTHY",
        "ELIGIBLE_IDLE",
        "WAITING_INTEGRATION",
        "HUMAN_GATE",
        "PROVIDER_GATE",
        "DEPENDENCY_BLOCKED",
        "RATE_LIMITED",
        "UNSAFE_STOP",
        "UNKNOWN",
    ]
    milestone_code: Optional[str] = Field(default=None, min_length=1, max_length=160)
    current_assignment: Optional[str] = Field(
        default=None, min_length=1, max_length=200
    )
    next_queued_item: Optional[str] = Field(default=None, min_length=1, max_length=200)
    queue_depth: int = Field(default=0, ge=0, le=10000)
    last_handoff_at: Optional[datetime] = None
    evidence: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def require_canonical_controller_mapping(self) -> FactoryLiveLaneTarget:
        if self.lane_code != self.controlling_enterprise:
            raise ValueError("lane must map to its canonical controlling Enterprise")
        if (
            self.lifecycle_state in {"ACTIVE", "ASSIGNED", "WAITING_INTEGRATION"}
            and self.current_assignment is None
        ):
            raise ValueError("active controller state requires a current assignment")
        if self.lifecycle_state == "ELIGIBLE_IDLE" and self.current_assignment is not None:
            raise ValueError("eligible idle controller cannot retain an assignment")
        if self.lifecycle_state == "WAITING_INTEGRATION" and self.last_handoff_at is None:
            raise ValueError("waiting integration requires the handoff timestamp")
        if self.last_handoff_at is not None and self.last_handoff_at.tzinfo is None:
            raise ValueError("last_handoff_at must include a timezone")
        return self


class FactoryLiveSyncIn(StrictSchema):
    observed_at: datetime
    targets: list[FactoryLiveLaneTarget] = Field(min_length=1, max_length=3)

    @field_validator("observed_at")
    @classmethod
    def require_observation_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_unique_targets(self) -> FactoryLiveSyncIn:
        lane_codes = [target.lane_code for target in self.targets]
        worker_ids = [target.worker_id for target in self.targets]
        if len(lane_codes) != len(set(lane_codes)) or len(worker_ids) != len(
            set(worker_ids)
        ):
            raise ValueError("live controller targets must be unique")
        return self


class FactoryLaneResponse(StrictSchema):
    lane_code: str
    milestone_code: Optional[str]
    lifecycle_state: str
    queue_depth: int
    machine: Optional[str]
    current_assignment: Optional[str]
    next_queued_item: Optional[str]
    controlling_enterprise: Optional[str]
    self_refill_health: Optional[str]
    idle_duration_seconds: Optional[float]
    sla_state: Literal["HEALTHY", "VIOLATED", "NOT_APPLICABLE"]
    sla_violations: list[str]
    active_since: Optional[datetime]
    last_handoff_at: Optional[datetime]
    last_event_at: datetime


class FactoryMetricsResponse(StrictSchema):
    represented_milestones: int
    superseded_milestones: int
    engineering_count: int
    beta_count: int
    owner_count: int
    closed_count: int
    engineering_percent: float
    beta_percent: float
    owner_percent: float
    closed_percent: float
    engineering_remaining_weight: float
    human_gated_remaining_weight: float
    provider_gated_remaining_weight: float
    weighted_delivery_percent: float
    delivery_1d_percent: float
    delivery_3d_percent: float
    delivery_7d_percent: float
    open_defects: int
    defects_discovered: int
    defects_closed: int
    defects_reopened: int
    open_gates: int
    utilization_percent: float
    effective_utilization_percent: float
    eligible_idle_seconds: float
    pickup_latency_seconds: Optional[float]
    domain_pickup_latency_seconds: Optional[float]
    release_pickup_latency_seconds: Optional[float]
    release_latency_seconds: Optional[float]
    queue_depth: int
    oldest_handoff_seconds: Optional[float]
    rework_rate_percent: float
    first_pass_yield_percent: float
    event_history_status: Literal["MEASURED", "NOT_YET_MEASURED"]
    lane_history_status: Literal["MEASURED", "NOT_YET_MEASURED"]
    velocity_history_status: Literal["MEASURED", "NOT_YET_MEASURED"]


class OperationalAcceptanceSurfaceResponse(StrictSchema):
    acceptance_id: str
    surface: str
    milestone_code: str
    owner_task: str
    real_data_required: str
    current_result: str
    blocker: str
    owning_domain: str
    priority: Literal["P0", "P1", "P2", "P3"]
    status: Literal[
        "NOT_TESTED",
        "PASS",
        "DEFECT",
        "HUMAN_INPUT_REQUIRED",
        "PROVIDER_GATE",
    ]
    beta_operable: bool
    owner_accepted: bool
    evidence: list[str]


class FactoryOverviewResponse(StrictSchema):
    roadmap_digest: str
    roadmap_milestones: int
    metrics: FactoryMetricsResponse
    lanes: list[FactoryLaneResponse]
    generated_at: datetime
    p0_backlog: int
    p1_backlog: int
    human_gates: int
    provider_gates: int
    owner_actions: list[dict[str, Any]]
    lifecycle_counts: dict[str, int]
    active_p0: list[dict[str, Any]]
    active_p1: list[dict[str, Any]]
    current_bottleneck: Optional[dict[str, Any]]
    recent_movements: list[dict[str, Any]]
    latest_snapshot_at: Optional[datetime]
    last_controller_ingestion_at: Optional[datetime]
    telemetry_freshness: Literal["LIVE", "STALE", "NOT_YET_MEASURED"]
    real_operational_acceptance: list[OperationalAcceptanceSurfaceResponse]


class FactoryLaneDrilldownResponse(StrictSchema):
    lane: FactoryLaneResponse
    events: list[dict[str, Any]]
