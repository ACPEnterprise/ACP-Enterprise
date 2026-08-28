"""Commands for the paid-time authority."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from .contracts import PunchKind


@dataclass(frozen=True)
class RecordPunch:
    employee_id: UUID
    branch_id: UUID | None
    kind: PunchKind
    occurred_at: datetime
    timezone: str
    idempotency_key: str | None = None
    source_device_reference: str | None = None


@dataclass(frozen=True)
class RecordManualTime:
    employee_id: UUID
    branch_id: UUID | None
    work_date: date
    timezone: str
    start_at: datetime | None
    end_at: datetime | None
    approved_duration_minutes: int | None
    reason: str
    idempotency_key: str | None = None


@dataclass(frozen=True)
class CorrectTimeEntry:
    revision_id: UUID
    start_at: datetime | None
    end_at: datetime | None
    approved_duration_minutes: int | None
    reason: str


@dataclass(frozen=True)
class CreatePayPeriod:
    period_start: date
    period_end: date
    processing_date: date
    payday: date
    timezone: str
    schedule_definition_id: str
    schedule_version: int
