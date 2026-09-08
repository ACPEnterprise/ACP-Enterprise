from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest
from app.timekeeping.job_participation import (
    ApprovedPaidTimeEvidence,
    JobParticipationError,
    ParticipationAssertion,
    ParticipationKind,
    reconcile_job_participation,
)

COMPANY = UUID("11111111-1111-1111-1111-111111111111")
BRANCH = UUID("22222222-2222-2222-2222-222222222222")
EMPLOYEE = UUID("33333333-3333-3333-3333-333333333333")
REVISION = UUID("44444444-4444-4444-4444-444444444444")
JOB = UUID("55555555-5555-5555-5555-555555555555")


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
    assert reconcile_job_participation(
        paid(), values
    ).evidence_digest == reconcile_job_participation(paid(), tuple(reversed(values))).evidence_digest


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
