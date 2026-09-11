from contextlib import AbstractAsyncContextManager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.timekeeping.commands import CorrectJobWorkedInterval, RecordJobClock
from app.timekeeping.contracts import WorkdayAuthorizationError, WorkdayConflictError
from app.timekeeping.job_participation import JobClockKind
from app.timekeeping.models import JobWorkedClockEvent, JobWorkedIntervalRevision
from app.timekeeping.query_service import WorkdayTimeQueryService
from app.timekeeping.service import WorkdayTimeService

NOW = datetime(2026, 9, 10, 12, 0, 1, 250000, tzinfo=timezone.utc)


class Transaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeSession:
    def __init__(self, repository: "FakeRepository") -> None:
        self.repository = repository

    def begin_nested(self) -> Transaction:
        return Transaction()

    def add(self, value: object) -> None:
        if isinstance(value, JobWorkedClockEvent):
            self.repository.events.append(value)
        elif isinstance(value, JobWorkedIntervalRevision):
            self.repository.intervals.append(value)

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FakeRepository:
    def __init__(self, employee_id: UUID) -> None:
        self.employee_id = employee_id
        self.events: list[JobWorkedClockEvent] = []
        self.intervals: list[JobWorkedIntervalRevision] = []

    async def employee_for_membership(self, *args: object, **kwargs: object) -> object:
        return SimpleNamespace(id=self.employee_id)

    async def job_scope_exists(self, *args: object, **kwargs: object) -> bool:
        return True

    async def lock_employee_job_clock(self, *args: object, **kwargs: object) -> None:
        return None

    async def latest_job_clock_event(
        self, *args: object, **kwargs: object
    ) -> JobWorkedClockEvent | None:
        return self.events[-1] if self.events else None

    async def job_clock_by_idempotency_key(
        self, *args: object, **kwargs: object
    ) -> JobWorkedClockEvent | None:
        key = kwargs["idempotency_key"]
        return next((item for item in self.events if item.idempotency_key == key), None)

    async def interval_for_job_clock_event(
        self, *args: object, **kwargs: object
    ) -> JobWorkedIntervalRevision | None:
        event_id = str(kwargs["event_id"])
        return next(
            (
                item
                for item in reversed(self.intervals)
                if event_id in item.source_event_ids
            ),
            None,
        )

    async def latest_job_interval_revision(
        self, *args: object, **kwargs: object
    ) -> JobWorkedIntervalRevision | None:
        revision_id = kwargs["revision_id"]
        base = next((item for item in self.intervals if item.id == revision_id), None)
        if base is None:
            return None
        return max(
            (item for item in self.intervals if item.interval_id == base.interval_id),
            key=lambda item: item.revision_number,
        )

    async def job_interval_correction_by_idempotency_key(
        self, *args: object, **kwargs: object
    ) -> JobWorkedIntervalRevision | None:
        key = kwargs["idempotency_key"]
        return next(
            (item for item in self.intervals if item.correction_idempotency_key == key),
            None,
        )

    async def current_job_intervals(
        self, *args: object, **kwargs: object
    ) -> tuple[JobWorkedIntervalRevision, ...]:
        return tuple(self.intervals)

    async def pay_period_for_date(self, *args: object, **kwargs: object) -> None:
        return None

    async def current_employee_revisions(
        self, *args: object, **kwargs: object
    ) -> tuple[object, ...]:
        return ()

    async def latest_punch(self, *args: object, **kwargs: object) -> None:
        return None

    async def latest_clock_in(self, *args: object, **kwargs: object) -> None:
        return None


class HarnessService(WorkdayTimeService):
    def _stage_action(self, *args: object, **kwargs: object) -> None:
        return None


def context(employee_id: UUID) -> object:
    company_id, branch_id, user_id, membership_id = uuid4(), uuid4(), uuid4(), uuid4()
    return SimpleNamespace(
        company=SimpleNamespace(id=company_id, timezone="America/New_York"),
        active_branch=SimpleNamespace(id=branch_id, timezone="America/New_York"),
        user=SimpleNamespace(id=user_id),
        membership=SimpleNamespace(id=membership_id),
        has_permission=lambda code: True,
        can_access_branch=lambda value: value == branch_id,
        employee_id=employee_id,
    )


def command(
    ctx: object,
    employee_id: UUID,
    action: JobClockKind,
    key: str,
    when: datetime,
    *,
    job_id: UUID,
) -> RecordJobClock:
    return RecordJobClock(
        employee_id=employee_id,
        branch_id=ctx.active_branch.id,
        job_id=job_id,
        appointment_id=None,
        kind=action,
        occurred_at=when,
        idempotency_key=key,
    )


