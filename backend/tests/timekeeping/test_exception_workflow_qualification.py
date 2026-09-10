"""Independent non-overlap qualification for the reconciled exception workflow."""

from datetime import datetime, timezone
from uuid import UUID

from app.timekeeping.job_participation import (
    JobClockEvent,
    JobClockKind,
    WorkedIntervalSource,
    correct_job_worked_interval,
    derive_job_worked_intervals,
)

COMPANY = UUID(int=1)
BRANCH = UUID(int=2)
EMPLOYEE = UUID(int=3)
USER = UUID(int=4)
JOB = UUID(int=5)
APPOINTMENT = UUID(int=6)


def _at(hour: int) -> datetime:
    return datetime(2026, 9, 8, hour, tzinfo=timezone.utc)


def _event(identity: int, kind: JobClockKind, hour: int) -> JobClockEvent:
    return JobClockEvent(
        event_id=UUID(int=identity),
        idempotency_key=f"job-clock-{identity}",
        request_digest=f"{identity:x}".zfill(64),
        company_id=COMPANY,
        branch_id=BRANCH,
        employee_id=EMPLOYEE,
        job_id=JOB,
        appointment_id=APPOINTMENT,
        kind=kind,
        occurred_at=_at(hour),
        recorded_by_user_id=USER,
        source=WorkedIntervalSource.EMPLOYEE_CLOCK,
    )


def test_non_overlapping_correction_preserves_original_and_is_deterministic() -> None:
    morning, afternoon = derive_job_worked_intervals(
        (
            _event(10, JobClockKind.START, 8),
            _event(11, JobClockKind.STOP, 10),
            _event(12, JobClockKind.START, 13),
            _event(13, JobClockKind.STOP, 15),
        )
    )
    preserved, corrected = correct_job_worked_interval(
        morning,
        start_at=_at(9),
        stop_at=_at(11),
        reason="Reviewer reconciled immutable field evidence",
        corrected_by_user_id=USER,
        other_current_intervals=(afternoon,),
    )
    replay = correct_job_worked_interval(
        morning,
        start_at=_at(9),
        stop_at=_at(11),
        reason="Reviewer reconciled immutable field evidence",
        corrected_by_user_id=USER,
        other_current_intervals=(afternoon,),
    )[1]

    assert preserved == morning
    assert preserved.evidence_digest == morning.evidence_digest
    assert corrected.supersedes_revision_id == morning.revision_id
    assert corrected.evidence_digest == replay.evidence_digest
    assert corrected.stop_at <= afternoon.start_at
