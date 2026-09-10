"""Phone-safe HTTP contracts for authoritative Workday Time."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import PunchKind, TimeCorrectionKind


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
    entries: tuple[TimeEntryView, ...]


class AdminTimecardReview(BaseModel):
    pay_period: PayPeriodView | None
    items: tuple[AdminTimecardReviewItem, ...]
