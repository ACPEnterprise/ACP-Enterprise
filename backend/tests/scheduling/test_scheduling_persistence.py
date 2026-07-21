import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.customers.models import Customer, ServiceLocation
from app.platform.auth import models as auth_models  # noqa: F401
from app.platform.audit import models as audit_models  # noqa: F401
from app.platform.branch.models import Branch
from app.platform.company import membership_models  # noqa: F401
from app.platform.company.models import Company
from app.platform.employees import models as employee_models  # noqa: F401
from app.platform.notifications import models as notification_models  # noqa: F401
from app.platform.permissions import models as permission_models  # noqa: F401
from app.platform.users import identity_models  # noqa: F401
from app.platform.users import models as user_models  # noqa: F401
from app.scheduling.models import (
    Appointment,
    AppointmentCapacityReservation,
    AppointmentNumberSequence,
    BranchSchedulingCalendar,
    BranchSchedulingException,
    BranchSchedulingWeeklyInterval,
)
from app.scheduling.repository import SchedulingRepository
from app.scheduling.types import AppointmentStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SchedulingFixture:
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    location_id: UUID
    other_company_id: UUID
    other_branch_id: UUID
    other_customer_id: UUID
    other_location_id: UUID


async def add_company_graph(
    session: AsyncSession, *, prefix: str
) -> tuple[UUID, UUID, UUID, UUID]:
    company_id = uuid4()
    branch_id = uuid4()
    customer_id = uuid4()
    location_id = uuid4()
    company_code = f"{prefix[:4].upper()}{uuid4().hex[:8].upper()}"
    session.add(
        Company(
            id=company_id,
            name=f"{prefix} Company",
            code=company_code,
            status="active",
            timezone="America/New_York",
        )
    )
    session.add(
        Branch(
            id=branch_id,
            company_id=company_id,
            name=f"{prefix} Branch",
            code=f"BR{uuid4().hex[:8].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
    )
    session.add(
        Customer(
            id=customer_id,
            company_id=company_id,
            customer_number=f"CUS-{int(uuid4().hex[:8], 16):010d}",
            status="active",
            customer_type="residential",
            display_name=f"{prefix} Customer",
            preferred_contact_method="phone",
            normalized_name=f"{prefix.lower()} customer",
        )
    )
    session.add(
        ServiceLocation(
            id=location_id,
            customer_id=customer_id,
            address="100 Test Street",
            city="Testville",
            state="NY",
            postal_code="10001",
            country="US",
            normalized_address=f"100 test street {uuid4().hex}",
            active=True,
        )
    )
    await session.flush()
    return company_id, branch_id, customer_id, location_id


@pytest_asyncio.fixture
async def scheduling_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        first = await add_company_graph(session, prefix="Scheduling A")
        second = await add_company_graph(session, prefix="Scheduling B")
    fixture = SchedulingFixture(*first, *second)
    try:
        yield engine, factory, fixture
    finally:
        async with factory() as session, session.begin():
            appointment_ids = select(Appointment.id).where(
                Appointment.company_id.in_(
                    (fixture.company_id, fixture.other_company_id)
                )
            )
            calendar_ids = select(BranchSchedulingCalendar.id).where(
                BranchSchedulingCalendar.company_id.in_(
                    (fixture.company_id, fixture.other_company_id)
                )
            )
            await session.execute(
                delete(AppointmentCapacityReservation).where(
                    AppointmentCapacityReservation.appointment_id.in_(appointment_ids)
                )
            )
            await session.execute(
                delete(BranchSchedulingException).where(
                    BranchSchedulingException.calendar_id.in_(calendar_ids)
                )
            )
            await session.execute(
                delete(BranchSchedulingWeeklyInterval).where(
                    BranchSchedulingWeeklyInterval.calendar_id.in_(calendar_ids)
                )
            )
            await session.execute(
                delete(BranchSchedulingCalendar).where(
                    BranchSchedulingCalendar.id.in_(calendar_ids)
                )
            )
            await session.execute(
                delete(Appointment).where(Appointment.id.in_(appointment_ids))
            )
            await session.execute(
                delete(AppointmentNumberSequence).where(
                    AppointmentNumberSequence.company_id.in_(
                        (fixture.company_id, fixture.other_company_id)
                    )
                )
            )
            await session.execute(
                delete(ServiceLocation).where(
                    ServiceLocation.id.in_(
                        (fixture.location_id, fixture.other_location_id)
                    )
                )
            )
            await session.execute(
                delete(Customer).where(
                    Customer.id.in_((fixture.customer_id, fixture.other_customer_id))
                )
            )
            await session.execute(
                delete(Branch).where(
                    Branch.id.in_((fixture.branch_id, fixture.other_branch_id))
                )
            )
            await session.execute(
                delete(Company).where(
                    Company.id.in_((fixture.company_id, fixture.other_company_id))
                )
            )
        await engine.dispose()


def build_appointment(
    fixture: SchedulingFixture,
    *,
    appointment_number: str = "APT-000001",
    status: AppointmentStatus = AppointmentStatus.SCHEDULED,
    window_start_at: datetime | None = None,
    window_end_at: datetime | None = None,
    expected_duration_minutes: int | None = 90,
) -> Appointment:
    start = window_start_at or (utc_now() + timedelta(days=1))
    end = window_end_at or (start + timedelta(hours=2))
    return Appointment(
        company_id=fixture.company_id,
        branch_id=fixture.branch_id,
        appointment_number=appointment_number,
        customer_id=fixture.customer_id,
        service_location_id=fixture.location_id,
        status=status.value,
        arrival_window_start_at=start,
        arrival_window_end_at=end,
        expected_duration_minutes=expected_duration_minutes,
        scheduling_timezone="America/New_York",
    )


async def create_calendar(
    session: AsyncSession,
    fixture: SchedulingFixture,
) -> BranchSchedulingCalendar:
    return await SchedulingRepository.create_branch_calendar(
        session,
        calendar=BranchSchedulingCalendar(
            company_id=fixture.company_id,
            branch_id=fixture.branch_id,
            booking_horizon_days=180,
            minimum_notice_minutes=60,
            slot_interval_minutes=30,
            default_capacity_units=Decimal("4.00"),
        ),
    )


@pytest.mark.asyncio
async def test_appointment_creation_retrieval_lifecycle_and_number_allocation(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
) -> None:
    _, factory, fixture = scheduling_database
    async with factory() as session, session.begin():
        first_number = await SchedulingRepository.next_appointment_number(
            session, company_id=fixture.company_id
        )
        second_number = await SchedulingRepository.next_appointment_number(
            session, company_id=fixture.company_id
        )
        assert first_number == "APT-000001"
        assert second_number == "APT-000002"
        appointment = await SchedulingRepository.create_appointment(
            session,
            appointment=build_appointment(
                fixture,
                appointment_number=first_number,
                status=AppointmentStatus.CONFIRMED,
            ),
        )

    async with factory() as session:
        retrieved = await SchedulingRepository.get_appointment(
            session,
            company_id=fixture.company_id,
            appointment_id=appointment.id,
        )
        by_number = await SchedulingRepository.get_appointment_by_number(
            session,
            company_id=fixture.company_id,
            appointment_number=first_number,
        )
        assert retrieved is not None
        assert by_number is not None and by_number.id == retrieved.id
        assert retrieved.status == AppointmentStatus.CONFIRMED.value
        assert retrieved.branch_id == fixture.branch_id
        assert retrieved.arrival_window_start_at is not None
        assert retrieved.arrival_window_end_at is not None
        assert retrieved.arrival_window_start_at.tzinfo is not None
        assert retrieved.arrival_window_end_at.tzinfo is not None
        assert retrieved.expected_duration_minutes == 90
        assert await SchedulingRepository.appointment_number_exists(
            session,
            company_id=fixture.company_id,
            appointment_number=first_number,
        )


@pytest.mark.asyncio
async def test_company_scoped_retrieval_conceals_cross_company_appointment(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
) -> None:
    _, factory, fixture = scheduling_database
    async with factory() as session, session.begin():
        appointment = await SchedulingRepository.create_appointment(
            session, appointment=build_appointment(fixture)
        )
    async with factory() as session:
        assert (
            await SchedulingRepository.get_appointment(
                session,
                company_id=fixture.other_company_id,
                appointment_id=appointment.id,
            )
            is None
        )


@pytest.mark.asyncio
async def test_appointment_number_is_unique_within_company(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
) -> None:
    _, factory, fixture = scheduling_database
    async with factory() as session:
        session.add_all(
            [
                build_appointment(fixture),
                build_appointment(fixture),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("end_delta", "duration"),
    [(timedelta(0), 60), (timedelta(hours=-1), 60), (timedelta(hours=1), 0)],
)
async def test_invalid_arrival_window_and_duration_are_rejected(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
    end_delta: timedelta,
    duration: int,
) -> None:
    _, factory, fixture = scheduling_database
    start = utc_now() + timedelta(days=1)
    async with factory() as session:
        session.add(
            build_appointment(
                fixture,
                window_start_at=start,
                window_end_at=start + end_delta,
                expected_duration_minutes=duration,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_invalid_lifecycle_and_capacity_quantity_are_rejected(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
) -> None:
    _, factory, fixture = scheduling_database
    invalid_status = build_appointment(fixture)
    invalid_status.status = "assigned"
    async with factory() as session:
        session.add(invalid_status)
        with pytest.raises(IntegrityError):
            await session.commit()

    start = utc_now() + timedelta(days=1)
    end = start + timedelta(hours=2)
    appointment = build_appointment(fixture, window_start_at=start, window_end_at=end)
    async with factory() as session, session.begin():
        await SchedulingRepository.create_appointment(session, appointment=appointment)
        await create_calendar(session, fixture)
    async with factory() as session:
        session.add(
            AppointmentCapacityReservation(
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                appointment_id=appointment.id,
                reserved_start_at=start,
                reserved_end_at=end,
                capacity_units=Decimal("0"),
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_cross_company_branch_customer_and_location_references_are_rejected(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
) -> None:
    _, factory, fixture = scheduling_database
    invalid_branch = build_appointment(fixture)
    invalid_branch.branch_id = fixture.other_branch_id
    async with factory() as session:
        session.add(invalid_branch)
        with pytest.raises(IntegrityError):
            await session.commit()

    invalid_customer = build_appointment(fixture)
    invalid_customer.customer_id = fixture.other_customer_id
    invalid_customer.service_location_id = fixture.other_location_id
    async with factory() as session:
        session.add(invalid_customer)
        with pytest.raises(DBAPIError):
            await session.commit()

    mismatched_location = build_appointment(fixture)
    mismatched_location.service_location_id = fixture.other_location_id
    async with factory() as session:
        session.add(mismatched_location)
        with pytest.raises(DBAPIError):
            await session.commit()


@pytest.mark.asyncio
async def test_capacity_reservation_persistence_overlap_and_release_filter(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
) -> None:
    _, factory, fixture = scheduling_database
    start = utc_now() + timedelta(days=1)
    appointment = build_appointment(
        fixture,
        window_start_at=start,
        window_end_at=start + timedelta(hours=2),
    )
    async with factory() as session, session.begin():
        await SchedulingRepository.create_appointment(session, appointment=appointment)
        await create_calendar(session, fixture)
        capacity_context = await SchedulingRepository.lock_capacity_context(
            session,
            company_id=fixture.company_id,
            branch_id=fixture.branch_id,
        )
        assert capacity_context is not None
        reservation = await SchedulingRepository.create_capacity_reservation(
            session,
            capacity_context=capacity_context,
            reservation=AppointmentCapacityReservation(
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                appointment_id=appointment.id,
                reserved_start_at=start,
                reserved_end_at=start + timedelta(minutes=90),
                capacity_units=Decimal("1.50"),
            ),
        )

    async with factory() as session:
        capacity_context = await SchedulingRepository.lock_capacity_context(
            session,
            company_id=fixture.company_id,
            branch_id=fixture.branch_id,
        )
        assert capacity_context is not None
        persisted = await SchedulingRepository.get_capacity_reservation(
            session,
            company_id=fixture.company_id,
            appointment_id=appointment.id,
        )
        overlaps = await SchedulingRepository.get_overlapping_capacity_reservations(
            session,
            capacity_context=capacity_context,
            window_start_at=start + timedelta(minutes=30),
            window_end_at=start + timedelta(hours=3),
        )
        adjacent = await SchedulingRepository.get_overlapping_capacity_reservations(
            session,
            capacity_context=capacity_context,
            window_start_at=start + timedelta(minutes=90),
            window_end_at=start + timedelta(hours=3),
        )
        assert persisted is not None
        assert persisted.capacity_units == Decimal("1.50")
        assert [record.id for record in overlaps] == [reservation.id]
        assert adjacent == []


@pytest.mark.asyncio
async def test_repository_row_lock_serializes_appointment_updates(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
) -> None:
    _, factory, fixture = scheduling_database
    async with factory() as session, session.begin():
        appointment = await SchedulingRepository.create_appointment(
            session, appointment=build_appointment(fixture)
        )

    first_locked = asyncio.Event()
    release_first = asyncio.Event()
    second_acquired = asyncio.Event()

    async def first_writer() -> None:
        async with factory() as session, session.begin():
            record = await SchedulingRepository.get_appointment_for_update(
                session,
                company_id=fixture.company_id,
                appointment_id=appointment.id,
            )
            assert record is not None
            first_locked.set()
            await release_first.wait()

    async def second_writer() -> None:
        await first_locked.wait()
        async with factory() as session, session.begin():
            record = await SchedulingRepository.get_appointment_for_update(
                session,
                company_id=fixture.company_id,
                appointment_id=appointment.id,
            )
            assert record is not None
            second_acquired.set()

    first_task = asyncio.create_task(first_writer())
    second_task = asyncio.create_task(second_writer())
    await first_locked.wait()
    await asyncio.sleep(0.05)
    assert not second_acquired.is_set()
    release_first.set()
    await asyncio.gather(first_task, second_task)
    assert second_acquired.is_set()


@pytest.mark.asyncio
async def test_branch_calendar_weekly_interval_and_exception_persistence(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
) -> None:
    _, factory, fixture = scheduling_database
    exception_date = date(2026, 12, 25)
    async with factory() as session, session.begin():
        calendar = await create_calendar(session, fixture)
        await SchedulingRepository.add_weekly_interval(
            session,
            company_id=fixture.company_id,
            branch_id=fixture.branch_id,
            interval=BranchSchedulingWeeklyInterval(
                calendar_id=calendar.id,
                day_of_week=0,
                start_minute=480,
                end_minute=1020,
                capacity_units=Decimal("4.00"),
            ),
        )
        await SchedulingRepository.add_calendar_exception(
            session,
            company_id=fixture.company_id,
            branch_id=fixture.branch_id,
            exception=BranchSchedulingException(
                calendar_id=calendar.id,
                exception_date=exception_date,
                is_closed=True,
                reason_code="holiday_closure",
            ),
        )

    async with factory() as session:
        persisted = await SchedulingRepository.get_branch_calendar(
            session,
            company_id=fixture.company_id,
            branch_id=fixture.branch_id,
        )
        assert persisted is not None
        assert persisted.default_capacity_units == Decimal("4.00")
        exceptions = await SchedulingRepository.calendar_capacity_for_date(
            session,
            company_id=fixture.company_id,
            branch_id=fixture.branch_id,
            calendar_id=persisted.id,
            exception_date=exception_date,
        )
        assert len(exceptions) == 1
        assert exceptions[0].is_closed


@pytest.mark.asyncio
async def test_invalid_appointment_reference_updates_are_rejected(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
) -> None:
    _, factory, fixture = scheduling_database
    async with factory() as session, session.begin():
        appointment = await SchedulingRepository.create_appointment(
            session, appointment=build_appointment(fixture)
        )

    async with factory() as session:
        record = await session.get(Appointment, appointment.id)
        assert record is not None
        record.customer_id = fixture.other_customer_id
        record.service_location_id = fixture.other_location_id
        with pytest.raises(DBAPIError):
            await session.commit()

    async with factory() as session:
        record = await session.get(Appointment, appointment.id)
        assert record is not None
        record.service_location_id = fixture.other_location_id
        with pytest.raises(DBAPIError):
            await session.commit()


@pytest.mark.asyncio
async def test_parent_identity_updates_cannot_break_appointment_references(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
) -> None:
    _, factory, fixture = scheduling_database
    async with factory() as session, session.begin():
        await SchedulingRepository.create_appointment(
            session, appointment=build_appointment(fixture)
        )

    async with factory() as session:
        customer = await session.get(Customer, fixture.customer_id)
        assert customer is not None
        customer.company_id = fixture.other_company_id
        with pytest.raises(DBAPIError):
            await session.commit()

    async with factory() as session:
        location = await session.get(ServiceLocation, fixture.location_id)
        assert location is not None
        location.customer_id = fixture.other_customer_id
        with pytest.raises(DBAPIError):
            await session.commit()


@pytest.mark.asyncio
async def test_calendar_children_are_concealed_across_companies(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
) -> None:
    _, factory, fixture = scheduling_database
    exception_date = date(2026, 12, 31)
    async with factory() as session, session.begin():
        calendar = await create_calendar(session, fixture)
        interval = BranchSchedulingWeeklyInterval(
            calendar_id=calendar.id,
            day_of_week=1,
            start_minute=480,
            end_minute=1020,
            capacity_units=Decimal("4.00"),
        )
        exception = BranchSchedulingException(
            calendar_id=calendar.id,
            exception_date=exception_date,
            is_closed=True,
            reason_code="year_end_closure",
        )
        assert (
            await SchedulingRepository.add_weekly_interval(
                session,
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                interval=interval,
            )
            is interval
        )
        assert (
            await SchedulingRepository.add_calendar_exception(
                session,
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                exception=exception,
            )
            is exception
        )

    async with factory() as session:
        assert (
            await SchedulingRepository.get_branch_calendar(
                session,
                company_id=fixture.other_company_id,
                branch_id=fixture.branch_id,
            )
            is None
        )
        assert (
            await SchedulingRepository.get_weekly_intervals(
                session,
                company_id=fixture.other_company_id,
                branch_id=fixture.branch_id,
                calendar_id=calendar.id,
            )
            == []
        )
        assert (
            await SchedulingRepository.calendar_capacity_for_date(
                session,
                company_id=fixture.other_company_id,
                branch_id=fixture.branch_id,
                calendar_id=calendar.id,
                exception_date=exception_date,
            )
            == []
        )
        assert (
            await SchedulingRepository.add_weekly_interval(
                session,
                company_id=fixture.other_company_id,
                branch_id=fixture.other_branch_id,
                interval=BranchSchedulingWeeklyInterval(
                    calendar_id=calendar.id,
                    day_of_week=2,
                    start_minute=480,
                    end_minute=1020,
                    capacity_units=Decimal("4.00"),
                ),
            )
            is None
        )
        assert (
            await SchedulingRepository.add_calendar_exception(
                session,
                company_id=fixture.other_company_id,
                branch_id=fixture.other_branch_id,
                exception=BranchSchedulingException(
                    calendar_id=calendar.id,
                    exception_date=exception_date,
                    is_closed=True,
                    reason_code="unauthorized_change",
                ),
            )
            is None
        )


@pytest.mark.asyncio
async def test_capacity_context_serializes_branch_capacity_evaluation(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
) -> None:
    _, factory, fixture = scheduling_database
    async with factory() as session, session.begin():
        await create_calendar(session, fixture)

    first_locked = asyncio.Event()
    release_first = asyncio.Event()
    second_acquired = asyncio.Event()

    async def first_evaluator() -> None:
        async with factory() as session, session.begin():
            context = await SchedulingRepository.lock_capacity_context(
                session,
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
            )
            assert context is not None
            first_locked.set()
            await release_first.wait()

    async def second_evaluator() -> None:
        await first_locked.wait()
        async with factory() as session, session.begin():
            context = await SchedulingRepository.lock_capacity_context(
                session,
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
            )
            assert context is not None
            second_acquired.set()

    first_task = asyncio.create_task(first_evaluator())
    second_task = asyncio.create_task(second_evaluator())
    await first_locked.wait()
    await asyncio.sleep(0.05)
    assert not second_acquired.is_set()
    release_first.set()
    await asyncio.gather(first_task, second_task)
    assert second_acquired.is_set()


@pytest.mark.asyncio
async def test_scheduling_integrity_triggers_are_installed(
    scheduling_database: tuple[
        AsyncEngine, async_sessionmaker[AsyncSession], SchedulingFixture
    ],
) -> None:
    _, factory, _ = scheduling_database
    async with factory() as session:
        trigger_names = set(
            (
                await session.scalars(
                    text(
                        "SELECT trigger_name FROM information_schema.triggers "
                        "WHERE trigger_name IN "
                        "('trg_appointments_customer_location', "
                        "'trg_customers_protect_appointment_company', "
                        "'trg_service_locations_protect_appointment_customer')"
                    )
                )
            ).all()
        )
        function_names = set(
            (
                await session.scalars(
                    text(
                        "SELECT proname FROM pg_proc WHERE proname IN "
                        "('validate_appointment_customer_location', "
                        "'protect_appointment_customer_company', "
                        "'protect_appointment_service_location_customer')"
                    )
                )
            ).all()
        )
    assert trigger_names == {
        "trg_appointments_customer_location",
        "trg_customers_protect_appointment_company",
        "trg_service_locations_protect_appointment_customer",
    }
    assert function_names == {
        "validate_appointment_customer_location",
        "protect_appointment_customer_company",
        "protect_appointment_service_location_customer",
    }
