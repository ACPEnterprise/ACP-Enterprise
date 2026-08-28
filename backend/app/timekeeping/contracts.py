"""Immutable contracts for paid time and future Payroll handoff."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

WORKDAY_TIME_DEFINITION_VERSION = "time.workday-authority.v1"
PAYROLL_TIME_INPUT_VERSION = "payroll.time-input.v1"


class TimeEntryProvenance(StrEnum):
    EMPLOYEE_PUNCH = "employee_punch"
    AUTHORIZED_MANUAL_ENTRY = "authorized_manual_entry"


class PunchKind(StrEnum):
    CLOCK_IN = "clock_in"
    CLOCK_OUT = "clock_out"
    BREAK_START = "break_start"
    BREAK_END = "break_end"


class TimeEntryState(StrEnum):
    RECORDED = "recorded"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    CORRECTED = "corrected"


class WorkdayTimeError(ValueError):
    pass


class WorkdayAuthorizationError(PermissionError):
    pass


class WorkdayConflictError(WorkdayTimeError):
    pass


def canonical_digest(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ApprovedWorkdayTimeFact:
    entry_id: UUID
    revision_id: UUID
    revision_number: int
    company_id: UUID
    branch_id: UUID | None
    employee_id: UUID
    work_date: date
    timezone: str
    provenance: TimeEntryProvenance
    start_at: datetime | None
    end_at: datetime | None
    approved_duration_minutes: int
    punch_event_ids: tuple[UUID, ...]
    correction_lineage: tuple[UUID, ...]
    entered_by_user_id: UUID | None
    approval_id: UUID
    approved_by_user_id: UUID
    approved_at: datetime
    evidence_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "definition_version": WORKDAY_TIME_DEFINITION_VERSION,
            "entry_id": str(self.entry_id),
            "revision_id": str(self.revision_id),
            "revision_number": self.revision_number,
            "company_id": str(self.company_id),
            "branch_id": str(self.branch_id) if self.branch_id else None,
            "employee_id": str(self.employee_id),
            "work_date": self.work_date.isoformat(),
            "timezone": self.timezone,
            "provenance": self.provenance.value,
            "start_at": self.start_at.isoformat() if self.start_at else None,
            "end_at": self.end_at.isoformat() if self.end_at else None,
            "approved_duration_minutes": self.approved_duration_minutes,
            "punch_event_ids": tuple(str(value) for value in self.punch_event_ids),
            "correction_lineage": tuple(
                str(value) for value in self.correction_lineage
            ),
            "entered_by_user_id": (
                str(self.entered_by_user_id) if self.entered_by_user_id else None
            ),
            "approval_id": str(self.approval_id),
            "approved_by_user_id": str(self.approved_by_user_id),
            "approved_at": self.approved_at.isoformat(),
        }

    def verify(self) -> None:
        if self.approved_duration_minutes < 0:
            raise WorkdayTimeError("approved duration cannot be negative")
        if canonical_digest(self.canonical_content()) != self.evidence_digest:
            raise WorkdayTimeError("approved Workday Time digest mismatch")


@dataclass(frozen=True)
class PayrollTimeInputSnapshot:
    snapshot_id: str
    version: str
    company_id: UUID
    employee_id: UUID
    pay_period_id: UUID
    period_start: date
    period_end: date
    approved_entries: tuple[ApprovedWorkdayTimeFact, ...]
    total_approved_minutes: int
    approval_evidence_digests: tuple[str, ...]
    snapshot_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "version": self.version,
            "company_id": str(self.company_id),
            "employee_id": str(self.employee_id),
            "pay_period_id": str(self.pay_period_id),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "entry_digests": tuple(
                value.evidence_digest for value in self.approved_entries
            ),
            "total_approved_minutes": self.total_approved_minutes,
            "approval_evidence_digests": self.approval_evidence_digests,
        }

    def verify(self) -> None:
        for entry in self.approved_entries:
            entry.verify()
            if (
                entry.company_id != self.company_id
                or entry.employee_id != self.employee_id
            ):
                raise WorkdayTimeError("Payroll Time Input scope mismatch")
        if self.total_approved_minutes != sum(
            entry.approved_duration_minutes for entry in self.approved_entries
        ):
            raise WorkdayTimeError("Payroll Time Input total mismatch")
        digest = canonical_digest(self.canonical_content())
        if self.snapshot_id != f"payroll-time-input:{digest}":
            raise WorkdayTimeError("Payroll Time Input identity mismatch")
        if self.snapshot_digest != digest:
            raise WorkdayTimeError("Payroll Time Input digest mismatch")


def seal_payroll_time_input(
    *,
    company_id: UUID,
    employee_id: UUID,
    pay_period_id: UUID,
    period_start: date,
    period_end: date,
    approved_entries: tuple[ApprovedWorkdayTimeFact, ...],
) -> PayrollTimeInputSnapshot:
    ordered = tuple(
        sorted(
            approved_entries, key=lambda value: (value.work_date, str(value.entry_id))
        )
    )
    if not ordered:
        raise WorkdayTimeError(
            "Payroll Time Input requires approved evidence; missing is not zero"
        )
    draft = PayrollTimeInputSnapshot(
        snapshot_id="",
        version=PAYROLL_TIME_INPUT_VERSION,
        company_id=company_id,
        employee_id=employee_id,
        pay_period_id=pay_period_id,
        period_start=period_start,
        period_end=period_end,
        approved_entries=ordered,
        total_approved_minutes=sum(
            value.approved_duration_minutes for value in ordered
        ),
        approval_evidence_digests=tuple(value.evidence_digest for value in ordered),
        snapshot_digest="",
    )
    digest = canonical_digest(draft.canonical_content())
    result = PayrollTimeInputSnapshot(
        **{
            **draft.__dict__,
            "snapshot_id": f"payroll-time-input:{digest}",
            "snapshot_digest": digest,
        }
    )
    result.verify()
    return result


def duration_minutes(
    start_at: datetime | None,
    end_at: datetime | None,
    approved_duration_minutes: int | None,
) -> int:
    if approved_duration_minutes is not None:
        if approved_duration_minutes < 0:
            raise WorkdayTimeError("duration cannot be negative")
        return approved_duration_minutes
    if start_at is None or end_at is None or end_at <= start_at:
        raise WorkdayTimeError("valid start/end or approved duration is required")
    return int(Decimal((end_at - start_at).total_seconds()) / Decimal(60))
