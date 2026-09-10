"""Deterministic Job Participation evidence reconciled to approved paid time.

Workday Time remains the authority for paid minutes.  Participation assertions only
attribute portions of an approved time-entry revision to a Job or an explicit non-Job
activity; they cannot create paid time, compensation, withholding, or Payroll results.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from itertools import pairwise
from uuid import UUID, uuid5

CONTRACT_VERSION = "timekeeping.job-participation-reconciliation.v1"
INTERVAL_CONTRACT_VERSION = "timekeeping.job-worked-interval.v1"
INTERVAL_NAMESPACE = UUID("79d5c21e-061c-4a94-99dc-0d8ce811e250")


class JobParticipationError(ValueError):
    pass


class ParticipationKind(StrEnum):
    JOB = "job"
    TRAVEL = "travel"
    NONPRODUCTIVE = "nonproductive"


class JobClockKind(StrEnum):
    START = "start"
    STOP = "stop"


class WorkedIntervalSource(StrEnum):
    EMPLOYEE_CLOCK = "employee_clock"
    AUTHORIZED_MANUAL = "authorized_manual"


class CorrectionState(StrEnum):
    ORIGINAL = "original"
    CORRECTED = "corrected"
    SUPERSEDED = "superseded"


class IntervalValidity(StrEnum):
    VALID = "valid"
    CORRECTION_REQUIRED = "correction_required"


class IntervalConfidence(StrEnum):
    AUTHORITATIVE = "authoritative"
    DISPUTED = "disputed"


@dataclass(frozen=True, slots=True)
class JobClockEvent:
    event_id: UUID
    idempotency_key: str
    request_digest: str
    company_id: UUID
    branch_id: UUID | None
    employee_id: UUID
    job_id: UUID
    appointment_id: UUID | None
    kind: JobClockKind
    occurred_at: datetime
    recorded_by_user_id: UUID
    source: WorkedIntervalSource = WorkedIntervalSource.EMPLOYEE_CLOCK


@dataclass(frozen=True, slots=True)
class JobWorkedInterval:
    interval_id: UUID
    revision_id: UUID
    revision_number: int
    company_id: UUID
    branch_id: UUID | None
    employee_id: UUID
    job_id: UUID
    appointment_id: UUID | None
    start_at: datetime
    stop_at: datetime
    duration_minutes: int
    source: WorkedIntervalSource
    correction_state: CorrectionState
    supersedes_revision_id: UUID | None
    audit_lineage: tuple[UUID, ...]
    source_event_ids: tuple[UUID, ...]
    validity: IntervalValidity
    confidence: IntervalConfidence
    evidence_digest: str
    correction_reason: str | None = None


def derive_job_worked_intervals(
    events: tuple[JobClockEvent, ...],
) -> tuple[JobWorkedInterval, ...]:
    """Pair authoritative Job clock events without consulting schedules or paid time."""

    replay: dict[tuple[UUID, UUID, str], JobClockEvent] = {}
    event_ids: dict[UUID, str] = {}
    for event in events:
        _validate_clock_event(event)
        previous_digest = event_ids.setdefault(event.event_id, event.request_digest)
        if previous_digest != event.request_digest:
            raise JobParticipationError("contradictory clock event replay")
        key = (event.company_id, event.recorded_by_user_id, event.idempotency_key)
        previous = replay.get(key)
        if previous is not None and previous.request_digest != event.request_digest:
            raise JobParticipationError("contradictory idempotency replay")
        replay.setdefault(key, event)

    ordered = sorted(
        replay.values(), key=lambda value: (value.occurred_at, str(value.event_id))
    )
    active: dict[tuple[UUID, UUID], JobClockEvent] = {}
    intervals: list[JobWorkedInterval] = []
    for event in ordered:
        employee_scope = (event.company_id, event.employee_id)
        if event.kind is JobClockKind.START:
            if employee_scope in active:
                raise JobParticipationError(
                    "employee already has an active Job interval"
                )
            active[employee_scope] = event
            continue
        start = active.pop(employee_scope, None)
        if start is None:
            raise JobParticipationError("Job clock stop has no active interval")
        if (start.job_id, start.appointment_id, start.branch_id) != (
            event.job_id,
            event.appointment_id,
            event.branch_id,
        ):
            raise JobParticipationError("Job clock stop scope does not match start")
        if event.occurred_at <= start.occurred_at:
            raise JobParticipationError("Job clock stop must follow start")
        interval_id = uuid5(
            INTERVAL_NAMESPACE,
            f"{start.company_id}:{start.employee_id}:{start.event_id}:{event.event_id}",
        )
        revision_id = uuid5(INTERVAL_NAMESPACE, f"{interval_id}:1")
        intervals.append(
            _seal_interval(
                interval_id=interval_id,
                revision_id=revision_id,
                revision_number=1,
                company_id=start.company_id,
                branch_id=start.branch_id,
                employee_id=start.employee_id,
                job_id=start.job_id,
                appointment_id=start.appointment_id,
                start_at=start.occurred_at,
                stop_at=event.occurred_at,
                source=start.source,
                correction_state=CorrectionState.ORIGINAL,
                supersedes_revision_id=None,
                audit_lineage=(revision_id,),
                source_event_ids=(start.event_id, event.event_id),
                validity=IntervalValidity.VALID,
                confidence=IntervalConfidence.AUTHORITATIVE,
            )
        )
    if active:
        raise JobParticipationError("one or more Job intervals remain active")
    _assert_no_overlap(tuple(intervals))
    return tuple(intervals)


def correct_job_worked_interval(
    current: JobWorkedInterval,
    *,
    start_at: datetime,
    stop_at: datetime,
    reason: str,
    corrected_by_user_id: UUID,
    other_current_intervals: tuple[JobWorkedInterval, ...] = (),
) -> tuple[JobWorkedInterval, JobWorkedInterval]:
    """Return immutable superseded evidence and its corrected successor revision."""

    if current.correction_state is CorrectionState.SUPERSEDED:
        raise JobParticipationError("only a current interval can be corrected")
    if not reason.strip():
        raise JobParticipationError("correction reason is required")
    revision_number = current.revision_number + 1
    revision_id = uuid5(
        INTERVAL_NAMESPACE,
        f"{current.interval_id}:{revision_number}:{corrected_by_user_id}",
    )
    corrected = _seal_interval(
        interval_id=current.interval_id,
        revision_id=revision_id,
        revision_number=revision_number,
        company_id=current.company_id,
        branch_id=current.branch_id,
        employee_id=current.employee_id,
        job_id=current.job_id,
        appointment_id=current.appointment_id,
        start_at=start_at,
        stop_at=stop_at,
        source=WorkedIntervalSource.AUTHORIZED_MANUAL,
        correction_state=CorrectionState.CORRECTED,
        supersedes_revision_id=current.revision_id,
        audit_lineage=(*current.audit_lineage, revision_id),
        source_event_ids=current.source_event_ids,
        validity=IntervalValidity.VALID,
        confidence=current.confidence,
        correction_reason=reason.strip(),
    )
    _assert_no_overlap((*other_current_intervals, corrected))
    return current, corrected


@dataclass(frozen=True, slots=True)
class ApprovedPaidTimeEvidence:
    revision_id: UUID
    evidence_digest: str
    company_id: UUID
    branch_id: UUID | None
    employee_id: UUID
    start_at: datetime
    end_at: datetime
    approved: bool


@dataclass(frozen=True, slots=True)
class ParticipationAssertion:
    assertion_id: UUID
    evidence_digest: str
    paid_time_revision_id: UUID
    company_id: UUID
    branch_id: UUID | None
    employee_id: UUID
    kind: ParticipationKind
    start_at: datetime
    end_at: datetime
    job_id: UUID | None
    approved: bool


@dataclass(frozen=True, slots=True)
class JobMinutes:
    job_id: UUID
    minutes: int


@dataclass(frozen=True, slots=True)
class JobParticipationReconciliation:
    contract: str
    company_id: UUID
    employee_id: UUID
    paid_minutes: int
    attributed_minutes: int
    job_minutes: tuple[JobMinutes, ...]
    travel_minutes: int
    nonproductive_minutes: int
    unclassified_minutes: int
    accepted_assertion_ids: tuple[UUID, ...]
    blockers: tuple[str, ...]
    evidence_digest: str

    @property
    def payroll_ready(self) -> bool:
        """Attribution completeness only; never authorizes Payroll execution."""

        return not self.blockers and self.unclassified_minutes == 0


def reconcile_job_participation(
    paid_time: ApprovedPaidTimeEvidence,
    assertions: tuple[ParticipationAssertion, ...],
) -> JobParticipationReconciliation:
    """Reconcile explicit participation to one approved paid-time revision.

    Gaps remain unclassified rather than being inferred from Appointments or elapsed
    wall time. Unapproved assertions are visible blockers and contribute no minutes.
    """

    _validate_paid_time(paid_time)
    blockers: list[str] = []
    accepted: list[ParticipationAssertion] = []
    assertion_ids: set[UUID] = set()
    for value in assertions:
        _validate_assertion_shape(value)
        if value.assertion_id in assertion_ids:
            raise JobParticipationError("duplicate participation assertion identity")
        assertion_ids.add(value.assertion_id)
        if (
            value.company_id != paid_time.company_id
            or value.branch_id != paid_time.branch_id
            or value.employee_id != paid_time.employee_id
            or value.paid_time_revision_id != paid_time.revision_id
        ):
            raise JobParticipationError("participation assertion scope mismatch")
        if value.start_at < paid_time.start_at or value.end_at > paid_time.end_at:
            raise JobParticipationError("participation exceeds approved paid time")
        if not value.approved:
            blockers.append("UNAPPROVED_PARTICIPATION")
            continue
        accepted.append(value)

    accepted.sort(key=lambda item: (item.start_at, item.end_at, str(item.assertion_id)))
    for previous, current in pairwise(accepted):
        if current.start_at < previous.end_at:
            raise JobParticipationError("participation assertions overlap")

    job_totals: dict[UUID, int] = defaultdict(int)
    travel = 0
    nonproductive = 0
    for value in accepted:
        minutes = _minutes(value.start_at, value.end_at)
        if value.kind is ParticipationKind.JOB:
            assert value.job_id is not None
            job_totals[value.job_id] += minutes
        elif value.kind is ParticipationKind.TRAVEL:
            travel += minutes
        else:
            nonproductive += minutes
    paid_minutes = _minutes(paid_time.start_at, paid_time.end_at)
    attributed = sum(job_totals.values()) + travel + nonproductive
    unclassified = paid_minutes - attributed
    if unclassified:
        blockers.append("UNCLASSIFIED_PAID_TIME")
    if not paid_time.approved:
        blockers.append("PAID_TIME_NOT_APPROVED")

    job_minutes = tuple(
        JobMinutes(job_id, minutes)
        for job_id, minutes in sorted(job_totals.items(), key=lambda item: str(item[0]))
    )
    accepted_ids = tuple(item.assertion_id for item in accepted)
    canonical = {
        "contract": CONTRACT_VERSION,
        "paid_time": {
            "revision_id": str(paid_time.revision_id),
            "evidence_digest": paid_time.evidence_digest,
        },
        "assertions": [
            {
                "assertion_id": str(item.assertion_id),
                "evidence_digest": item.evidence_digest,
            }
            for item in accepted
        ],
        "job_minutes": [
            {"job_id": str(item.job_id), "minutes": item.minutes}
            for item in job_minutes
        ],
        "travel_minutes": travel,
        "nonproductive_minutes": nonproductive,
        "unclassified_minutes": unclassified,
        "blockers": sorted(set(blockers)),
    }
    return JobParticipationReconciliation(
        contract=CONTRACT_VERSION,
        company_id=paid_time.company_id,
        employee_id=paid_time.employee_id,
        paid_minutes=paid_minutes,
        attributed_minutes=attributed,
        job_minutes=job_minutes,
        travel_minutes=travel,
        nonproductive_minutes=nonproductive,
        unclassified_minutes=unclassified,
        accepted_assertion_ids=accepted_ids,
        blockers=tuple(sorted(set(blockers))),
        evidence_digest=hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )


def _validate_paid_time(value: ApprovedPaidTimeEvidence) -> None:
    if value.start_at.tzinfo is None or value.end_at.tzinfo is None:
        raise JobParticipationError("paid time must be timezone-aware")
    if value.end_at <= value.start_at or not _digest_valid(value.evidence_digest):
        raise JobParticipationError("paid-time evidence is invalid")


def _validate_assertion_shape(value: ParticipationAssertion) -> None:
    if value.start_at.tzinfo is None or value.end_at.tzinfo is None:
        raise JobParticipationError("participation time must be timezone-aware")
    if value.end_at <= value.start_at or not _digest_valid(value.evidence_digest):
        raise JobParticipationError("participation evidence is invalid")
    if (value.kind is ParticipationKind.JOB) != (value.job_id is not None):
        raise JobParticipationError(
            "Job identity is required only for Job participation"
        )


def _minutes(start: datetime, end: datetime) -> int:
    seconds = int((end - start).total_seconds())
    if seconds % 60:
        raise JobParticipationError(
            "participation evidence must resolve to whole minutes"
        )
    return seconds // 60


def _digest_valid(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _validate_clock_event(value: JobClockEvent) -> None:
    if value.occurred_at.tzinfo is None:
        raise JobParticipationError("Job clock timestamp must be timezone-aware")
    if not value.idempotency_key.strip() or not _digest_valid(value.request_digest):
        raise JobParticipationError("Job clock replay evidence is invalid")


def _seal_interval(**values: object) -> JobWorkedInterval:
    start_at = values["start_at"]
    stop_at = values["stop_at"]
    assert isinstance(start_at, datetime) and isinstance(stop_at, datetime)
    duration = _minutes(start_at, stop_at)
    canonical = {
        "contract": INTERVAL_CONTRACT_VERSION,
        **{
            key: (
                value.isoformat()
                if isinstance(value, datetime)
                else value.value
                if isinstance(value, StrEnum)
                else tuple(str(item) for item in value)
                if isinstance(value, tuple)
                else str(value)
                if isinstance(value, UUID)
                else value
            )
            for key, value in values.items()
        },
        "duration_minutes": duration,
    }
    return JobWorkedInterval(
        **values,  # type: ignore[arg-type]
        duration_minutes=duration,
        evidence_digest=hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )


def _assert_no_overlap(values: tuple[JobWorkedInterval, ...]) -> None:
    current = sorted(
        (
            item
            for item in values
            if item.correction_state is not CorrectionState.SUPERSEDED
        ),
        key=lambda item: (item.company_id, item.employee_id, item.start_at),
    )
    for previous, candidate in pairwise(current):
        same_employee = (
            previous.company_id == candidate.company_id
            and previous.employee_id == candidate.employee_id
        )
        if same_employee and candidate.start_at < previous.stop_at:
            raise JobParticipationError("Job worked intervals overlap")
