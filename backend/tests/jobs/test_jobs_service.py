import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.customers.models import Customer, ServiceLocation
from app.events.models import BusinessEvent
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.jobs.commands import (
    ActivateJob,
    CancelJob,
    CompleteJob,
    CreateJob,
    CreateJobFromAppointment,
    LinkAppointment,
    PauseJob,
    ReopenJob,
    ResumeJob,
    StartJob,
    UpdateJob,
)
from app.jobs.errors import (
    AppointmentNotFoundError,
    JobCompletionBlockedError,
    JobInvalidTransitionError,
    JobNotFoundError,
    JobVersionConflictError,
)
from app.jobs.guards import JobGuardContext
from app.jobs.models import Job, JobAppointmentLink
from app.jobs.service import JobService
from app.jobs.types import (
    JobCancellationReason,
    JobPauseReason,
    JobPriority,
    JobReopeningReason,
    JobStatus,
)
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User
from app.scheduling.models import Appointment


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ServiceFixture:
    factory: async_sessionmaker[AsyncSession]
    context: AuthorizationContext
    company_id: UUID
    branch_id: UUID
    inaccessible_branch_id: UUID
    customer_id: UUID
    location_id: UUID
    second_customer_id: UUID
    second_location_id: UUID
    actor_id: UUID
    appointment_id: UUID
    other_appointment_id: UUID
    appointment_status: str
    customer_name: str


async def add_customer_graph(
    session: AsyncSession, *, prefix: str
) -> tuple[Company, Branch, Customer, ServiceLocation]:
    company = Company(
        name=f"{prefix} Company",
        code=f"J{uuid4().hex[:9].upper()}",
        status="active",
        timezone="America/New_York",
    )
    branch = Branch(
        company=company,
        name=f"{prefix} Branch",
        code=f"B{uuid4().hex[:9].upper()}",
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
        address="100 Service Test Street",
        city="Testville",
        state="NY",
        postal_code="10001",
        country="US",
        normalized_address=f"100 service test street {uuid4().hex}",
        active=True,
    )
    session.add_all([company, branch, customer, location])
    await session.flush()
    return company, branch, customer, location


@pytest_asyncio.fixture
async def service_fixture() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        company, branch, customer, location = await add_customer_graph(
            session, prefix="Job Service"
        )
        (
            other_company,
            other_branch,
            other_customer,
            other_location,
        ) = await add_customer_graph(session, prefix="Other Job Service")
        inaccessible_branch = Branch(
            company_id=company.id,
            name="Inaccessible Branch",
            code=f"B{uuid4().hex[:9].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=False,
        )
        second_customer = Customer(
            company_id=company.id,
            customer_number=f"CUS-{int(uuid4().hex[:8], 16):010d}",
            status="active",
            customer_type="commercial",
            display_name="Second Customer",
            preferred_contact_method="email",
            normalized_name=f"second customer {uuid4().hex}",
        )
        second_location = ServiceLocation(
            customer=second_customer,
            address="200 Service Test Street",
            city="Testville",
            state="NY",
            postal_code="10002",
            country="US",
            normalized_address=f"200 service test street {uuid4().hex}",
            active=True,
        )
        actor = User(
            normalized_email=f"jobs-service-{uuid4().hex}@example.test",
            first_name="Job",
            last_name="Operator",
            display_name="Job Operator",
            status="active",
        )
        session.add_all([inaccessible_branch, second_customer, second_location, actor])
        await session.flush()
        start = utc_now() + timedelta(days=1)
        appointment = Appointment(
            company_id=company.id,
            branch_id=branch.id,
            appointment_number=f"APT-{int(uuid4().hex[:6], 16):06d}",
            customer_id=customer.id,
            service_location_id=location.id,
            status="scheduled",
            arrival_window_start_at=start,
            arrival_window_end_at=start + timedelta(hours=2),
            expected_duration_minutes=90,
            scheduling_timezone="America/New_York",
        )
        other_appointment = Appointment(
            company_id=other_company.id,
            branch_id=other_branch.id,
            appointment_number=f"APT-{int(uuid4().hex[:6], 16):06d}",
            customer_id=other_customer.id,
            service_location_id=other_location.id,
            status="scheduled",
            arrival_window_start_at=start,
            arrival_window_end_at=start + timedelta(hours=2),
            expected_duration_minutes=90,
            scheduling_timezone="America/New_York",
        )
        session.add_all([appointment, other_appointment])
        await session.flush()
    membership = Membership(
        user_id=actor.id,
        company_id=company.id,
        status="active",
        has_all_branch_access=False,
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
        factory=factory,
        context=context,
        company_id=company.id,
        branch_id=branch.id,
        inaccessible_branch_id=inaccessible_branch.id,
        customer_id=customer.id,
        location_id=location.id,
        second_customer_id=second_customer.id,
        second_location_id=second_location.id,
        actor_id=actor.id,
        appointment_id=appointment.id,
        other_appointment_id=other_appointment.id,
        appointment_status=appointment.status,
        customer_name=customer.display_name,
    )
    try:
        yield fixture
    finally:
        await engine.dispose()


