import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.analytics.service import AnalyticsService
from app.core.config import settings
from app.customers.models import Customer, ServiceLocation
from app.events.models import BusinessEvent
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.jobs.commands import ActivateJob, CancelJob, ReopenJob
from app.jobs.models import JobAppointmentLink
from app.jobs.service import JobService
from app.jobs.types import JobCancellationReason, JobPriority, JobReopeningReason
from app.operations.service import OperationsService
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User
from app.scheduling.errors import (
    SchedulingCapacityError,
    SchedulingConflictError,
    SchedulingNotFoundError,
    SchedulingValidationError,
    SchedulingVersionConflictError,
)
from app.scheduling.models import (
    Appointment,
    AppointmentCapacityReservation,
    BranchSchedulingCalendar,
    BranchSchedulingException,
    BranchSchedulingWeeklyInterval,
)
from app.scheduling.repository import SchedulingRepository
from app.scheduling.service import (
    CancelAppointmentCommand,
    CreateAppointmentCommand,
    RescheduleAppointmentCommand,
    SchedulingService,
)
from app.scheduling.types import (
    AppointmentCancellationReason,
    AppointmentRescheduleReason,
)

BUSINESS_TIMEZONE = ZoneInfo("America/New_York")
BUSINESS_TODAY = datetime.now(timezone.utc).astimezone(BUSINESS_TIMEZONE).date()
FIXED_NOW = datetime.combine(
    BUSINESS_TODAY, time.min, tzinfo=BUSINESS_TIMEZONE
).astimezone(timezone.utc)
FIRST_START = datetime.combine(
    BUSINESS_TODAY + timedelta(days=1),
    time(hour=10),
    tzinfo=BUSINESS_TIMEZONE,
).astimezone(timezone.utc)


@dataclass(frozen=True)
class ServiceFixture:
    company: Company
    branch: Branch
    customer: Customer
    location: ServiceLocation
    other_company: Company
    other_branch: Branch
    actor: User
    context: AuthorizationContext


async def add_company_graph(
    session: AsyncSession, *, prefix: str
) -> tuple[Company, Branch, Customer, ServiceLocation]:
    company = Company(
        name=f"{prefix} Company",
        code=f"{prefix[:3].upper()}{uuid4().hex[:8].upper()}",
        status="active",
        timezone="America/New_York",
    )
    branch = Branch(
        company=company,
        name=f"{prefix} Branch",
        code=f"BR{uuid4().hex[:8].upper()}",
        status="active",
        timezone="America/New_York",
        is_primary=True,
    )
    customer = Customer(
        company=company,
        customer_number=f"CUS-{int(uuid4().hex[:8], 16):010d}",
        status="active",
        customer_type="residential",
        display_name=f"{prefix} Customer",
        preferred_contact_method="phone",
        normalized_name=f"{prefix.lower()} customer",
    )
    location = ServiceLocation(
        customer=customer,
        address="100 Test Street",
        city="Testville",
        state="NY",
        postal_code="10001",
        country="US",
        normalized_address=f"100 test street {uuid4().hex}",
        active=True,
    )
    session.add_all([company, branch, customer, location])
    await session.flush()
    return company, branch, customer, location


@pytest_asyncio.fixture
async def service_database() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], ServiceFixture]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        company, branch, customer, location = await add_company_graph(
            session, prefix="Service A"
        )
        other_company, other_branch, _, _ = await add_company_graph(
            session, prefix="Service B"
        )
        actor = User(
            normalized_email=f"scheduler-{uuid4().hex}@example.test",
            first_name="Schedule",
            last_name="Operator",
            display_name="Schedule Operator",
            status="active",
        )
        session.add(actor)
        await session.flush()
        calendar = await SchedulingRepository.create_branch_calendar(
            session,
            calendar=BranchSchedulingCalendar(
                company_id=company.id,
                branch_id=branch.id,
                booking_horizon_days=180,
                minimum_notice_minutes=30,
                slot_interval_minutes=30,
                default_capacity_units=Decimal("2.00"),
            ),
        )
        for day in range(7):
            await SchedulingRepository.add_weekly_interval(
                session,
                company_id=company.id,
                branch_id=branch.id,
                interval=BranchSchedulingWeeklyInterval(
                    calendar_id=calendar.id,
                    day_of_week=day,
                    start_minute=8 * 60,
                    end_minute=18 * 60,
                    capacity_units=Decimal("2.00"),
                ),
            )
    membership = Membership(
        user_id=actor.id,
        company_id=company.id,
        status="active",
        has_all_branch_access=True,
    )
    context = AuthorizationContext(
        user=actor,
        company=company,
        membership=membership,
        authorized_branches=(branch,),
        active_branch=branch,
        effective_roles=(),
        effective_permissions=(),
        credential_version=1,
        authorization_version=1,
    )
    fixture = ServiceFixture(
        company=company,
        branch=branch,
        customer=customer,
        location=location,
        other_company=other_company,
        other_branch=other_branch,
        actor=actor,
        context=context,
    )
    try:
        yield factory, fixture
    finally:
        await engine.dispose()