@pytest.mark.asyncio
async def test_clock_start_stop_visibility_precision_and_lost_response_replay() -> None:
    employee_id, job_id = uuid4(), uuid4()
    ctx = context(employee_id)
    repository = FakeRepository(employee_id)
    service = HarnessService(repository)  # type: ignore[arg-type]
    session = FakeSession(repository)
    start = command(ctx, employee_id, JobClockKind.START, "start-1", NOW, job_id=job_id)
    start_event, interval = await service.record_job_clock(
        session, context=ctx, command=start
    )  # type: ignore[arg-type]
    assert interval is None

    replay, replay_interval = await service.record_job_clock(
        session,
        context=ctx,  # type: ignore[arg-type]
        command=command(
            ctx,
            employee_id,
            JobClockKind.START,
            "start-1",
            NOW + timedelta(seconds=9),
            job_id=job_id,
        ),
    )
    assert replay.id == start_event.id
    assert replay_interval is None

    stop = command(
        ctx,
        employee_id,
        JobClockKind.STOP,
        "stop-1",
        NOW + timedelta(seconds=91),
        job_id=job_id,
    )
    stop_event, completed = await service.record_job_clock(
        session, context=ctx, command=stop
    )  # type: ignore[arg-type]
    assert completed is not None
    assert completed.duration_seconds == 91
    assert completed.duration_minutes == 1
    recovered_event, recovered = await service.record_job_clock(
        session,
        context=ctx,  # type: ignore[arg-type]
        command=command(
            ctx,
            employee_id,
            JobClockKind.STOP,
            "stop-1",
            NOW + timedelta(seconds=150),
            job_id=job_id,
        ),
    )
    assert recovered_event.id == stop_event.id
    assert recovered is not None and recovered.id == completed.id


@pytest.mark.asyncio
async def test_independent_employee_identity_and_overlap_fail_closed() -> None:
    employee_id, other_employee, job_id = uuid4(), uuid4(), uuid4()
    ctx = context(employee_id)
    repository = FakeRepository(employee_id)
    service = HarnessService(repository)  # type: ignore[arg-type]
    session = FakeSession(repository)
    with pytest.raises(WorkdayAuthorizationError, match="own Job work"):
        await service.record_job_clock(
            session,
            context=ctx,  # type: ignore[arg-type]
            command=command(
                ctx, other_employee, JobClockKind.START, "foreign", NOW, job_id=job_id
            ),
        )
    await service.record_job_clock(
        session,
        context=ctx,  # type: ignore[arg-type]
        command=command(
            ctx, employee_id, JobClockKind.START, "start", NOW, job_id=job_id
        ),
    )
    with pytest.raises(WorkdayConflictError, match="active Job clock"):
        await service.record_job_clock(
            session,
            context=ctx,  # type: ignore[arg-type]
            command=command(
                ctx, employee_id, JobClockKind.START, "overlap", NOW, job_id=uuid4()
            ),
        )


@pytest.mark.asyncio
async def test_correction_is_append_only_and_replay_safe() -> None:
    employee_id, job_id = uuid4(), uuid4()
    ctx = context(employee_id)
    repository = FakeRepository(employee_id)
    service = HarnessService(repository)  # type: ignore[arg-type]
    session = FakeSession(repository)
    await service.record_job_clock(
        session,
        context=ctx,  # type: ignore[arg-type]
        command=command(ctx, employee_id, JobClockKind.START, "s", NOW, job_id=job_id),
    )
    _, original = await service.record_job_clock(
        session,
        context=ctx,  # type: ignore[arg-type]
        command=command(
            ctx,
            employee_id,
            JobClockKind.STOP,
            "e",
            NOW + timedelta(minutes=5),
            job_id=job_id,
        ),
    )
    assert original is not None
    correction = CorrectJobWorkedInterval(
        revision_id=original.id,
        start_at=NOW + timedelta(seconds=5),
        stop_at=NOW + timedelta(minutes=5, seconds=10),
        reason="Synthetic supervisor verification",
        idempotency_key="correction-1",
    )
    corrected = await service.correct_job_interval(
        session, context=ctx, command=correction
    )  # type: ignore[arg-type]
    replay = await service.correct_job_interval(
        session, context=ctx, command=correction
    )  # type: ignore[arg-type]
    assert replay.id == corrected.id
    assert original.revision_number == 1
    assert corrected.revision_number == 2
    assert corrected.supersedes_revision_id == original.id
    assert corrected.audit_lineage == [*original.audit_lineage, str(corrected.id)]


@pytest.mark.asyncio
async def test_active_clock_and_timecard_project_job_evidence_without_making_it_paid() -> (
    None
):
    employee_id, job_id = uuid4(), uuid4()
    ctx = context(employee_id)
    repository = FakeRepository(employee_id)
    service = HarnessService(repository)  # type: ignore[arg-type]
    session = FakeSession(repository)
    await service.record_job_clock(
        session,
        context=ctx,  # type: ignore[arg-type]
        command=command(
            ctx, employee_id, JobClockKind.START, "start", NOW, job_id=job_id
        ),
    )
    queries = WorkdayTimeQueryService(repository)  # type: ignore[arg-type]
    active = await queries.active_job_clock(
        session,  # type: ignore[arg-type]
        context=ctx,  # type: ignore[arg-type]
        employee_id=employee_id,
        observed_at=NOW + timedelta(seconds=45),
    )
    assert active.active is True
    assert active.job_id == job_id
    assert active.employee_id == employee_id
    assert active.elapsed_seconds == 45

    await service.record_job_clock(
        session,
        context=ctx,  # type: ignore[arg-type]
        command=command(
            ctx,
            employee_id,
            JobClockKind.STOP,
            "stop",
            NOW + timedelta(minutes=2),
            job_id=job_id,
        ),
    )
    timecard = await queries.own_timecard(session, context=ctx)  # type: ignore[arg-type]
    assert timecard.entries == ()
    assert len(timecard.job_intervals) == 1
    assert timecard.job_intervals[0].job_id == job_id
    assert timecard.job_intervals[0].duration_seconds == 120
