from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest
from app.timekeeping.job_participation import (
    ApprovedPaidTimeEvidence,
    CorrectionState,
    JobClockEvent,
    JobClockKind,
    JobParticipationError,
    ParticipationAssertion,
    ParticipationKind,
    WorkedIntervalSource,
    correct_job_worked_interval,
    derive_job_worked_intervals,
    reconcile_job_participation,
)

COMPANY = UUID("11111111-1111-1111-1111-111111111111")
BRANCH = UUID("22222222-2222-2222-2222-222222222222")
EMPLOYEE = UUID("33333333-3333-3333-3333-333333333333")
REVISION = UUID("44444444-4444-4444-4444-444444444444")
JOB = UUID("55555555-5555-5555-5555-555555555555")
APPOINTMENT = UUID("66666666-6666-6666-6666-666666666666")
USER = UUID("77777777-7777-7777-7777-777777777777")


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 8, hour, minute, tzinfo=timezone.utc)


def paid(*, approved: bool = True) -> ApprovedPaidTimeEvidence:
    return ApprovedPaidTimeEvidence(
        REVISION, "a" * 64, COMPANY, BRANCH, EMPLOYEE, at(8), at(12), approved
    )


def assertion(
    identity: int,
    kind: ParticipationKind,
    start: datetime,
    end: datetime,
    *,
    job_id: UUID | None = None,
    approved: bool = True,
) -> ParticipationAssertion:
    return ParticipationAssertion(
        UUID(int=identity),
        f"{identity:x}".zfill(64),
        REVISION,
        COMPANY,
        BRANCH,
        EMPLOYEE,
        kind,
        start,
        end,
        job_id,
        approved,
    )


def test_reconciles_job_travel_and_nonproductive_to_paid_minutes() -> None:
    result = reconcile_job_participation(
        paid(),
        (
            assertion(1, ParticipationKind.TRAVEL, at(8), at(8, 30)),
            assertion(2, ParticipationKind.JOB, at(8, 30), at(11, 30), job_id=JOB),
            assertion(3, ParticipationKind.NONPRODUCTIVE, at(11, 30), at(12)),
        ),
    )
    assert result.paid_minutes == result.attributed_minutes == 240
    assert result.job_minutes[0].minutes == 180
    assert result.travel_minutes == result.nonproductive_minutes == 30
    assert result.unclassified_minutes == 0
    assert result.blockers == ()
    assert result.payroll_ready is True


def test_order_does_not_change_reconciliation_digest() -> None:
    values = (
        assertion(1, ParticipationKind.JOB, at(8), at(10), job_id=JOB),
        assertion(2, ParticipationKind.NONPRODUCTIVE, at(10), at(12)),
    )
    assert (
        reconcile_job_participation(paid(), values).evidence_digest
        == reconcile_job_participation(paid(), tuple(reversed(values))).evidence_digest
    )


def test_gap_remains_explicit_and_never_becomes_inferred_job_time() -> None:
    result = reconcile_job_participation(
        paid(),
        (assertion(1, ParticipationKind.JOB, at(9), at(11), job_id=JOB),),
    )
    assert result.job_minutes[0].minutes == 120
    assert result.unclassified_minutes == 120
    assert result.blockers == ("UNCLASSIFIED_PAID_TIME",)
    assert result.payroll_ready is False


def test_unapproved_assertion_contributes_no_minutes() -> None:
    result = reconcile_job_participation(
        paid(),
        (
            assertion(
                1,
                ParticipationKind.JOB,
                at(8),
                at(12),
                job_id=JOB,
                approved=False,
            ),
        ),
    )
    assert result.attributed_minutes == 0
    assert result.unclassified_minutes == 240
    assert result.blockers == (
        "UNAPPROVED_PARTICIPATION",
        "UNCLASSIFIED_PAID_TIME",
    )


@pytest.mark.parametrize(
    "values, message",
    [
        (
            (
                assertion(1, ParticipationKind.JOB, at(8), at(10), job_id=JOB),
                assertion(2, ParticipationKind.TRAVEL, at(9), at(11)),
            ),
            "overlap",
        ),
        (
            (assertion(1, ParticipationKind.JOB, at(7), at(9), job_id=JOB),),
            "exceeds",
        ),
    ],
)
def test_overlap_and_out_of_paid_time_fail_closed(
    values: tuple[ParticipationAssertion, ...], message: str
) -> None:
    with pytest.raises(JobParticipationError, match=message):
        reconcile_job_participation(paid(), values)


def test_company_employee_branch_and_revision_scope_fail_closed() -> None:
    value = assertion(1, ParticipationKind.JOB, at(8), at(12), job_id=JOB)
    changed = replace(value, company_id=UUID(int=99))
    with pytest.raises(JobParticipationError, match="scope"):
        reconcile_job_participation(paid(), (changed,))