def create_command(fixture: ServiceFixture) -> CreateJob:
    return CreateJob(
        branch_id=fixture.branch_id,
        customer_id=fixture.customer_id,
        service_location_id=fixture.location_id,
        job_type_code="service_call",
        priority=JobPriority.HIGH,
        customer_reported_problem="No heat",
        internal_description="Diagnose system.",
    )


async def create_job(fixture: ServiceFixture, service: JobService | None = None) -> Job:
    async with fixture.factory() as session:
        return await (service or JobService()).create_job(
            session, context=fixture.context, command=create_command(fixture)
        )


@pytest.mark.asyncio
async def test_creation_is_atomic_and_stages_company_scoped_event(
    service_fixture: ServiceFixture,
) -> None:
    fixture = service_fixture
    job = await create_job(fixture)
    assert job.status == JobStatus.DRAFT.value
    assert job.concurrency_version == 1
    assert job.job_number.startswith("JOB-")
    async with fixture.factory() as session:
        event = await session.scalar(
            select(BusinessEvent).where(BusinessEvent.entity_id == job.id)
        )
        assert event is not None
        assert event.event_type == "job.created"
        assert event.company_id == fixture.company_id
        assert event.branch_id == fixture.branch_id
        assert event.payload["version"] == 1


@pytest.mark.asyncio
async def test_create_from_appointment_is_atomic_and_preserves_other_domains(
    service_fixture: ServiceFixture,
) -> None:
    fixture = service_fixture
    service = JobService()
    command = CreateJobFromAppointment(
        appointment_id=fixture.appointment_id,
        job_type_code="service_call",
        customer_reported_problem="No heat",
        internal_description="Diagnose system.",
    )
    async with fixture.factory() as session:
        job = await service.create_job_from_appointment(
            session, context=fixture.context, command=command
        )
    async with fixture.factory() as session:
        links = tuple(
            (
                await session.scalars(
                    select(JobAppointmentLink).where(
                        JobAppointmentLink.job_id == job.id
                    )
                )
            ).all()
        )
        events = tuple(
            (
                await session.scalars(
                    select(BusinessEvent)
                    .where(BusinessEvent.entity_id == job.id)
                    .order_by(BusinessEvent.event_type)
                )
            ).all()
        )
        appointment = await session.get(Appointment, fixture.appointment_id)
        customer = await session.get(Customer, fixture.customer_id)
        assert len(links) == 1
        assert [event.event_type for event in events] == [
            "job.appointment_linked",
            "job.created",
        ]
        assert events[0].occurred_at == events[1].occurred_at
        assert events[0].correlation_id == events[1].correlation_id
        assert (
            appointment is not None and appointment.status == fixture.appointment_status
        )
        assert customer is not None and customer.display_name == fixture.customer_name


