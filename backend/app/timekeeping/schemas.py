"""Phone-safe HTTP contracts for authoritative Workday Time."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import PayrollInputExclusionReason, PunchKind, TimeCorrectionKind
from .job_participation import (
    CorrectionState,
    IntervalConfidence,
    IntervalValidity,
    JobClockKind,
    WorkedIntervalSource,
)


class PunchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: PunchKind
    device_reference: str | None = Field(default=None, max_length=200)


class JobClockInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: JobClockKind
    job_id: UUID
    appointment_id: UUID | None = None


class JobWorkedIntervalView(BaseModel):
    interval_id: UUID
    revision_id: UUID
    revision_number: int
    employee_id: UUID
    job_id: UUID
    appointment_id: UUID | None
    start_at: datetime
    stop_at: datetime
    duration_seconds: int
    source: WorkedIntervalSource
    correction_state: CorrectionState
    supersedes_revision_id: UUID | None
    audit_lineage: tuple[UUID, ...]
    source_event_ids: tuple[UUID, ...]
    validity: IntervalValidity
    confidence: IntervalConfidence
    evidence_digest: str
    correction_reason: str | None
    corrected_by_user_id: UUID | None


class ActiveJobClockView(BaseModel):
    active: bool
    event_id: UUID | None = None
    employee_id: UUID
    job_id: UUID | None = None
    appointment_id: UUID | None = None
    started_at: datetime | None = None
    server_observed_at: datetime
    elapsed_seconds: int | None = None
    latest_action: JobClockKind | None = None
    latest_event_id: UUID | None = None
    latest_occurred_at: datetime | None = None
    latest_completed_interval_id: UUID | None = None


class JobClockResult(BaseModel):
    event_id: UUID
    action: JobClockKind
    occurred_at: datetime
    state: ActiveJobClockView
    completed_interval: JobWorkedIntervalView | None


class JobWorkedIntervalCorrectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_at: datetime
    stop_at: datetime
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def valid_interval(self) -> "JobWorkedIntervalCorrectionInput":
        if self.start_at.tzinfo is None or self.stop_at.tzinfo is None:
            raise ValueError("Job worked timestamps must be timezone-aware")
        if self.stop_at <= self.start_at:
            raise ValueError("stop_at must follow start_at")
        return self


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
    correction_kind: TimeCorrectionKind

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
    correction_kind: str | None
    reviewed_by_user_id: UUID
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
    job_intervals: tuple[JobWorkedIntervalView, ...] = ()


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


class PayrollInputEvidenceItem(BaseModel):
    entry_id: UUID | None
    revision_id: UUID | None
    state: str
    eligible: bool
    reason: PayrollInputExclusionReason | None
    approved_minutes: int | None
    evidence_digest: str | None


class PayrollInputProjectionView(BaseModel):
    version: str
    employee_id: UUID
    pay_period_id: UUID
    included: tuple[PayrollInputEvidenceItem, ...]
    excluded: tuple[PayrollInputEvidenceItem, ...]
    total_eligible_minutes: int
    projection_digest: str


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
    entries: tuple[TimeEntryView, ...]


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
    job_intervals: tuple[JobWorkedIntervalView, ...] = ()
    days: tuple[AdminTimecardDay, ...]
    total_supported_minutes: int
    accepted_minutes: int
    exception_codes: tuple[str, ...]
    review_state: Literal["ACCEPTED", "NEEDS_REVIEW"]


class AdminTimecardOperations(BaseModel):
    contract_version: Literal["WORKFORCE.TIMECARD.OPERATIONS.v1"]
    pay_period: PayPeriodView
    employees: tuple[AdminEmployeeTimecard, ...]
    job_attribution_readiness: Literal["AVAILABLE"]
    limitations: tuple[str, ...]


class JobLaborActualItem(BaseModel):
    employee_id: UUID
    employee_number: str
    employee_name: str
    interval: JobWorkedIntervalView
    evidence_state: Literal["ACCEPTED", "NEEDS_REVIEW"]
    paid_time_reconciliation: Literal[
        "WITHIN_ACCEPTED_PAID_TIME",
        "PARTIAL_ACCEPTED_PAID_OVERLAP",
        "OUTSIDE_ACCEPTED_PAID_TIME",
        "PAID_TIME_UNAVAILABLE",
    ]
    exception_codes: tuple[str, ...]


class JobLaborActualsQueue(BaseModel):
    contract_version: Literal["WORKFORCE.JOB.LABOR.ACTUALS.v1"]
    pay_period: PayPeriodView
    accepted_interval_count: int
    review_interval_count: int
    total_accepted_seconds: int
    items: tuple[JobLaborActualItem, ...]
    limitations: tuple[str, ...]
