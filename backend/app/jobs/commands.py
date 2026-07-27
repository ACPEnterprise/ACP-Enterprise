from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

from app.jobs.types import (
    JobCancellationReason,
    JobPauseReason,
    JobPriority,
    JobReopeningReason,
)


class UnsetType(Enum):
    UNSET = "unset"


UNSET = UnsetType.UNSET
OptionalTextUpdate = str | None | UnsetType


@dataclass(frozen=True)
class CreateJob:
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    job_type_code: str | None = None
    priority: JobPriority = JobPriority.NORMAL
    customer_reported_problem: str | None = None
    internal_description: str | None = None


@dataclass(frozen=True)
class MigrateJob:
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    status: str
    priority: JobPriority = JobPriority.NORMAL
    customer_reported_problem: str | None = None
    internal_description: str | None = None
    activated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True)
class CreateJobFromAppointment:
    appointment_id: UUID
    job_type_code: str | None = None
    priority: JobPriority = JobPriority.NORMAL
    customer_reported_problem: str | None = None
    internal_description: str | None = None


@dataclass(frozen=True)
class UpdateJob:
    job_id: UUID
    expected_version: int
    customer_id: UUID | UnsetType = UNSET
    service_location_id: UUID | UnsetType = UNSET
    job_type_code: OptionalTextUpdate = UNSET
    priority: JobPriority | UnsetType = UNSET
    customer_reported_problem: OptionalTextUpdate = UNSET
    internal_description: OptionalTextUpdate = UNSET


@dataclass(frozen=True)
class ActivateJob:
    job_id: UUID
    expected_version: int


@dataclass(frozen=True)
class LinkAppointment:
    job_id: UUID
    appointment_id: UUID
    visit_sequence: int
    expected_version: int


@dataclass(frozen=True)
class StartJob:
    job_id: UUID
    expected_version: int


@dataclass(frozen=True)
class PauseJob:
    job_id: UUID
    expected_version: int
    reason_code: JobPauseReason


@dataclass(frozen=True)
class ResumeJob:
    job_id: UUID
    expected_version: int


@dataclass(frozen=True)
class CompleteJob:
    job_id: UUID
    expected_version: int


@dataclass(frozen=True)
class CancelJob:
    job_id: UUID
    expected_version: int
    reason_code: JobCancellationReason


@dataclass(frozen=True)
class ReopenJob:
    job_id: UUID
    expected_version: int
    reason_code: JobReopeningReason