@pytest.mark.asyncio
async def test_lifecycle_versions_retries_and_reopen_preserve_history(
    service_fixture: ServiceFixture,
) -> None:
    fixture = service_fixture
    service = JobService()
    job = await create_job(fixture, service)
    async with fixture.factory() as session:
        job = await service.activate_job(
            session,
            context=fixture.context,
            command=ActivateJob(job.id, expected_version=1),
        )
    assert job.status == "ready" and job.concurrency_version == 2
    async with fixture.factory() as session:
        job = await service.start_job(
            session, context=fixture.context, command=StartJob(job.id, 2)
        )
    assert job.status == "in_progress" and job.concurrency_version == 3
    async with fixture.factory() as session:
        job = await service.pause_job(
            session,
            context=fixture.context,
            command=PauseJob(job.id, 3, JobPauseReason.AWAITING_MATERIAL),
        )
    paused_version = job.concurrency_version
    async with fixture.factory() as session:
        retried = await service.pause_job(
            session,
            context=fixture.context,
            command=PauseJob(job.id, 3, JobPauseReason.AWAITING_MATERIAL),
        )
    assert retried.concurrency_version == paused_version
    async with fixture.factory() as session:
        job = await service.resume_job(
            session, context=fixture.context, command=ResumeJob(job.id, paused_version)
        )
    async with fixture.factory() as session:
        job = await service.complete_job(
            session,
            context=fixture.context,
            command=CompleteJob(job.id, job.concurrency_version),
        )
    completed_at = job.completed_at
    started_at = job.started_at
    completed_version = job.concurrency_version
    async with fixture.factory() as session:
        retried = await service.complete_job(
            session,
            context=fixture.context,
            command=CompleteJob(job.id, completed_version - 1),
        )
    assert retried.concurrency_version == completed_version
    async with fixture.factory() as session:
        job = await service.reopen_job(
            session,
            context=fixture.context,
            command=ReopenJob(
                job.id,
                completed_version,
                JobReopeningReason.ADDITIONAL_WORK_REQUIRED,
            ),
        )
    assert job.status == "ready"
    assert job.completed_at == completed_at
    assert job.started_at == started_at
    assert job.paused_at is None and job.pause_reason_code is None
    async with fixture.factory() as session:
        event_types = tuple(
            (
                await session.scalars(
                    select(BusinessEvent.event_type)
                    .where(BusinessEvent.entity_id == job.id)
                    .order_by(BusinessEvent.event_type)
                )
            ).all()
        )
    assert event_types.count("job.paused") == 1
    assert event_types.count("job.completed") == 1


@pytest.mark.asyncio
async def test_concurrent_lifecycle_transition_has_one_authoritative_winner(
    service_fixture: ServiceFixture,
) -> None:
    fixture = service_fixture
    service = JobService()
    job = await create_job(fixture, service)
    command = ActivateJob(job.id, expected_version=1)

    async def activate():
        async with fixture.factory() as session:
            return await service.activate_job(
                session, context=fixture.context, command=command
            )

    results = await asyncio.gather(activate(), activate(), return_exceptions=True)
    winners = [result for result in results if isinstance(result, Job)]
    conflicts = [
        result for result in results if isinstance(result, JobVersionConflictError)
    ]
    assert len(winners) == len(conflicts) == 1
    assert winners[0].status == JobStatus.READY.value
    assert winners[0].concurrency_version == 2
    async with fixture.factory() as session:
        persisted = await session.get(Job, job.id)
        event_count = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(
                BusinessEvent.entity_id == job.id,
                BusinessEvent.event_type == "job.activated",
            )
        )
    assert persisted is not None
    assert (persisted.status, persisted.concurrency_version) == ("ready", 2)
    assert event_count == 1


@pytest.mark.asyncio
async def test_cancel_is_retriable_but_active_cancellation_is_rejected(
    service_fixture: ServiceFixture,
) -> None:
    fixture = service_fixture
    service = JobService()
    job = await create_job(fixture, service)
    async with fixture.factory() as session:
        cancelled = await service.cancel_job(
            session,
            context=fixture.context,
            command=CancelJob(job.id, 1, JobCancellationReason.CUSTOMER_CANCELLED),
        )
    async with fixture.factory() as session:
        retried = await service.cancel_job(
            session,
            context=fixture.context,
            command=CancelJob(job.id, 1, JobCancellationReason.CUSTOMER_CANCELLED),
        )
    assert retried.concurrency_version == cancelled.concurrency_version == 2
    async with fixture.factory() as session:
        cancellation_count = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(
                BusinessEvent.entity_id == job.id,
                BusinessEvent.event_type == "job.cancelled",
            )
        )
    assert cancellation_count == 1
    async with fixture.factory() as session:
        with pytest.raises(JobInvalidTransitionError):
            await service.cancel_job(
                session,
                context=fixture.context,
                command=CancelJob(job.id, 1, JobCancellationReason.DUPLICATE),
            )

    active = await create_job(fixture, service)
    async with fixture.factory() as session:
        active = await service.activate_job(
            session, context=fixture.context, command=ActivateJob(active.id, 1)
        )
    async with fixture.factory() as session:
        active = await service.start_job(
            session, context=fixture.context, command=StartJob(active.id, 2)
        )
    async with fixture.factory() as session:
        with pytest.raises(JobInvalidTransitionError):
            await service.cancel_job(
                session,
                context=fixture.context,
                command=CancelJob(
                    active.id,
                    active.concurrency_version,
                    JobCancellationReason.DUPLICATE,
                ),
            )


