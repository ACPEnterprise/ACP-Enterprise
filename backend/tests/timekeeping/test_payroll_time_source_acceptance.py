# ruff: noqa: F811

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.timekeeping.commands import (
    CorrectTimeEntry,
    CreatePayPeriod,
    RecordManualTime,
)
from app.timekeeping.contracts import (
    TimeCorrectionKind,
    WorkdayAuthorizationError,
    WorkdayTimeError,
    canonical_digest,
    seal_payroll_time_input,
)
from app.timekeeping.job_participation import (
    ApprovedPaidTimeEvidence,
    JobClockEvent,
    JobClockKind,
    JobParticipationError,
    ParticipationAssertion,
    ParticipationKind,
    derive_job_worked_intervals,
    reconcile_job_participation,
)
from app.timekeeping.permissions import TimekeepingPermission
from app.timekeeping.service import WorkdayTimeService
from tests.timekeeping.test_workday_authority import (
    FakeContext,
    SeededTimekeeping,
    timekeeping_database,  # noqa: F401
)

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def manager(seed: SeededTimekeeping) -> FakeContext:
    return FakeContext(
        seed,
        {
            TimekeepingPermission.MANUAL_ENTRY,
            TimekeepingPermission.CORRECT,
            TimekeepingPermission.APPROVE,
            TimekeepingPermission.ADMIN_READ,
        },
        manager=True,
    )


async def accepted_revision(
    service: WorkdayTimeService,
    session: AsyncSession,
    seed: SeededTimekeeping,
    *,
    work_date: date,
    start_at: datetime,
    end_at: datetime,
):
    context = manager(seed)
    recorded = await service.record_manual_time(
        session,
        context=context,  # type: ignore[arg-type]
        command=RecordManualTime(
            employee_id=seed.employee_id,
            branch_id=seed.branch_id,
            work_date=work_date,
            timezone="America/New_York",
            start_at=start_at,
            end_at=end_at,
            approved_duration_minutes=None,
            reason="Sanctioned isolated Payroll source acceptance fixture",
        ),
    )
    submitted = await service.submit(
        session,
        context=context,  # type: ignore[arg-type]
        revision_id=recorded.id,
    )
    return await service.approve(
        session,
        context=context,  # type: ignore[arg-type]
        revision_id=submitted.id,
    )


async def period(
    service: WorkdayTimeService,
    session: AsyncSession,
    seed: SeededTimekeeping,
    *,
    start: date = date(2026, 8, 29),
    end: date = date(2026, 8, 30),
):
    return await service.create_pay_period(
        session,
        context=manager(seed),  # type: ignore[arg-type]
        command=CreatePayPeriod(
            period_start=start,
            period_end=end,
            processing_date=date(2026, 9, 3),
            payday=date(2026, 9, 4),
            timezone="America/New_York",
            schedule_definition_id="synthetic.payroll-source-acceptance",
            schedule_version=1,
        ),
    )


