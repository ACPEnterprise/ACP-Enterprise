from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

CapacityDecision = Literal[
    "capacity_available",
    "waiting_for_capacity",
    "reserved",
    "allocated",
    "blocked_by_policy",
    "blocked_by_worker_health",
    "reconciliation_required",
]


class CapacitySchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CapacityPolicyResponse(CapacitySchema):
    id: UUID
    maximum_concurrent_workstreams: int
    maximum_per_worker: int
    reserved_capacity: int
    auto_allocate_released_capacity: bool
    version: int
    updated_at: datetime


class CapacityPolicyUpdate(CapacitySchema):
    maximum_concurrent_workstreams: int = Field(ge=1, le=100)
    maximum_per_worker: int = Field(ge=1, le=20)
    reserved_capacity: int = Field(ge=0, le=100)
    auto_allocate_released_capacity: bool = False
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_limits(self) -> "CapacityPolicyUpdate":
        if self.reserved_capacity > self.maximum_concurrent_workstreams:
            raise ValueError("Reserved capacity cannot exceed total capacity.")
        if self.maximum_per_worker > self.maximum_concurrent_workstreams:
            raise ValueError("Per-worker capacity cannot exceed total capacity.")
        return self


class CapacityMachineResponse(CapacitySchema):
    id: UUID
    machine_label: str
    expected_available_on: date | None
    enrollment_state: str
    worker_id: UUID | None


class CapacityBaselineRequest(CapacitySchema):
    machine_label: str = Field(min_length=1, max_length=120)
    expected_available_on: date | None = None


class WorkerCapacityResponse(CapacitySchema):
    id: UUID
    worker_id: UUID
    machine_id: UUID
    machine_label: str
    configured_limit: int
    allocated_capacity: int
    reserved_capacity: int
    available_capacity: int
    operational_state: str
    health_state: str
    last_reconciled_at: datetime | None
    version: int


class WorkerCapacityUpdate(CapacitySchema):
    configured_limit: int = Field(ge=1, le=20)
    expected_version: int = Field(ge=1)


class WorkerCapacityRegister(CapacitySchema):
    worker_id: UUID
    machine_id: UUID
    configured_limit: int = Field(default=1, ge=1, le=20)
    idempotency_key: str = Field(min_length=8, max_length=128)


class ExistingWorkerCapacitySetup(CapacitySchema):
    worker_id: UUID
    machine_label: str = Field(min_length=1, max_length=120)
    configured_limit: int = Field(default=1, ge=1, le=20)
    idempotency_key: str = Field(min_length=8, max_length=128)


class EligibleWorkerResponse(CapacitySchema):
    worker_id: UUID
    worker_name: str
    provider_identifier: str
    lifecycle_state: str
    identity_name: str
    identity_state: str
    last_heartbeat_at: datetime | None
    health_state: str
    capacity_configured: bool


class PermanentCapacityResponse(CapacitySchema):
    id: UUID
    identity_code: str
    display_name: str
    state: str
    reconciliation_reason: str | None
    version: int


class PermanentCapacityBindingResponse(CapacitySchema):
    id: UUID
    permanent_capacity_id: UUID
    worker_capacity_id: UUID
    state: str
    evidence: dict[str, object]
    version: int


class PermanentCapacityBindingRequest(CapacitySchema):
    identity_code: Literal["OM1", "OM2", "MIG", "ECO", "LAP"]
    worker_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)


class WorkerStateUpdate(CapacitySchema):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=200)


class CapacityReservationRequest(CapacitySchema):
    command_id: UUID
    worker_id: UUID | None = None
    owner_intent_reference: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=128)
    transition_source: Literal["owner", "automatic", "system"] = "owner"


class CapacityAllocationRequest(CapacitySchema):
    reservation_id: UUID
    execution_id: UUID | None = None
    idempotency_key: str = Field(min_length=8, max_length=128)
    transition_source: Literal["owner", "automatic", "system"] = "system"


class CapacityReleaseRequest(CapacitySchema):
    idempotency_key: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=1, max_length=200)
    expected_version: int = Field(ge=1)


class CapacityReconciliationRequest(CapacitySchema):
    resolution: Literal["confirmed_active", "confirmed_released"]
    reason: str = Field(min_length=1, max_length=200)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)


class CapacityReservationResponse(CapacitySchema):
    id: UUID
    command_id: UUID
    execution_id: UUID | None
    worker_capacity_id: UUID
    machine_label: str
    ecid: str | None = None
    milestone_title: str | None = None
    milestone_position: int | None = None
    workstream: str | None = None
    owning_branch: str | None = None
    owner_intent_reference: str
    status: str
    transition_source: str
    requested_at: datetime
    reserved_at: datetime
    released_at: datetime | None
    release_reason: str | None
    version: int


class CapacityAllocationResponse(CapacitySchema):
    id: UUID
    reservation_id: UUID
    command_id: UUID
    execution_id: UUID | None
    worker_capacity_id: UUID
    machine_label: str
    ecid: str | None = None
    milestone_title: str | None = None
    milestone_position: int | None = None
    workstream: str | None = None
    owning_branch: str | None = None
    status: str
    transition_source: str
    allocated_at: datetime
    released_at: datetime | None
    release_reason: str | None
    version: int


class CapacityQueueItem(CapacitySchema):
    command_id: UUID
    ecid: str
    repository_key: str
    expected_branch: str
    milestone_id: UUID | None
    milestone_title: str | None
    milestone_position: int | None
    workstream: str | None
    roadmap_title: str | None
    owning_branch: str | None
    identity_state: Literal["resolved", "reconciliation_required"]
    assigned_worker_id: UUID | None
    assigned_worker_name: str | None
    machine_label: str | None
    capacity_amount: int
    requested_at: datetime
    decision: CapacityDecision
    reason: str


class CapacitySummaryResponse(CapacitySchema):
    policy: CapacityPolicyResponse | None
    configured_capacity: int
    allocated_capacity: int
    reserved_capacity: int
    numeric_available_capacity: int
    available_capacity: int
    offline_workers: int
    unhealthy_workers: int
    reconciliation_required: int
    workers: tuple[WorkerCapacityResponse, ...]
    eligible_workers: tuple[EligibleWorkerResponse, ...]
    machines: tuple[CapacityMachineResponse, ...]
    active_reservations: tuple[CapacityReservationResponse, ...]
    active_allocations: tuple[CapacityAllocationResponse, ...]
    waiting_workstreams: tuple[CapacityQueueItem, ...]
    permanent_capacities: tuple[PermanentCapacityResponse, ...] = ()
    permanent_capacity_bindings: tuple[PermanentCapacityBindingResponse, ...] = ()