@pytest.mark.asyncio
async def test_update_distinguishes_omitted_null_and_value_and_checks_version(
    service_fixture: ServiceFixture,
) -> None:
    fixture = service_fixture
    service = JobService()
    job = await create_job(fixture, service)
    async with fixture.factory() as session:
        updated = await service.update_job(
            session,
            context=fixture.context,
            command=UpdateJob(
                job.id,
                1,
                job_type_code=None,
                priority=JobPriority.EMERGENCY,
                customer_reported_problem="Updated problem",
            ),
        )
    assert updated.job_type_code is None
    assert updated.internal_description == "Diagnose system."
    assert updated.priority == "emergency"
    assert updated.concurrency_version == 2
    async with fixture.factory() as session:
        with pytest.raises(JobVersionConflictError):
            await service.update_job(
                session,
                context=fixture.context,
                command=UpdateJob(job.id, 1, priority=JobPriority.LOW),
            )


@pytest.mark.asyncio
async def test_customer_reference_becomes_immutable_after_link(
    service_fixture: ServiceFixture,
) -> None:
    fixture = service_fixture
    service = JobService()
    job = await create_job(fixture, service)
    async with fixture.factory() as session:
        linked = await service.link_appointment(
            session,
            context=fixture.context,
            command=LinkAppointment(job.id, fixture.appointment_id, 1, 1),
        )
    async with fixture.factory() as session:
        with pytest.raises(JobInvalidTransitionError):
            await service.update_job(
                session,
                context=fixture.context,
                command=UpdateJob(
                    job.id,
                    linked.concurrency_version,
                    customer_id=fixture.second_customer_id,
                    service_location_id=fixture.second_location_id,
                ),
            )


@pytest.mark.asyncio
async def test_inaccessible_same_company_branch_is_concealed(
    service_fixture: ServiceFixture,
) -> None:
    fixture = service_fixture
    command = CreateJob(
        branch_id=fixture.inaccessible_branch_id,
        customer_id=fixture.customer_id,
        service_location_id=fixture.location_id,
    )
    async with fixture.factory() as session:
        with pytest.raises(JobNotFoundError):
            await JobService().create_job(
                session, context=fixture.context, command=command
            )


@pytest.mark.asyncio
async def test_appointment_link_retry_and_concurrent_create_are_serialized(
    service_fixture: ServiceFixture,
) -> None:
    fixture = service_fixture
    service = JobService()
    job = await create_job(fixture, service)
    command = LinkAppointment(job.id, fixture.appointment_id, 1, 1)
    async with fixture.factory() as session:
        linked = await service.link_appointment(
            session, context=fixture.context, command=command
        )
    async with fixture.factory() as session:
        retried = await service.link_appointment(
            session, context=fixture.context, command=command
        )
    assert linked.concurrency_version == retried.concurrency_version == 2
    async with fixture.factory() as session:
        link_event_count = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(
                BusinessEvent.entity_id == job.id,
                BusinessEvent.event_type == "job.appointment_linked",
            )
        )
    assert link_event_count == 1

    second_command = CreateJobFromAppointment(
        appointment_id=fixture.other_appointment_id
    )
    async with fixture.factory() as session:
        with pytest.raises(AppointmentNotFoundError):
            await service.create_job_from_appointment(
                session, context=fixture.context, command=second_command
            )