@pytest.mark.asyncio
async def test_job_labor_and_payroll_bind_the_same_accepted_revision_once(
    timekeeping_database: tuple[async_sessionmaker[AsyncSession], SeededTimekeeping],
) -> None:
    factory, seed = timekeeping_database
    service = WorkdayTimeService()
    async with factory() as session:
        approved = await accepted_revision(
            service,
            session,
            seed,
            work_date=date(2026, 8, 29),
            start_at=NOW,
            end_at=NOW + timedelta(hours=2),
        )
        pay_period = await period(service, session, seed)
        snapshot = await service.seal_payroll_input(
            session,
            context=manager(seed),  # type: ignore[arg-type]
            employee_id=seed.employee_id,
            pay_period=pay_period,
        )
        replay = await service.seal_payroll_input(
            session,
            context=manager(seed),  # type: ignore[arg-type]
            employee_id=seed.employee_id,
            pay_period=pay_period,
        )
        assert snapshot.snapshot_digest == replay.snapshot_digest
        assert tuple(item.revision_id for item in snapshot.approved_entries) == (
            approved.id,
        )
        overlap_draft = replace(
            snapshot.approved_entries[0],
            entry_id=uuid4(),
            revision_id=uuid4(),
            evidence_digest="",
        )
        overlap = replace(
            overlap_draft,
            evidence_digest=canonical_digest(overlap_draft.canonical_content()),
        )
        with pytest.raises(WorkdayTimeError, match="overlapping approved"):
            seal_payroll_time_input(
                company_id=seed.company_id,
                employee_id=seed.employee_id,
                pay_period_id=pay_period.id,
                period_start=pay_period.period_start,
                period_end=pay_period.period_end,
                approved_entries=(snapshot.approved_entries[0], overlap),
            )

        fact = snapshot.approved_entries[0]
        job_id = uuid4()
        clock_scope = {
            "company_id": fact.company_id,
            "branch_id": fact.branch_id,
            "employee_id": fact.employee_id,
            "job_id": job_id,
            "appointment_id": None,
            "recorded_by_user_id": seed.user_id,
        }
        worked = derive_job_worked_intervals(
            (
                JobClockEvent(
                    event_id=uuid4(),
                    idempotency_key="accepted-job-start",
                    request_digest="1" * 64,
                    kind=JobClockKind.START,
                    occurred_at=NOW,
                    **clock_scope,
                ),
                JobClockEvent(
                    event_id=uuid4(),
                    idempotency_key="accepted-job-stop",
                    request_digest="2" * 64,
                    kind=JobClockKind.STOP,
                    occurred_at=NOW + timedelta(hours=2),
                    **clock_scope,
                ),
            )
        )[0]
        paid = ApprovedPaidTimeEvidence(
            revision_id=fact.revision_id,
            evidence_digest=fact.evidence_digest,
            company_id=fact.company_id,
            branch_id=fact.branch_id,
            employee_id=fact.employee_id,
            start_at=NOW,
            end_at=NOW + timedelta(hours=2),
            approved=True,
        )
        assertion = ParticipationAssertion(
            assertion_id=uuid4(),
            evidence_digest=worked.evidence_digest,
            paid_time_revision_id=fact.revision_id,
            company_id=fact.company_id,
            branch_id=fact.branch_id,
            employee_id=fact.employee_id,
            kind=ParticipationKind.JOB,
            start_at=worked.start_at,
            end_at=worked.stop_at,
            job_id=worked.job_id,
            approved=True,
        )
        labor = reconcile_job_participation(paid, (assertion,))
        assert labor.accepted_assertion_ids == (assertion.assertion_id,)
        assert labor.job_minutes[0].minutes == snapshot.total_approved_minutes
        assert (
            assertion.paid_time_revision_id == snapshot.approved_entries[0].revision_id
        )