def create_command(
    fixture: ServiceFixture,
    *,
    start: datetime = FIRST_START,
    capacity_units: Decimal = Decimal("1.00"),
) -> CreateAppointmentCommand:
    return CreateAppointmentCommand(
        branch_id=fixture.branch.id,
        customer_id=fixture.customer.id,
        service_location_id=fixture.location.id,
        arrival_window_start_at=start,
        arrival_window_end_at=start + timedelta(hours=1),
        expected_duration_minutes=60,
        capacity_units=capacity_units,
    )


async def add_calendar_exception(
    factory: async_sessionmaker[AsyncSession],
    fixture: ServiceFixture,
    *,
    start_minute: int | None,
    end_minute: int | None,
    is_closed: bool,
    capacity_units: Decimal | None,
) -> None:
    async with factory() as session, session.begin():
        calendar = await SchedulingRepository.get_branch_calendar(
            session,
            company_id=fixture.company.id,
            branch_id=fixture.branch.id,
        )
        assert calendar is not None
        record = await SchedulingRepository.add_calendar_exception(
            session,
            company_id=fixture.company.id,
            branch_id=fixture.branch.id,
            exception=BranchSchedulingException(
                calendar_id=calendar.id,
                exception_date=FIRST_START.astimezone(
                    timezone(timedelta(hours=-4))
                ).date(),
                start_minute=start_minute,
                end_minute=end_minute,
                is_closed=is_closed,
                capacity_units=capacity_units,
                reason_code="test_calendar_policy",
            ),
        )
        assert record is not None


@pytest.mark.asyncio
async def test_creation_allocates_number_reserves_capacity_and_stages_event(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    service = SchedulingService(clock=lambda: FIXED_NOW)
    async with factory() as session:
        appointment = await service.create_appointment(
            session, context=fixture.context, command=create_command(fixture)
        )
    assert appointment.appointment_number == "APT-000001"
    assert appointment.status == "scheduled"
    assert appointment.concurrency_version == 1
    async with factory() as session:
        reservation = await SchedulingRepository.get_capacity_reservation(
            session,
            company_id=fixture.company.id,
            appointment_id=appointment.id,
        )
        events = list(
            (
                await session.scalars(
                    select(BusinessEvent)
                    .where(BusinessEvent.entity_id == appointment.id)
                    .order_by(BusinessEvent.event_type)
                )
            ).all()
        )
        analytics = await AnalyticsService.get_today_summary(
            session, company_id=fixture.company.id
        )
    assert reservation is not None
    assert reservation.capacity_units == Decimal("1.00")
    assert [event.event_type for event in events] == [
        "appointment.booked",
        "appointment.created",
    ]
    assert all(event.company_id == fixture.company.id for event in events)
    assert all(event.entity_id == appointment.id for event in events)
    assert all(event.branch_id == fixture.branch.id for event in events)
    assert events[0].occurred_at == events[1].occurred_at == FIXED_NOW
    assert analytics.appointments_booked.value == 1


@pytest.mark.asyncio
async def test_creation_is_tenant_scoped_and_numbering_is_company_scoped(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    service = SchedulingService(clock=lambda: FIXED_NOW)
    unauthorized = CreateAppointmentCommand(
        **{
            **create_command(fixture).__dict__,
            "branch_id": fixture.other_branch.id,
        }
    )
    async with factory() as session:
        with pytest.raises(SchedulingNotFoundError):
            await service.create_appointment(
                session, context=fixture.context, command=unauthorized
            )
        first = await service.create_appointment(
            session, context=fixture.context, command=create_command(fixture)
        )
        second = await service.create_appointment(
            session,
            context=fixture.context,
            command=create_command(fixture, start=FIRST_START + timedelta(hours=2)),
        )
    assert (first.appointment_number, second.appointment_number) == (
        "APT-000001",
        "APT-000002",
    )


@pytest.mark.asyncio
async def test_creation_retry_uses_deterministic_appointment_without_duplicate_evidence(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    request_id = uuid4()
    command = CreateAppointmentCommand(
        **{
            **create_command(fixture).__dict__,
            "idempotency_key": request_id,
        }
    )
    service = SchedulingService(clock=lambda: FIXED_NOW)

    async with factory() as session:
        first = await service.create_appointment(
            session, context=fixture.context, command=command
        )
        replay = await service.create_appointment(
            session, context=fixture.context, command=command
        )

    assert (
        first.id
        == replay.id
        == uuid5(fixture.company.id, f"operations.service_request:{request_id}")
    )
    assert first.appointment_number == replay.appointment_number == "APT-000001"
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(Appointment.id)).where(
                    Appointment.company_id == fixture.company.id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(BusinessEvent.id)).where(
                    BusinessEvent.entity_id == first.id
                )
            )
            == 2
        )


