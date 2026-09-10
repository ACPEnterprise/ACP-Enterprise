"""Phone-safe HTTP contracts for authoritative Workday Time."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import PunchKind


class PunchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: PunchKind
    device_reference: str | None = Field(default=None, max_length=200)


class ManualTimeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    work_date: date
    timezone: str = Field(min_length=1, max_length=80)
    start_at: datetime | None = None
    end_at: datetime | None = None
    approved_duration_minutes: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_time_shape(self) -> "ManualTimeInput":
        if self.approved_duration_minutes is None and (
            self.start_at is None or self.end_at is None
        ):
            raise ValueError("start/end or approved duration is required")
        return self


class CorrectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_at: datetime | None = None
    end_at: datetime | None = None
    approved_duration_minutes: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_time_shape(self) -> "CorrectionInput":
        if self.approved_duration_minutes is None and (
            self.start_at is None or self.end_at is None
        ):
            raise ValueError("start/end or approved duration is required")
        return self


class PunchState(BaseModel):
    state: Literal["not_clocked_in", "clocked_in", "on_break"]
    last_action: PunchKind | None
    occurred_at: datetime | None
    server_observed_at: datetime
    elapsed_seconds: int | None


class TimeEntryView(BaseModel):
    entry_id: UUID
    revision_id: UUID
    revision_number: int
    work_date: date
    timezone: str
    provenance: str
    start_at: datetime | None
    end_at: datetime | None
    approved_duration_minutes: int | None
    state: str
    supersedes_revision_id: UUID | None
    correction_reason: str | None
    approved_at: datetime | None


class PayPeriodView(BaseModel):
    id: UUID
    period_start: date
    period_end: date
    processing_date: date
    payday: date
    timezone: str
    schedule_definition_id: str
    schedule_version: int


class TimecardView(BaseModel):
    employee_id: UUID
    punch_state: PunchState
    pay_period: PayPeriodView | None
    entries: tuple[TimeEntryView, ...]


class PunchResult(BaseModel):
    punch_id: UUID
    action: PunchKind
    occurred_at: datetime
    state: PunchState
    completed_entry: TimeEntryView | None


class PayrollTimeInputView(BaseModel):
    snapshot_id: str
    version: str
    employee_id: UUID
    pay_period_id: UUID
    period_start: date
    period_end: date
    approved_revision_ids: tuple[UUID, ...]
    total_approved_minutes: int
    snapshot_digest: str


class AdminTimecardReviewItem(BaseModel):
    employee_id: UUID
    employee_number: str
    display_name: str
    home_branch_id: UUID | None
    entry_count: int
    total_minutes: int
    exception_codes: tuple[
        Literal["no_time", "unsubmitted", "corrected", "overlap"], ...
    ]


class AdminTimecardReview(BaseModel):
    pay_period: PayPeriodView | None
    items: tuple[AdminTimecardReviewItem, ...]


class AdminTimecardInterval(BaseModel):
    entry_id: UUID
    revision_id: UUID
    revision_number: int
    work_date: date
    start_at: datetime | None
    end_at: datetime | None
    supported_minutes: int
    job_id: UUID | None = None
    job_number: str | None = None
    job_minutes: int | None = None
    non_job_supported_minutes: int | None = None
    attribution_state: Literal["ATTRIBUTED", "NON_JOB", "UNCLASSIFIED"]
    provenance: str
    entry_state: str
    corrected: bool
    overlap: bool
    review_state: Literal["ACCEPTED", "NEEDS_REVIEW"]
    audit_digest: str


class AdminTimecardDay(BaseModel):
    work_date: date
    intervals: tuple[AdminTimecardInterval, ...]
    total_supported_minutes: int
    job_minutes: int | None
    non_job_supported_minutes: int | None
    unclassified_minutes: int
    has_overlap: bool
    has_correction: bool
    review_state: Literal["ACCEPTED", "NEEDS_REVIEW"]


class AdminEmployeeTimecard(BaseModel):
    employee_id: UUID
    employee_number: str
    display_name: str
    home_branch_id: UUID | None
    punch_state: PunchState
    active_open_clock: bool
    missing_clock_out: bool
    days: tuple[AdminTimecardDay, ...]
    total_supported_minutes: int
    accepted_minutes: int
    exception_codes: tuple[str, ...]
    review_state: Literal["ACCEPTED", "NEEDS_REVIEW"]


class AdminTimecardOperations(BaseModel):
    contract_version: Literal["WORKFORCE.TIMECARD.OPERATIONS.v1"]
    pay_period: PayPeriodView
    employees: tuple[AdminEmployeeTimecard, ...]
    job_attribution_readiness: Literal["PARTIAL"]
    limitations: tuple[str, ...]
