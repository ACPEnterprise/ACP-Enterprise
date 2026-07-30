from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .contracts import (
    ConnectionState,
    LeasePhase,
    MonitoringState,
    ProjectionAvailability,
)


class StatusSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TimelineEntry(StatusSchema):
    event: str
    occurred_at: datetime


class LeaseStatus(StatusSchema):
    availability: ProjectionAvailability
    worker_id: UUID | None
    status: str | None
    started_at: datetime | None
    expires_at: datetime | None
    released_at: datetime | None
    phase: LeasePhase


class HeartbeatStatus(StatusSchema):
    availability: ProjectionAvailability
    health: str | None
    last_seen: datetime | None
    age_seconds: int | None = Field(ge=0)


class TransportSessionStatus(StatusSchema):
    availability: ProjectionAvailability
    state: str | None
    established_at: datetime | None
    expires_at: datetime | None
    last_contact_at: datetime | None


class ResultStatus(StatusSchema):
    availability: ProjectionAvailability
    status: str | None
    validation_available: bool
    evidence_available: bool
    output_reference_count: int = Field(ge=0)
    failure_classification: str | None
    created_at: datetime | None


class SupervisorStatus(StatusSchema):
    availability: ProjectionAvailability
    state: str | None
    session_state: str | None
    runtime_state: str | None
    credential_status: str
    provider_ready: bool
    ready: bool
    reconnecting: bool
    recovering: bool
    timed_out: bool
    cancelled: bool
    failed: bool
    updated_at: datetime | None
    expires_at: datetime | None
    failure_classification: str | None
    execution_active: bool = False
    command_id: UUID | None = None
    execution_offer_id: UUID | None = None
    provider_session_reference_present: bool = False


class MobileExecutionStatus(StatusSchema):
    command_id: UUID
    ecid: str
    approval_state: str
    monitoring_state: MonitoringState
    execution_available: bool
    execution_connected: bool
    connection_state: ConnectionState
    transport_health: str
    execution_id: UUID | None
    execution_state: str | None
    execution_status: str | None
    progress_label: str
    requested_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime
    lease: LeaseStatus
    heartbeat: HeartbeatStatus
    transport_session: TransportSessionStatus
    result: ResultStatus
    supervisor: SupervisorStatus
    review_available: bool = False
    review_id: UUID | None = None
    review_state: str | None = None
    review_version: int | None = Field(default=None, ge=1)
    review_decided_at: datetime | None = None
    authorization_required: bool = False
    authorization_status: str | None = None
    authorization_id: UUID | None = None
    authorized_at: datetime | None = None
    authorization_expires_at: datetime | None = None
    authorization_revoked_at: datetime | None = None
    authorization_consumed_at: datetime | None = None
    authorized_operation_type: str | None = None
    authorization_eligible: bool = False
    repository_operation_required: bool = False
    repository_operation_id: UUID | None = None
    repository_operation_type: str | None = None
    repository_operation_status: str | None = None
    repository_operation_eligible: bool = False
    repository_operation_expected_branch: str | None = None
    repository_operation_resulting_commit_sha: str | None = None
    repository_operation_requested_at: datetime | None = None
    repository_operation_reserved_at: datetime | None = None
    repository_operation_started_at: datetime | None = None
    repository_operation_completed_at: datetime | None = None
    repository_operation_failed_at: datetime | None = None
    repository_operation_reconciliation_at: datetime | None = None
    repository_operation_failure_classification: str | None = None
    repository_operation_owner_attention_required: bool = False
    timeline: tuple[TimelineEntry, ...]
    terminal: bool
    polling_after_seconds: int | None = Field(ge=5, le=300)