@pytest.mark.asyncio
async def test_creation_rejects_conflicting_idempotency_replay(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    request_id = uuid4()
    original = CreateAppointmentCommand(
        **{
            **create_command(fixture).__dict__,
            "idempotency_key": request_id,
        }
    )
    conflict = CreateAppointmentCommand(
        **{
            **create_command(fixture, start=FIRST_START + timedelta(hours=2)).__dict__,
            "idempotency_key": request_id,
        }
    )
    async with factory() as session:
        await SchedulingService(clock=lambda: FIXED_NOW).create_appointment(
            session, context=fixture.context, command=original
        )
        with pytest.raises(SchedulingConflictError):
            await SchedulingService(clock=lambda: FIXED_NOW).create_appointment(
                session, context=fixture.context, command=conflict
            )


@pytest.mark.asyncio
async def test_concurrent_idempotent_creation_returns_one_appointment(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    request_id = uuid4()
    command = CreateAppointmentCommand(
        **{
            **create_command(fixture).__dict__,
            "idempotency_key": request_id,
        }
    )
    service = SchedulingService(clock=lambda: FIXED_NOW)

    async def invoke() -> UUID:
        async with factory() as session:
            appointment = await service.create_appointment(
                session, context=fixture.context, command=command
            )
            return appointment.id

    first, second = await asyncio.gather(invoke(), invoke())
    assert first == second
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(Appointment.id)).where(
                    Appointment.company_id == fixture.company.id
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_launch_workflow_links_retries_reschedules_cancels_and_reopens(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    request_id = uuid4()
    scheduling = SchedulingService(clock=lambda: FIXED_NOW)
    jobs = JobService(clock=lambda: FIXED_NOW)
    operations = OperationsService(scheduling=scheduling, jobs=jobs)
    appointment_command = CreateAppointmentCommand(
        **{
            **create_command(fixture).__dict__,
            "idempotency_key": request_id,
        }
    )

    async with factory() as session:
        first = await operations.accept_service_request(
            session,
            context=fixture.context,
            request_id=request_id,
            appointment=appointment_command,
            job_type_code="repair",
            priority=JobPriority.HIGH,
            customer_reported_problem="No cooling",
            internal_description=None,
        )
        replay = await operations.accept_service_request(
            session,
            context=fixture.context,
            request_id=request_id,
            appointment=appointment_command,
            job_type_code="repair",
            priority=JobPriority.HIGH,
            customer_reported_problem="No cooling",
            internal_description=None,
        )
    assert replay.appointment.id == first.appointment.id
    assert replay.job.id == first.job.id

    async with factory() as session:
        rescheduled = await scheduling.reschedule_appointment(
            session,
            context=fixture.context,
            command=RescheduleAppointmentCommand(
                appointment_id=first.appointment.id,
                expected_version=1,
                arrival_window_start_at=FIRST_START + timedelta(hours=2),
                arrival_window_end_at=FIRST_START + timedelta(hours=3),
                expected_duration_minutes=60,
                capacity_units=Decimal("1.00"),
                reason_code=AppointmentRescheduleReason.CUSTOMER_REQUEST,
            ),
        )
        activated = await jobs.activate_job(
            session,
            context=fixture.context,
            command=ActivateJob(first.job.id, 1),
        )
    assert rescheduled.concurrency_version == 2
    assert activated.status == "ready"

    async with factory() as session:
        cancelled_appointment = await scheduling.cancel_appointment(
            session,
            context=fixture.context,
            command=CancelAppointmentCommand(
                first.appointment.id,
                rescheduled.concurrency_version,
                AppointmentCancellationReason.CUSTOMER_REQUEST,
            ),
        )
        cancelled_job = await jobs.cancel_job(
            session,
            context=fixture.context,
            command=CancelJob(
                first.job.id,
                activated.concurrency_version,
                JobCancellationReason.CUSTOMER_CANCELLED,
            ),
        )
        assert cancelled_job.status == "cancelled"
        reopened = await jobs.reopen_job(
            session,
            context=fixture.context,
            command=ReopenJob(
                first.job.id,
                cancelled_job.concurrency_version,
                JobReopeningReason.CUSTOMER_CALLBACK,
            ),
        )
    assert cancelled_appointment.status == "cancelled"
    assert reopened.status == "ready"

    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(JobAppointmentLink.id)).where(
                    JobAppointmentLink.appointment_id == first.appointment.id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(BusinessEvent.id)).where(
                    BusinessEvent.event_type == "operations.service_request.accepted",
                    BusinessEvent.correlation_id == request_id,
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_partial_closed_exception_overlap_rejects_creation(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    await add_calendar_exception(
        factory,
        fixture,
        start_minute=10 * 60 + 30,
        end_minute=11 * 60,
        is_closed=True,
        capacity_units=None,
    )
    async with factory() as session:
        with pytest.raises(SchedulingCapacityError):
            await SchedulingService(clock=lambda: FIXED_NOW).create_appointment(
                session, context=fixture.context, command=create_command(fixture)
            )


@pytest.mark.asyncio
async def test_boundary_touching_closed_exception_does_not_overlap(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    await add_calendar_exception(
        factory,
        fixture,
        start_minute=9 * 60,
        end_minute=10 * 60,
        is_closed=True,
        capacity_units=None,
    )
    async with factory() as session:
        appointment = await SchedulingService(
            clock=lambda: FIXED_NOW
        ).create_appointment(
            session, context=fixture.context, command=create_command(fixture)
        )
    assert appointment.status == "scheduled"


@pytest.mark.asyncio
async def test_full_day_closure_rejects_creation(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    await add_calendar_exception(
        factory,
        fixture,
        start_minute=None,
        end_minute=None,
        is_closed=True,
        capacity_units=None,
    )
    async with factory() as session:
        with pytest.raises(SchedulingCapacityError):
            await SchedulingService(clock=lambda: FIXED_NOW).create_appointment(
                session, context=fixture.context, command=create_command(fixture)
            )


@pytest.mark.asyncio
async def test_open_exception_can_override_weekly_availability(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    await add_calendar_exception(
        factory,
        fixture,
        start_minute=18 * 60,
        end_minute=20 * 60,
        is_closed=False,
        capacity_units=Decimal("1.00"),
    )
    outside_weekly_start = FIRST_START + timedelta(hours=8, minutes=30)
    async with factory() as session:
        appointment = await SchedulingService(
            clock=lambda: FIXED_NOW
        ).create_appointment(
            session,
            context=fixture.context,
            command=create_command(fixture, start=outside_weekly_start),
        )
    assert appointment.arrival_window_start_at == outside_weekly_start


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "start",
    [
        FIRST_START + timedelta(seconds=1),
        FIRST_START + timedelta(microseconds=1),
    ],
)
async def test_slot_alignment_rejects_seconds_and_microseconds(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
    start: datetime,
) -> None:
    factory, fixture = service_database
    async with factory() as session:
        with pytest.raises(SchedulingValidationError):
            await SchedulingService(clock=lambda: FIXED_NOW).create_appointment(
                session,
                context=fixture.context,
                command=create_command(fixture, start=start),
            )


@pytest.mark.asyncio
async def test_arrival_window_must_fit_when_working_interval_fits(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    start = FIRST_START + timedelta(hours=7, minutes=30)
    command = CreateAppointmentCommand(
        branch_id=fixture.branch.id,
        customer_id=fixture.customer.id,
        service_location_id=fixture.location.id,
        arrival_window_start_at=start,
        arrival_window_end_at=start + timedelta(hours=1),
        expected_duration_minutes=30,
    )
    async with factory() as session:
        with pytest.raises(SchedulingCapacityError):
            await SchedulingService(clock=lambda: FIXED_NOW).create_appointment(
                session, context=fixture.context, command=command
            )


@pytest.mark.asyncio
async def test_working_interval_must_fit_when_arrival_window_fits(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    start = FIRST_START + timedelta(hours=7)
    command = CreateAppointmentCommand(
        branch_id=fixture.branch.id,
        customer_id=fixture.customer.id,
        service_location_id=fixture.location.id,
        arrival_window_start_at=start,
        arrival_window_end_at=start + timedelta(minutes=30),
        expected_duration_minutes=90,
    )
    async with factory() as session:
        with pytest.raises(SchedulingCapacityError):
            await SchedulingService(clock=lambda: FIXED_NOW).create_appointment(
                session, context=fixture.context, command=command
            )


@pytest.mark.asyncio
async def test_insufficient_capacity_fails_without_partial_persistence(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    service = SchedulingService(clock=lambda: FIXED_NOW)
    async with factory() as session:
        await service.create_appointment(
            session,
            context=fixture.context,
            command=create_command(fixture, capacity_units=Decimal("2.00")),
        )
        with pytest.raises(SchedulingCapacityError):
            await service.create_appointment(
                session, context=fixture.context, command=create_command(fixture)
            )
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(Appointment.company_id == fixture.company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AppointmentCapacityReservation)
                .where(
                    AppointmentCapacityReservation.appointment_id.in_(
                        select(Appointment.id).where(
                            Appointment.company_id == fixture.company.id
                        )
                    )
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(BusinessEvent.company_id == fixture.company.id)
            )
            == 2
        )


@pytest.mark.asyncio
async def test_concurrent_capacity_requests_are_serialized(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    async with factory() as session, session.begin():
        calendar = await SchedulingRepository.get_branch_calendar(
            session,
            company_id=fixture.company.id,
            branch_id=fixture.branch.id,
            for_update=True,
        )
        assert calendar is not None
        calendar.default_capacity_units = Decimal("1.00")
        intervals = await SchedulingRepository.get_weekly_intervals(
            session,
            company_id=fixture.company.id,
            branch_id=fixture.branch.id,
            calendar_id=calendar.id,
        )
        for interval in intervals:
            interval.capacity_units = Decimal("1.00")

    async def attempt() -> str:
        async with factory() as session:
            try:
                await SchedulingService(clock=lambda: FIXED_NOW).create_appointment(
                    session, context=fixture.context, command=create_command(fixture)
                )
                return "created"
            except SchedulingCapacityError:
                return "capacity"

    assert sorted(await asyncio.gather(attempt(), attempt())) == [
        "capacity",
        "created",
    ]


@pytest.mark.asyncio
async def test_cancellation_releases_capacity_and_is_idempotent(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    service = SchedulingService(clock=lambda: FIXED_NOW)
    async with factory() as session:
        appointment = await service.create_appointment(
            session, context=fixture.context, command=create_command(fixture)
        )
        cancelled = await service.cancel_appointment(
            session,
            context=fixture.context,
            command=CancelAppointmentCommand(
                appointment_id=appointment.id,
                expected_version=1,
                reason_code=AppointmentCancellationReason.CUSTOMER_REQUEST,
            ),
        )
        repeated = await service.cancel_appointment(
            session,
            context=fixture.context,
            command=CancelAppointmentCommand(
                appointment_id=appointment.id,
                expected_version=1,
                reason_code=AppointmentCancellationReason.CUSTOMER_REQUEST,
            ),
        )
    assert cancelled.status == "cancelled"
    assert repeated.concurrency_version == 2
    async with factory() as session:
        reservation = await SchedulingRepository.get_capacity_reservation(
            session,
            company_id=fixture.company.id,
            appointment_id=appointment.id,
        )
        cancellation_events = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(
                BusinessEvent.company_id == fixture.company.id,
                BusinessEvent.entity_id == appointment.id,
                BusinessEvent.event_type == "appointment.cancelled",
            )
        )
    assert reservation is not None and reservation.released_at == FIXED_NOW
    assert cancellation_events == 1


@pytest.mark.asyncio
async def test_reschedule_moves_capacity_and_rejects_stale_version(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    service = SchedulingService(clock=lambda: FIXED_NOW)
    replacement = FIRST_START + timedelta(days=1)
    async with factory() as session:
        appointment = await service.create_appointment(
            session, context=fixture.context, command=create_command(fixture)
        )
        appointment_id = appointment.id
        moved = await service.reschedule_appointment(
            session,
            context=fixture.context,
            command=RescheduleAppointmentCommand(
                appointment_id=appointment_id,
                expected_version=1,
                arrival_window_start_at=replacement,
                arrival_window_end_at=replacement + timedelta(hours=1),
                expected_duration_minutes=90,
                capacity_units=Decimal("1.00"),
                reason_code=AppointmentRescheduleReason.CUSTOMER_REQUEST,
            ),
        )
        assert moved.arrival_window_start_at == replacement
        assert moved.reschedule_count == 1
        assert moved.concurrency_version == 2
        other_context = AuthorizationContext(
            user=fixture.actor,
            company=fixture.other_company,
            membership=Membership(
                user_id=fixture.actor.id,
                company_id=fixture.other_company.id,
                status="active",
                has_all_branch_access=True,
            ),
            authorized_branches=(fixture.other_branch,),
            active_branch=fixture.other_branch,
            effective_roles=(),
            effective_permissions=(),
            credential_version=1,
            authorization_version=1,
        )
        with pytest.raises(SchedulingNotFoundError):
            await service.reschedule_appointment(
                session,
                context=other_context,
                command=RescheduleAppointmentCommand(
                    appointment_id=appointment_id,
                    expected_version=2,
                    arrival_window_start_at=replacement + timedelta(days=1),
                    arrival_window_end_at=replacement + timedelta(days=1, hours=1),
                    expected_duration_minutes=60,
                    capacity_units=Decimal("1.00"),
                    reason_code=AppointmentRescheduleReason.CUSTOMER_REQUEST,
                ),
            )
        with pytest.raises(SchedulingVersionConflictError):
            await service.reschedule_appointment(
                session,
                context=fixture.context,
                command=RescheduleAppointmentCommand(
                    appointment_id=appointment_id,
                    expected_version=1,
                    arrival_window_start_at=replacement + timedelta(days=1),
                    arrival_window_end_at=replacement + timedelta(days=1, hours=1),
                    expected_duration_minutes=60,
                    capacity_units=Decimal("1.00"),
                    reason_code=AppointmentRescheduleReason.CUSTOMER_REQUEST,
                ),
            )
    async with factory() as session:
        reservation = await SchedulingRepository.get_capacity_reservation(
            session,
            company_id=fixture.company.id,
            appointment_id=appointment_id,
        )
        event = await session.scalar(
            select(BusinessEvent).where(
                BusinessEvent.event_type == "appointment.rescheduled"
            )
        )
    assert reservation is not None and reservation.reserved_start_at == replacement
    assert event is not None


@pytest.mark.asyncio
async def test_unsupported_cancellation_and_reschedule_reasons_are_rejected(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
) -> None:
    factory, fixture = service_database
    service = SchedulingService(clock=lambda: FIXED_NOW)
    async with factory() as session:
        appointment = await service.create_appointment(
            session, context=fixture.context, command=create_command(fixture)
        )
        with pytest.raises(SchedulingValidationError):
            await service.cancel_appointment(
                session,
                context=fixture.context,
                command=CancelAppointmentCommand(
                    appointment_id=appointment.id,
                    expected_version=1,
                    reason_code=cast(
                        AppointmentCancellationReason, "private customer notes"
                    ),
                ),
            )
        with pytest.raises(SchedulingValidationError):
            await service.reschedule_appointment(
                session,
                context=fixture.context,
                command=RescheduleAppointmentCommand(
                    appointment_id=appointment.id,
                    expected_version=1,
                    arrival_window_start_at=FIRST_START + timedelta(days=1),
                    arrival_window_end_at=FIRST_START + timedelta(days=1, hours=1),
                    expected_duration_minutes=60,
                    capacity_units=Decimal("1.00"),
                    reason_code=cast(
                        AppointmentRescheduleReason, "unsupported operational detail"
                    ),
                ),
            )


@pytest.mark.asyncio
async def test_event_staging_failure_rolls_back_appointment_and_reservation(
    service_database: tuple[async_sessionmaker[AsyncSession], ServiceFixture],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, fixture = service_database
    original_stage = BusinessEventService.stage

    def fail_after_stage(
        session: AsyncSession, event_data: BusinessEventCreate
    ) -> BusinessEvent:
        original_stage(session, event_data)
        raise RuntimeError("controlled event staging failure")

    monkeypatch.setattr(BusinessEventService, "stage", fail_after_stage)
    async with factory() as session:
        with pytest.raises(RuntimeError, match="controlled event staging failure"):
            await SchedulingService(clock=lambda: FIXED_NOW).create_appointment(
                session, context=fixture.context, command=create_command(fixture)
            )
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(Appointment.company_id == fixture.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AppointmentCapacityReservation)
                .where(
                    AppointmentCapacityReservation.appointment_id.in_(
                        select(Appointment.id).where(
                            Appointment.company_id == fixture.company.id
                        )
                    )
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(BusinessEvent.company_id == fixture.company.id)
            )
            == 0
        )
