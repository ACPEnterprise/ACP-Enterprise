from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.customers.models import Customer, ServiceLocation  # noqa: F401
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.permissions.catalog import permission_catalog
from app.platform.users.models import User
from app.scheduling.models import Appointment  # noqa: F401
from app.timekeeping.commands import (
    CorrectTimeEntry,
    CreatePayPeriod,
    RecordManualTime,
    RecordPunch,
)
from app.timekeeping.contracts import (
    PunchKind,
    TimeEntryProvenance,
    WorkdayAuthorizationError,
    WorkdayConflictError,
    WorkdayTimeError,
    seal_payroll_time_input,
)
from app.timekeeping.economics_adapter import to_economics_workday_time
from app.timekeeping.permissions import TimekeepingPermission
from app.timekeeping.service import WorkdayTimeService

NOW = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)


def test_timekeeping_permissions_are_narrow_and_catalogued() -> None:
    permission_catalog.validate()
    definitions = {
        value.code: value
        for value in permission_catalog.definitions
        if value.code in TimekeepingPermission.ALL
    }
    assert set(definitions) == set(TimekeepingPermission.ALL)
    assert all(value.resource == "timekeeping" for value in definitions.values())


def test_missing_approved_time_never_seals_as_zero() -> None:
    with pytest.raises(WorkdayTimeError, match="missing is not zero"):
        seal_payroll_time_input(
            company_id=uuid4(),
            employee_id=uuid4(),
            pay_period_id=uuid4(),
            period_start=date(2026, 8, 29),
            period_end=date(2026, 9, 4),
            approved_entries=(),
        )


@dataclass(frozen=True)
class SeededTimekeeping:
    company_id: UUID
    branch_id: UUID
    user_id: UUID
    membership_id: UUID
    employee_id: UUID
    other_employee_id: UUID


class FakeContext:
    def __init__(self, seed: SeededTimekeeping, permissions: set[str]) -> None:
        self.company = SimpleNamespace(id=seed.company_id)
        self.user = SimpleNamespace(id=seed.user_id)
        self.membership = SimpleNamespace(id=seed.membership_id)
        self._branch_ids = {seed.branch_id}
        self._permissions = permissions

    def has_permission(self, code: str) -> bool:
        return code in self._permissions

    def can_access_branch(self, branch_id: UUID) -> bool:
        return branch_id in self._branch_ids