def test_job_identity_shape_fails_closed() -> None:
    with pytest.raises(JobParticipationError, match="Job identity"):
        reconcile_job_participation(
            paid(),
            (assertion(1, ParticipationKind.JOB, at(8), at(12)),),
        )


def test_unapproved_paid_time_never_becomes_payroll_ready() -> None:
    result = reconcile_job_participation(
        paid(approved=False),
        (assertion(1, ParticipationKind.JOB, at(8), at(12), job_id=JOB),),
    )
    assert result.blockers == ("PAID_TIME_NOT_APPROVED",)
    assert result.payroll_ready is False


def clock(
    identity: int, kind: JobClockKind, when: datetime, *, employee: UUID = EMPLOYEE
) -> JobClockEvent:
    return JobClockEvent(
        event_id=UUID(int=identity),
        idempotency_key=f"clock-{identity}",
        request_digest=f"{identity:x}".zfill(64),
        company_id=COMPANY,
        branch_id=BRANCH,
        employee_id=employee,
        job_id=JOB,
        appointment_id=APPOINTMENT,
        kind=kind,
        occurred_at=when,
        recorded_by_user_id=USER,
    )


def test_job_clock_derives_authoritative_interval_without_scheduled_or_paid_time() -> (
    None
):
    result = derive_job_worked_intervals(
        (clock(1, JobClockKind.START, at(8)), clock(2, JobClockKind.STOP, at(9, 30)))
    )
    assert len(result) == 1
    interval = result[0]
    assert (interval.employee_id, interval.job_id, interval.appointment_id) == (
        EMPLOYEE,
        JOB,
        APPOINTMENT,
    )
    assert (interval.start_at, interval.stop_at, interval.duration_minutes) == (
        at(8),
        at(9, 30),
        90,
    )
    assert interval.source is WorkedIntervalSource.EMPLOYEE_CLOCK
    assert interval.correction_state is CorrectionState.ORIGINAL
    assert interval.audit_lineage == (interval.revision_id,)


def test_exact_event_and_idempotency_replay_is_stable() -> None:
    values = (clock(1, JobClockKind.START, at(8)), clock(2, JobClockKind.STOP, at(9)))
    assert derive_job_worked_intervals(values) == derive_job_worked_intervals(
        values + values
    )


def test_contradictory_replay_and_duplicate_active_interval_fail_closed() -> None:
    changed = replace(clock(1, JobClockKind.START, at(8)), request_digest="f" * 64)
    with pytest.raises(JobParticipationError, match="contradictory"):
        derive_job_worked_intervals((clock(1, JobClockKind.START, at(8)), changed))
    with pytest.raises(JobParticipationError, match="already has an active"):
        derive_job_worked_intervals(
            (clock(1, JobClockKind.START, at(8)), clock(2, JobClockKind.START, at(9)))
        )


def test_multiple_employees_and_multiple_intervals_per_job_are_supported() -> None:
    second_employee = UUID(int=88)
    values = (
        clock(1, JobClockKind.START, at(8)),
        clock(2, JobClockKind.START, at(8), employee=second_employee),
        clock(3, JobClockKind.STOP, at(9)),
        clock(4, JobClockKind.STOP, at(10), employee=second_employee),
        clock(5, JobClockKind.START, at(10)),
        clock(6, JobClockKind.STOP, at(11)),
    )
    result = derive_job_worked_intervals(values)
    assert len(result) == 3
    assert (
        sum(value.duration_minutes for value in result if value.employee_id == EMPLOYEE)
        == 120
    )


def test_correction_preserves_original_evidence_and_rejects_overlap() -> None:
    original = derive_job_worked_intervals(
        (clock(1, JobClockKind.START, at(8)), clock(2, JobClockKind.STOP, at(9)))
    )[0]
    preserved, corrected = correct_job_worked_interval(
        original,
        start_at=at(8, 15),
        stop_at=at(9, 15),
        reason="Supervisor verified field evidence",
        corrected_by_user_id=USER,
    )
    assert preserved == original
    assert preserved.evidence_digest == original.evidence_digest
    assert preserved.correction_state is CorrectionState.ORIGINAL
    assert corrected.supersedes_revision_id == original.revision_id
    assert corrected.audit_lineage[:-1] == original.audit_lineage
    assert corrected.source_event_ids == original.source_event_ids
    assert corrected.source is WorkedIntervalSource.AUTHORIZED_MANUAL

    other = replace(corrected, interval_id=UUID(int=99), start_at=at(9), stop_at=at(10))
    with pytest.raises(JobParticipationError, match="overlap"):
        correct_job_worked_interval(
            original,
            start_at=at(8, 30),
            stop_at=at(9, 30),
            reason="Verified",
            corrected_by_user_id=USER,
            other_current_intervals=(other,),
        )
