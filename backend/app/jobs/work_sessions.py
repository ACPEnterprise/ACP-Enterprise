"""Canonical Job planning and field-activity rules.

These facts attribute activity inside a Job visit.  They never establish paid time;
Workday Time remains the sole payable-time authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID


class JobWorkSessionError(ValueError):
    """Raised when Job activity evidence cannot be proven."""


class WorkPattern(StrEnum):
    SINGLE_VISIT = "single_visit"
    MULTI_DAY = "multi_day"
    PROJECT = "project"


class JobActivity(StrEnum):
    WORKING = "working"
    PARTS_RUN = "parts_run"


class ActivityAction(StrEnum):
    START = "start"
    CHANGE = "change"
    FINISH_VISIT = "finish_visit"


class ContinuationReason(StrEnum):
    PARTS_MATERIAL = "parts_material"
    ADDITIONAL_LABOR = "additional_labor"
    RETURN_VISIT = "return_visit"
    MULTI_DAY_PLANNED = "multi_day_planned"
    INSPECTION_PERMIT = "inspection_permit"
    CUSTOMER_AVAILABILITY = "customer_availability"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class JobPlan:
    pattern: WorkPattern | None = None
    estimated_technician_labor_minutes: int | None = None
    estimated_visits: int | None = None
    planned_start: date | None = None
    target_completion: date | None = None

    def __post_init__(self) -> None:
        if self.estimated_technician_labor_minutes is not None and self.estimated_technician_labor_minutes <= 0:
            raise JobWorkSessionError("estimated technician labor must be positive")
        if self.estimated_visits is not None and self.estimated_visits <= 0:
            raise JobWorkSessionError("estimated visits must be positive")
        if self.planned_start and self.target_completion and self.target_completion < self.planned_start:
            raise JobWorkSessionError("target completion cannot precede planned start")


@dataclass(frozen=True, slots=True)
class JobActivityEvent:
    event_id: UUID
    company_id: UUID
    branch_id: UUID
    employee_id: UUID
    job_id: UUID
    appointment_id: UUID
    action: ActivityAction
    activity: JobActivity | None
    occurred_at: datetime
    job_version: int
    appointment_version: int
    idempotency_key: str
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class JobActivityInterval:
    company_id: UUID
    branch_id: UUID
    employee_id: UUID
    job_id: UUID
    appointment_id: UUID
    activity: JobActivity
    start_at: datetime
    stop_at: datetime
    start_event_id: UUID
    stop_event_id: UUID

    @property
    def duration_seconds(self) -> int:
        return int((self.stop_at - self.start_at).total_seconds())


@dataclass(frozen=True, slots=True)
class JobContinuation:
    company_id: UUID
    branch_id: UUID
    employee_id: UUID
    job_id: UUID
    appointment_id: UUID
    reason: ContinuationReason
    requested_return_date: date | None
    needs_scheduling: bool
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.needs_scheduling and self.requested_return_date is None:
            raise JobWorkSessionError("a scheduled continuation requires a return date")
        if self.reason is ContinuationReason.OTHER and not (self.note and self.note.strip()):
            raise JobWorkSessionError("other continuation reason requires a note")


def derive_activity_intervals(events: tuple[JobActivityEvent, ...]) -> tuple[JobActivityInterval, ...]:
    """Derive exact activity intervals; reject ambiguous, replayed, or cross-scope evidence."""

    by_key: dict[tuple[UUID, UUID, str], JobActivityEvent] = {}
    by_id: dict[UUID, str] = {}
    for event in events:
        if event.occurred_at.tzinfo is None:
            raise JobWorkSessionError("activity timestamp must be timezone-aware")
        if event.job_version < 1 or event.appointment_version < 1:
            raise JobWorkSessionError("activity evidence must bind positive versions")
        if not event.idempotency_key or not event.evidence_digest:
            raise JobWorkSessionError("activity evidence requires idempotency and digest")
        prior_digest = by_id.setdefault(event.event_id, event.evidence_digest)
        if prior_digest != event.evidence_digest:
            raise JobWorkSessionError("contradictory activity event identity")
        replay_key = (event.company_id, event.employee_id, event.idempotency_key)
        prior = by_key.setdefault(replay_key, event)
        if prior.evidence_digest != event.evidence_digest:
            raise JobWorkSessionError("contradictory activity replay")

    ordered = sorted(by_key.values(), key=lambda value: (value.occurred_at, str(value.event_id)))
    active: JobActivityEvent | None = None
    intervals: list[JobActivityInterval] = []
    for event in ordered:
        if event.action is ActivityAction.START:
            if event.activity is None or active is not None:
                raise JobWorkSessionError("activity start requires no existing active activity")
            active = event
            continue
        if active is None:
            raise JobWorkSessionError("activity transition requires an active activity")
        scope = (event.company_id, event.branch_id, event.employee_id, event.job_id, event.appointment_id)
        active_scope = (active.company_id, active.branch_id, active.employee_id, active.job_id, active.appointment_id)
        if scope != active_scope:
            raise JobWorkSessionError("activity transition scope differs from active visit")
        if event.occurred_at <= active.occurred_at:
            raise JobWorkSessionError("activity transition must follow active activity")
        intervals.append(JobActivityInterval(*scope, active.activity, active.occurred_at, event.occurred_at, active.event_id, event.event_id))  # type: ignore[arg-type]
        if event.action is ActivityAction.CHANGE:
            if event.activity is None or event.activity is active.activity:
                raise JobWorkSessionError("activity change requires a different activity")
            active = event
        elif event.action is ActivityAction.FINISH_VISIT:
            if event.activity is not None:
                raise JobWorkSessionError("finish visit cannot start another activity")
            active = None
        else:
            raise JobWorkSessionError("unsupported activity action")
    if active is not None:
        raise JobWorkSessionError("visit has an open activity")
    return tuple(intervals)