@pytest_asyncio.fixture
async def timekeeping_database() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], SeededTimekeeping]
]:
    engine: AsyncEngine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    company_id, branch_id, user_id, membership_id = uuid4(), uuid4(), uuid4(), uuid4()
    employee_id, other_employee_id = uuid4(), uuid4()
    async with factory() as session, session.begin():
        session.add(
            Company(
                id=company_id,
                name="Synthetic Time Company",
                code=f"TIME{uuid4().hex[:8].upper()}",
                status="active",
                timezone="America/New_York",
            )
        )
        session.add(
            Branch(
                id=branch_id,
                company_id=company_id,
                name="Synthetic Time Branch",
                code=f"TB{uuid4().hex[:8].upper()}",
                status="active",
                timezone="America/New_York",
                is_primary=True,
            )
        )
        session.add(
            User(
                id=user_id,
                normalized_email=f"time-{uuid4().hex}@example.test",
                first_name="Time",
                last_name="Worker",
                display_name="Time Worker",
                status="active",
                authorization_version=1,
            )
        )
        session.add(
            Membership(
                id=membership_id,
                user_id=user_id,
                company_id=company_id,
                status="active",
                default_branch_id=branch_id,
                has_all_branch_access=False,
                accepted_at=NOW,
            )
        )
        await session.flush()
        for value, number in (
            (employee_id, "TIME-001"),
            (other_employee_id, "TIME-002"),
        ):
            session.add(
                Employee(
                    id=value,
                    company_id=company_id,
                    membership_id=membership_id if value == employee_id else None,
                    home_branch_id=branch_id,
                    employee_number=number,
                    first_name="Synthetic",
                    last_name="Employee",
                    display_name=number,
                    employee_type="employee",
                    status="active",
                )
            )
    seed = SeededTimekeeping(
        company_id, branch_id, user_id, membership_id, employee_id, other_employee_id
    )
    try:
        yield factory, seed
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_manual_entry_requires_authority_and_punch_is_employee_owned(
    timekeeping_database: tuple[async_sessionmaker[AsyncSession], SeededTimekeeping],
) -> None:
    factory, seed = timekeeping_database
    service = WorkdayTimeService()
    no_permissions = FakeContext(seed, set())
    manual = RecordManualTime(
        employee_id=seed.employee_id,
        branch_id=seed.branch_id,
        work_date=date(2026, 8, 29),
        timezone="America/New_York",
        start_at=NOW,
        end_at=NOW + timedelta(hours=2),
        approved_duration_minutes=None,
        reason="Missed punch",
    )
    async with factory() as session:
        with pytest.raises(WorkdayAuthorizationError):
            await service.record_manual_time(
                session, context=no_permissions, command=manual
            )  # type: ignore[arg-type]
    punch_context = FakeContext(seed, {TimekeepingPermission.OWN_PUNCH})
    async with factory() as session:
        with pytest.raises(WorkdayAuthorizationError):
            await service.record_punch(
                session,
                context=punch_context,  # type: ignore[arg-type]
                command=RecordPunch(
                    employee_id=seed.other_employee_id,
                    branch_id=seed.branch_id,
                    kind=PunchKind.CLOCK_IN,
                    occurred_at=NOW,
                    timezone="America/New_York",
                ),
            )
    invalid_timezone = RecordManualTime(
        employee_id=seed.employee_id,
        branch_id=seed.branch_id,
        work_date=date(2026, 8, 29),
        timezone="not/a-timezone",
        start_at=NOW,
        end_at=NOW + timedelta(hours=2),
        approved_duration_minutes=None,
        reason="Invalid timezone regression",
    )
    manager_context = FakeContext(seed, {TimekeepingPermission.MANUAL_ENTRY})
    async with factory() as session:
        with pytest.raises(WorkdayTimeError, match="valid IANA zone"):
            await service.record_manual_time(
                session,
                context=manager_context,  # type: ignore[arg-type]
                command=invalid_timezone,
            )
        with pytest.raises(WorkdayAuthorizationError, match="Branch access"):
            await service.record_manual_time(
                session,
                context=manager_context,  # type: ignore[arg-type]
                command=RecordManualTime(
                    employee_id=seed.employee_id,
                    branch_id=uuid4(),
                    work_date=date(2026, 8, 29),
                    timezone="America/New_York",
                    start_at=NOW,
                    end_at=NOW + timedelta(hours=2),
                    approved_duration_minutes=None,
                    reason="Wrong Branch regression",
                ),
            )


