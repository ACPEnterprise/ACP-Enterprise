from datetime import datetime
from typing import Literal
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
    ready: bool
    reconnecting: bool
    recovering: bool
    timed_out: bool
    cancelled: bool
    failed: bool
    updated_at: datetime | None
    expires_at: datetime | None
    failure_classification: str | None


class MobileExecutionStatus(StatusSchema):
    command_id: UUID
    ecid: str
    approval_state: str
    monitoring_state: MonitoringState
    execution_available: bool
    execution_connected: Literal[False]
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
    timeline: tuple[TimelineEntry, ...]
    terminal: bool
    polling_after_seconds: int | None = Field(ge=5, le=300)