@pytest.mark.asyncio
async def test_correction_and_period_boundaries_leave_one_current_contribution(
    timekeeping_database: tuple[async_sessionmaker[AsyncSession], SeededTimekeeping],
) -> None:
    factory, seed = timekeeping_database
    service = WorkdayTimeService()
    context = manager(seed)
    async with factory() as session:
        original = await accepted_revision(
            service,
            session,
            seed,
            work_date=date(2026, 8, 29),
            start_at=NOW,
            end_at=NOW + timedelta(hours=2),
        )
        await accepted_revision(
            service,
            session,
            seed,
            work_date=date(2026, 8, 31),
            start_at=NOW + timedelta(days=2),
            end_at=NOW + timedelta(days=2, hours=3),
        )
        pay_period = await period(
            service, session, seed, start=date(2026, 8, 29), end=date(2026, 8, 30)
        )
        first = await service.seal_payroll_input(
            session,
            context=context,  # type: ignore[arg-type]
            employee_id=seed.employee_id,
            pay_period=pay_period,
        )
        assert first.total_approved_minutes == 120

        corrected = await service.correct(
            session,
            context=context,  # type: ignore[arg-type]
            command=CorrectTimeEntry(
                revision_id=original.id,
                start_at=NOW,
                end_at=NOW + timedelta(hours=3),
                approved_duration_minutes=None,
                reason="Synthetic correction acceptance",
                correction_kind=TimeCorrectionKind.INCORRECT_STOP,
                idempotency_key="source-acceptance-correction",
            ),
        )
        projection = await service.payroll_input_projection(
            session,
            context=context,  # type: ignore[arg-type]
            employee_id=seed.employee_id,
            pay_period=pay_period,
        )
        assert projection.total_eligible_minutes == 0
        with pytest.raises(WorkdayTimeError, match="missing is not zero"):
            await service.seal_payroll_input(
                session,
                context=context,  # type: ignore[arg-type]
                employee_id=seed.employee_id,
                pay_period=pay_period,
            )
        submitted = await service.submit(
            session,
            context=context,  # type: ignore[arg-type]
            revision_id=corrected.id,
        )
        awaiting = await service.payroll_input_projection(
            session,
            context=context,  # type: ignore[arg-type]
            employee_id=seed.employee_id,
            pay_period=pay_period,
        )
        assert awaiting.total_eligible_minutes == 0
        successor = await service.approve(
            session,
            context=context,  # type: ignore[arg-type]
            revision_id=submitted.id,
        )
        current = await service.seal_payroll_input(
            session,
            context=context,  # type: ignore[arg-type]
            employee_id=seed.employee_id,
            pay_period=pay_period,
        )
        assert current.total_approved_minutes == 180
        assert tuple(item.revision_id for item in current.approved_entries) == (
            successor.id,
        )
        assert original.id in current.approved_entries[0].correction_lineage


@pytest.mark.asyncio
async def test_unapproved_job_evidence_and_cross_company_scope_fail_closed(
    timekeeping_database: tuple[async_sessionmaker[AsyncSession], SeededTimekeeping],
) -> None:
    factory, seed = timekeeping_database
    service = WorkdayTimeService()
    async with factory() as session:
        approved = await accepted_revision(
            service,
            session,
            seed,
            work_date=date(2026, 8, 29),
            start_at=NOW,
            end_at=NOW + timedelta(hours=1),
        )
        pay_period = await period(service, session, seed)
        foreign = manager(seed)
        foreign.company.id = uuid4()
        with pytest.raises(WorkdayAuthorizationError, match="Company mismatch"):
            await service.seal_payroll_input(
                session,
                context=foreign,  # type: ignore[arg-type]
                employee_id=seed.employee_id,
                pay_period=pay_period,
            )

        paid = ApprovedPaidTimeEvidence(
            revision_id=approved.id,
            evidence_digest=approved.evidence_digest,
            company_id=seed.company_id,
            branch_id=seed.branch_id,
            employee_id=seed.employee_id,
            start_at=NOW,
            end_at=NOW + timedelta(hours=1),
            approved=True,
        )
        rejected = ParticipationAssertion(
            assertion_id=uuid4(),
            evidence_digest="b" * 64,
            paid_time_revision_id=approved.id,
            company_id=seed.company_id,
            branch_id=seed.branch_id,
            employee_id=seed.employee_id,
            kind=ParticipationKind.JOB,
            start_at=NOW,
            end_at=NOW + timedelta(hours=1),
            job_id=uuid4(),
            approved=False,
        )
        result = reconcile_job_participation(paid, (rejected,))
        assert result.job_minutes == ()
        assert "UNAPPROVED_PARTICIPATION" in result.blockers

        foreign_assertion = replace(rejected, company_id=UUID(int=99))
        with pytest.raises(JobParticipationError, match="scope mismatch"):
            reconcile_job_participation(paid, (foreign_assertion,))


def test_open_job_clock_does_not_create_completed_or_payable_evidence() -> None:
    start = JobClockEvent(
        event_id=uuid4(),
        idempotency_key="isolated-open-clock",
        request_digest="c" * 64,
        company_id=uuid4(),
        branch_id=uuid4(),
        employee_id=uuid4(),
        job_id=uuid4(),
        appointment_id=None,
        kind=JobClockKind.START,
        occurred_at=NOW,
        recorded_by_user_id=uuid4(),
    )
    with pytest.raises(JobParticipationError, match="remain active"):
        derive_job_worked_intervals((start,))