@pytest.mark.asyncio
async def test_mixed_manual_and_punch_time_approval_correction_and_snapshot(
    timekeeping_database: tuple[async_sessionmaker[AsyncSession], SeededTimekeeping],
) -> None:
    factory, seed = timekeeping_database
    service = WorkdayTimeService()
    all_permissions = FakeContext(seed, set(TimekeepingPermission.ALL))
    async with factory() as session:
        manual = await service.record_manual_time(
            session,
            context=all_permissions,  # type: ignore[arg-type]
            command=RecordManualTime(
                employee_id=seed.employee_id,
                branch_id=seed.branch_id,
                work_date=date(2026, 8, 29),
                timezone="America/New_York",
                start_at=NOW,
                end_at=NOW + timedelta(hours=4),
                approved_duration_minutes=None,
                reason="Authorized first-period entry",
            ),
        )
        submitted_manual = await service.submit(
            session,
            context=all_permissions,
            revision_id=manual.id,  # type: ignore[arg-type]
        )
        approved_manual = await service.approve(
            session,
            context=all_permissions,  # type: ignore[arg-type]
            revision_id=submitted_manual.id,
        )
        assert (
            approved_manual.provenance
            == TimeEntryProvenance.AUTHORIZED_MANUAL_ENTRY.value
        )

        punch_start = NOW + timedelta(days=1)
        await service.record_punch(
            session,
            context=all_permissions,  # type: ignore[arg-type]
            command=RecordPunch(
                employee_id=seed.employee_id,
                branch_id=seed.branch_id,
                kind=PunchKind.CLOCK_IN,
                occurred_at=punch_start,
                timezone="America/New_York",
            ),
        )
        with pytest.raises(WorkdayConflictError):
            await service.record_punch(
                session,
                context=all_permissions,  # type: ignore[arg-type]
                command=RecordPunch(
                    employee_id=seed.employee_id,
                    branch_id=seed.branch_id,
                    kind=PunchKind.CLOCK_IN,
                    occurred_at=punch_start + timedelta(minutes=1),
                    timezone="America/New_York",
                ),
            )
        _, punch_revision = await service.record_punch(
            session,
            context=all_permissions,  # type: ignore[arg-type]
            command=RecordPunch(
                employee_id=seed.employee_id,
                branch_id=seed.branch_id,
                kind=PunchKind.CLOCK_OUT,
                occurred_at=punch_start + timedelta(hours=8),
                timezone="America/New_York",
            ),
        )
        assert punch_revision is not None
        submitted_punch = await service.submit(
            session,
            context=all_permissions,
            revision_id=punch_revision.id,  # type: ignore[arg-type]
        )
        approved_punch = await service.approve(
            session,
            context=all_permissions,  # type: ignore[arg-type]
            revision_id=submitted_punch.id,
        )
        assert approved_punch.provenance == TimeEntryProvenance.EMPLOYEE_PUNCH.value

        await service.record_manual_time(
            session,
            context=all_permissions,  # type: ignore[arg-type]
            command=RecordManualTime(
                employee_id=seed.employee_id,
                branch_id=seed.branch_id,
                work_date=date(2026, 8, 31),
                timezone="America/New_York",
                start_at=NOW + timedelta(days=2),
                end_at=NOW + timedelta(days=2, hours=1),
                approved_duration_minutes=None,
                reason="Unsubmitted synthetic entry",
            ),
        )

        period = await service.create_pay_period(
            session,
            context=all_permissions,  # type: ignore[arg-type]
            command=CreatePayPeriod(
                period_start=date(2026, 8, 29),
                period_end=date(2026, 9, 4),
                processing_date=date(2026, 9, 10),
                payday=date(2026, 9, 11),
                timezone="America/New_York",
                schedule_definition_id="synthetic.all-county.weekly-held-back",
                schedule_version=1,
            ),
        )
        first = await service.seal_payroll_input(
            session,
            context=all_permissions,  # type: ignore[arg-type]
            employee_id=seed.employee_id,
            pay_period=period,
        )
        replay = await service.seal_payroll_input(
            session,
            context=all_permissions,  # type: ignore[arg-type]
            employee_id=seed.employee_id,
            pay_period=period,
        )
        assert first.snapshot_digest == replay.snapshot_digest
        assert first.total_approved_minutes == 720
        assert len(first.approved_entries) == 2
        assert {value.provenance for value in first.approved_entries} == {
            TimeEntryProvenance.EMPLOYEE_PUNCH,
            TimeEntryProvenance.AUTHORIZED_MANUAL_ENTRY,
        }
        economics = to_economics_workday_time(first.approved_entries[0])
        assert economics.workday_time_id

        corrected = await service.correct(
            session,
            context=all_permissions,  # type: ignore[arg-type]
            command=CorrectTimeEntry(
                revision_id=approved_manual.id,
                start_at=NOW,
                end_at=NOW + timedelta(hours=5),
                approved_duration_minutes=None,
                reason="Manager-approved missed-punch correction",
            ),
        )
        resubmitted = await service.submit(
            session,
            context=all_permissions,
            revision_id=corrected.id,  # type: ignore[arg-type]
        )
        await service.approve(
            session,
            context=all_permissions,
            revision_id=resubmitted.id,  # type: ignore[arg-type]
        )
        changed = await service.seal_payroll_input(
            session,
            context=all_permissions,  # type: ignore[arg-type]
            employee_id=seed.employee_id,
            pay_period=period,
        )
        assert changed.snapshot_digest != first.snapshot_digest
        assert changed.total_approved_minutes == 780
        assert approved_manual.id in changed.approved_entries[0].correction_lineage