@pytest.mark.asyncio
async def test_two_concurrent_create_from_appointment_calls_return_one_job(
    service_fixture: ServiceFixture,
) -> None:
    fixture = service_fixture
    service = JobService()
    command = CreateJobFromAppointment(appointment_id=fixture.appointment_id)

    async def invoke() -> UUID:
        async with fixture.factory() as session:
            job = await service.create_job_from_appointment(
                session, context=fixture.context, command=command
            )
            return job.id

    first, second = await asyncio.gather(invoke(), invoke())
    assert first == second
    async with fixture.factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(JobAppointmentLink)
                .where(JobAppointmentLink.appointment_id == fixture.appointment_id)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_service_request_job_creation_stages_one_linked_operations_event(
    service_fixture: ServiceFixture,
) -> None:
    fixture = service_fixture
    service = JobService()
    request_id = uuid4()
    command = CreateJobFromAppointment(
        appointment_id=fixture.appointment_id,
        service_request_id=request_id,
        customer_reported_problem="No cooling",
    )
    async with fixture.factory() as session:
        first = await service.create_job_from_appointment(
            session, context=fixture.context, command=command
        )
    async with fixture.factory() as session:
        replay = await service.create_job_from_appointment(
            session, context=fixture.context, command=command
        )
        events = tuple(
            (
                await session.scalars(
                    select(BusinessEvent).where(
                        BusinessEvent.entity_id == first.id,
                        BusinessEvent.event_type
                        == "operations.service_request.accepted",
                    )
                )
            ).all()
        )

    assert replay.id == first.id
    assert len(events) == 1
    assert events[0].correlation_id == request_id
    assert events[0].payload == {
        "service_request_id": str(request_id),
        "customer_id": str(fixture.customer_id),
        "service_location_id": str(fixture.location_id),
        "appointment_id": str(fixture.appointment_id),
        "job_id": str(first.id),
        "status": "accepted",
        "schema_version": 1,
    }


class BlockingCompletionGuard:
    async def validate_completion(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job: JobGuardContext,
        correlation_id: UUID,
    ) -> None:
        raise JobCompletionBlockedError("Completion is blocked.")


@pytest.mark.asyncio
async def test_guard_rejection_rolls_back_without_event(
    service_fixture: ServiceFixture,
) -> None:
    fixture = service_fixture
    ordinary = JobService()
    job = await create_job(fixture, ordinary)
    async with fixture.factory() as session:
        job = await ordinary.activate_job(
            session, context=fixture.context, command=ActivateJob(job.id, 1)
        )
    async with fixture.factory() as session:
        job = await ordinary.start_job(
            session, context=fixture.context, command=StartJob(job.id, 2)
        )
    service = JobService(completion_guards=(BlockingCompletionGuard(),))
    async with fixture.factory() as session:
        with pytest.raises(JobCompletionBlockedError):
            await service.complete_job(
                session,
                context=fixture.context,
                command=CompleteJob(job.id, job.concurrency_version),
            )
    async with fixture.factory() as session:
        persisted = await session.get(Job, job.id)
        count = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(
                BusinessEvent.entity_id == job.id,
                BusinessEvent.event_type == "job.completed",
            )
        )
        assert persisted is not None and persisted.status == "in_progress"
        assert count == 0


@pytest.mark.asyncio
async def test_event_failure_rolls_back_job_number_and_all_persistence(
    service_fixture: ServiceFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = service_fixture
    original_stage = BusinessEventService.stage

    def fail_after_stage(
        session: AsyncSession, event_data: BusinessEventCreate
    ) -> BusinessEvent:
        original_stage(session, event_data)
        raise RuntimeError("event staging failed")

    monkeypatch.setattr(BusinessEventService, "stage", fail_after_stage)
    async with fixture.factory() as session:
        with pytest.raises(RuntimeError, match="event staging failed"):
            await JobService().create_job(
                session, context=fixture.context, command=create_command(fixture)
            )
    monkeypatch.setattr(BusinessEventService, "stage", original_stage)
    async with fixture.factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.company_id == fixture.company_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(BusinessEvent.company_id == fixture.company_id)
            )
            == 0
        )
    created = await create_job(fixture)
    assert created.job_number == "JOB-000001"
