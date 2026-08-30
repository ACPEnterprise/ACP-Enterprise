import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.customers.models import Customer, ServiceLocation
from app.jobs.models import Job, JobAppointmentLink
from app.jobs.repository import JobRepository
from app.jobs.types import JobPriority, JobStatus
from app.platform.audit import models as audit_models  # noqa: F401
from app.platform.auth import models as auth_models  # noqa: F401
from app.platform.branch.models import Branch
from app.platform.company import membership_models  # noqa: F401
from app.platform.company.models import Company
from app.platform.employees import models as employee_models  # noqa: F401
from app.platform.notifications import models as notification_models  # noqa: F401
from app.platform.permissions import models as permission_models  # noqa: F401
from app.platform.users import identity_models  # noqa: F401
from app.platform.users.models import User
from app.scheduling.models import Appointment


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class JobsFixture:
    company_id: UUID
    branch_id: UUID
    secondary_branch_id: UUID
    customer_id: UUID
    location_id: UUID
    alternate_location_id: UUID
    second_customer_id: UUID
    second_location_id: UUID
    other_company_id: UUID
    other_branch_id: UUID
    other_customer_id: UUID
    other_location_id: UUID
    user_id: UUID


async def add_company_graph(
    session: AsyncSession, *, prefix: str
) -> tuple[UUID, UUID, UUID, UUID]:
    company_id, branch_id, customer_id, location_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    session.add(
        Company(
            id=company_id,
            name=f"{prefix} Company",
            code=f"{prefix[:3].upper()}{uuid4().hex[:8].upper()}",
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
            address="100 Jobs Test Street",
            city="Testville",
            state="NY",
            postal_code="10001",
            country="US",
            normalized_address=f"100 jobs test street {uuid4().hex}",
            active=True,
        )
    )
    await session.flush()
    return company_id, branch_id, customer_id, location_id


@pytest_asyncio.fixture
async def jobs_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        first = await add_company_graph(session, prefix="Jobs A")
        second = await add_company_graph(session, prefix="Jobs B")
        secondary_branch_id = uuid4()
        session.add(
            Branch(
                id=secondary_branch_id,
                company_id=first[0],
                name="Jobs A Secondary Branch",
                code=f"BR{uuid4().hex[:8].upper()}",
                status="active",
                timezone="America/New_York",
                is_primary=False,
            )
        )
        second_customer_id, second_location_id, alternate_location_id = (
            uuid4(),
            uuid4(),
            uuid4(),
        )
        session.add(
            Customer(
                id=second_customer_id,
                company_id=first[0],
                customer_number=f"CUS-{int(uuid4().hex[:8], 16):010d}",
                status="active",
                customer_type="commercial",
                display_name="Jobs A Second Customer",
                preferred_contact_method="email",
                normalized_name="jobs a second customer",
            )
        )
        session.add(
            ServiceLocation(
                id=second_location_id,
                customer_id=second_customer_id,
                address="200 Jobs Test Street",
                city="Testville",
                state="NY",
                postal_code="10002",
                country="US",
                normalized_address=f"200 jobs test street {uuid4().hex}",
                active=True,
            )
        )
        session.add(
            ServiceLocation(
                id=alternate_location_id,
                customer_id=first[2],
                address="101 Jobs Test Street",
                city="Testville",
                state="NY",
                postal_code="10001",
                country="US",
                normalized_address=f"101 jobs test street {uuid4().hex}",
                active=True,
            )
        )
        user = User(
            normalized_email=f"jobs-{uuid4().hex}@example.test",
            first_name="Jobs",
            last_name="Tester",
            display_name="Jobs Tester",
            status="active",
        )
        session.add(user)
        await session.flush()
    fixture = JobsFixture(
        company_id=first[0],
        branch_id=first[1],
        secondary_branch_id=secondary_branch_id,
        customer_id=first[2],
        location_id=first[3],
        alternate_location_id=alternate_location_id,
        second_customer_id=second_customer_id,
        second_location_id=second_location_id,
        other_company_id=second[0],
        other_branch_id=second[1],
        other_customer_id=second[2],
        other_location_id=second[3],
        user_id=user.id,
    )
    try:
        yield engine, factory, fixture
    finally:
        await engine.dispose()


def build_job(
    fixture: JobsFixture,
    *,
    job_number: str = "JOB-000001",
    company_id: UUID | None = None,
    branch_id: UUID | None = None,
    customer_id: UUID | None = None,
    location_id: UUID | None = None,
    status: JobStatus = JobStatus.DRAFT,
    now: datetime | None = None,
) -> Job:
    timestamp = now or utc_now()
    lifecycle: dict[str, object] = {}
    if status in {
        JobStatus.READY,
        JobStatus.IN_PROGRESS,
        JobStatus.PAUSED,
        JobStatus.COMPLETED,
    }:
        lifecycle["activated_at"] = timestamp
    if status in {JobStatus.IN_PROGRESS, JobStatus.PAUSED, JobStatus.COMPLETED}:
        lifecycle["started_at"] = timestamp
    if status is JobStatus.PAUSED:
        lifecycle.update(paused_at=timestamp, pause_reason_code="awaiting_material")
    if status is JobStatus.COMPLETED:
        lifecycle.update(completed_at=timestamp, completed_by_user_id=fixture.user_id)
    if status is JobStatus.CANCELLED:
        lifecycle.update(
            cancelled_at=timestamp,
            cancelled_by_user_id=fixture.user_id,
            cancellation_reason_code="customer_request",
        )
    return Job(
        company_id=company_id or fixture.company_id,
        branch_id=branch_id or fixture.branch_id,
        job_number=job_number,
        customer_id=customer_id or fixture.customer_id,
        service_location_id=location_id or fixture.location_id,
        status=status.value,
        job_type_code="service_call",
        priority=JobPriority.NORMAL.value,
        customer_reported_problem="No hot water",
        internal_description="Inspect the water heater.",
        concurrency_version=1,
        created_by_user_id=fixture.user_id,
        updated_by_user_id=fixture.user_id,
        **lifecycle,
    )


def build_appointment(
    fixture: JobsFixture,
    *,
    appointment_number: str,
    customer_id: UUID | None = None,
    location_id: UUID | None = None,
) -> Appointment:
    start = utc_now() + timedelta(days=1)
    return Appointment(
        company_id=fixture.company_id,
        branch_id=fixture.branch_id,
        appointment_number=appointment_number,
        customer_id=customer_id or fixture.customer_id,
        service_location_id=location_id or fixture.location_id,
        status="scheduled",
        arrival_window_start_at=start,
        arrival_window_end_at=start + timedelta(hours=2),
        expected_duration_minutes=90,
        scheduling_timezone="America/New_York",
    )


@pytest.mark.asyncio
async def test_job_creation_retrieval_uuid_timestamps_and_company_numbering(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        number = await JobRepository.next_job_number(
            session, company_id=fixture.company_id
        )
        job = await JobRepository.create_job(
            session, job=build_job(fixture, job_number=number)
        )
    async with factory() as session:
        record = await JobRepository.get_job(
            session, company_id=fixture.company_id, job_id=job.id
        )
        by_number = await JobRepository.get_job_by_number(
            session, company_id=fixture.company_id, job_number=number
        )
        assert record is not None and by_number is not None
        assert record.id == by_number.id == job.id
        assert record.job_number == "JOB-000001"
        assert record.created_at.tzinfo is not None
        assert record.updated_at.tzinfo is not None
        assert record.status == JobStatus.DRAFT.value
        assert record.priority == JobPriority.NORMAL.value


@pytest.mark.asyncio
async def test_numbering_is_independent_by_company_and_rolls_back(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    with pytest.raises(RuntimeError, match="rollback"):
        async with factory() as session, session.begin():
            assert (
                await JobRepository.next_job_number(
                    session, company_id=fixture.company_id
                )
                == "JOB-000001"
            )
            raise RuntimeError("rollback")
    async with factory() as session, session.begin():
        assert (
            await JobRepository.next_job_number(session, company_id=fixture.company_id)
            == "JOB-000001"
        )
        assert (
            await JobRepository.next_job_number(
                session, company_id=fixture.other_company_id
            )
            == "JOB-000001"
        )


@pytest.mark.asyncio
async def test_concurrent_number_allocation_is_atomic(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database

    async def allocate() -> str:
        async with factory() as session, session.begin():
            return await JobRepository.next_job_number(
                session, company_id=fixture.company_id
            )

    assert set(await asyncio.gather(allocate(), allocate())) == {
        "JOB-000001",
        "JOB-000002",
    }


@pytest.mark.asyncio
async def test_job_number_and_company_branch_constraints(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session:
        session.add_all([build_job(fixture), build_job(fixture)])
        with pytest.raises((IntegrityError, DBAPIError)):
            await session.commit()
    async with factory() as session:
        session.add(build_job(fixture, branch_id=fixture.other_branch_id))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_customer_and_service_location_ownership_constraints(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session:
        session.add(
            build_job(
                fixture,
                customer_id=fixture.other_customer_id,
                location_id=fixture.other_location_id,
            )
        )
        with pytest.raises(DBAPIError):
            await session.commit()
    async with factory() as session:
        session.add(build_job(fixture, location_id=fixture.second_location_id))
        with pytest.raises(DBAPIError):
            await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", list(JobStatus))
async def test_valid_lifecycle_states_persist(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    status: JobStatus,
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        await JobRepository.create_job(
            session,
            job=build_job(
                fixture,
                job_number=f"JOB-{list(JobStatus).index(status) + 1:06d}",
                status=status,
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "dispatched"),
        ("priority", "critical"),
        ("job_type_code", "Invalid Type"),
        ("job_type_code", "x" * 65),
        ("concurrency_version", 0),
    ],
)
async def test_invalid_status_priority_type_and_version_are_rejected(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    field: str,
    value: object,
) -> None:
    _, factory, fixture = jobs_database
    job = build_job(fixture)
    setattr(job, field, value)
    async with factory() as session:
        session.add(job)
        with pytest.raises((IntegrityError, DBAPIError)):
            await session.commit()


def add_draft_activation(job: Job, _fixture: JobsFixture, now: datetime) -> None:
    job.activated_at = now


def omit_pause_metadata(job: Job, _fixture: JobsFixture, now: datetime) -> None:
    job.status = JobStatus.PAUSED.value
    job.activated_at = now
    job.started_at = now


def omit_completion_actor(job: Job, _fixture: JobsFixture, now: datetime) -> None:
    job.status = JobStatus.COMPLETED.value
    job.activated_at = now
    job.started_at = now
    job.completed_at = now


def omit_cancellation_actor(job: Job, _fixture: JobsFixture, now: datetime) -> None:
    job.status = JobStatus.CANCELLED.value
    job.cancelled_at = now
    job.cancellation_reason_code = "customer_request"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        add_draft_activation,
        omit_pause_metadata,
        omit_completion_actor,
        omit_cancellation_actor,
    ],
)
async def test_incoherent_lifecycle_metadata_is_rejected(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    mutate: Callable[[Job, JobsFixture, datetime], None],
) -> None:
    _, factory, fixture = jobs_database
    job = build_job(fixture)
    mutate(job, fixture, utc_now())
    async with factory() as session:
        session.add(job)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("completed_at", "completed_by_user_id"),
    [(None, "user"), ("timestamp", None)],
)
async def test_partial_completion_attribution_is_rejected(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    completed_at: str | None,
    completed_by_user_id: str | None,
) -> None:
    _, factory, fixture = jobs_database
    now = utc_now()
    job = build_job(fixture, status=JobStatus.READY)
    job.completed_at = now if completed_at else None
    job.completed_by_user_id = fixture.user_id if completed_by_user_id else None
    async with factory() as session:
        session.add(job)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_completed_status_requires_complete_completion_attribution(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    job = build_job(fixture, status=JobStatus.COMPLETED)
    job.completed_at = None
    job.completed_by_user_id = None
    async with factory() as session:
        session.add(job)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cancelled_at", "cancelled_by_user_id", "reason"),
    [
        ("timestamp", "user", None),
        ("timestamp", None, "customer_cancelled"),
        (None, "user", "customer_cancelled"),
    ],
)
async def test_partial_cancellation_attribution_is_rejected(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    cancelled_at: str | None,
    cancelled_by_user_id: str | None,
    reason: str | None,
) -> None:
    _, factory, fixture = jobs_database
    job = build_job(fixture, status=JobStatus.READY)
    job.cancelled_at = utc_now() if cancelled_at else None
    job.cancelled_by_user_id = fixture.user_id if cancelled_by_user_id else None
    job.cancellation_reason_code = reason
    async with factory() as session:
        session.add(job)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_cancelled_status_requires_complete_cancellation_attribution(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    job = build_job(fixture, status=JobStatus.CANCELLED)
    job.cancelled_at = None
    job.cancelled_by_user_id = None
    job.cancellation_reason_code = None
    async with factory() as session:
        session.add(job)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_ready_job_retains_historical_terminal_and_started_facts(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    now = utc_now()
    job = build_job(fixture, status=JobStatus.READY)
    job.started_at = now
    job.completed_at = now
    job.completed_by_user_id = fixture.user_id
    job.cancelled_at = now
    job.cancelled_by_user_id = fixture.user_id
    job.cancellation_reason_code = "customer_cancelled"

    async with factory() as session, session.begin():
        await JobRepository.create_job(session, job=job)

    async with factory() as session:
        persisted = await JobRepository.get_job(
            session, company_id=fixture.company_id, job_id=job.id
        )
        assert persisted is not None
        assert persisted.status == JobStatus.READY.value
        assert persisted.started_at == now
        assert persisted.completed_at == now
        assert persisted.completed_by_user_id == fixture.user_id
        assert persisted.cancelled_at == now
        assert persisted.cancelled_by_user_id == fixture.user_id
        assert persisted.cancellation_reason_code == "customer_cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [JobStatus.IN_PROGRESS, JobStatus.PAUSED, JobStatus.COMPLETED],
)
async def test_active_and_completed_states_require_started_at(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    status: JobStatus,
) -> None:
    _, factory, fixture = jobs_database
    job = build_job(fixture, status=status)
    job.started_at = None
    async with factory() as session:
        session.add(job)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_draft_rejects_historical_started_at(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    job = build_job(fixture)
    job.started_at = utc_now()
    async with factory() as session:
        session.add(job)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_multiple_appointments_link_to_one_job_in_visit_order(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        job = await JobRepository.create_job(session, job=build_job(fixture))
        first = build_appointment(fixture, appointment_number="APT-900001")
        second = build_appointment(fixture, appointment_number="APT-900002")
        session.add_all([first, second])
        await session.flush()
        await JobRepository.create_appointment_link(
            session,
            link=JobAppointmentLink(
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                job_id=job.id,
                appointment_id=second.id,
                visit_sequence=2,
                linked_by_user_id=fixture.user_id,
            ),
        )
        await JobRepository.create_appointment_link(
            session,
            link=JobAppointmentLink(
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                job_id=job.id,
                appointment_id=first.id,
                visit_sequence=1,
                linked_by_user_id=fixture.user_id,
            ),
        )
    async with factory() as session:
        links = await JobRepository.list_appointment_links(
            session, company_id=fixture.company_id, job_id=job.id
        )
        assert [link.appointment_id for link in links] == [first.id, second.id]
        assert links[0].linked_at.tzinfo is not None


@pytest.mark.asyncio
async def test_one_appointment_can_structurally_link_to_multiple_jobs(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        first_job = await JobRepository.create_job(session, job=build_job(fixture))
        second_job = await JobRepository.create_job(
            session, job=build_job(fixture, job_number="JOB-000002")
        )
        appointment = build_appointment(fixture, appointment_number="APT-900003")
        session.add(appointment)
        await session.flush()
        for job in (first_job, second_job):
            await JobRepository.create_appointment_link(
                session,
                link=JobAppointmentLink(
                    company_id=fixture.company_id,
                    branch_id=fixture.branch_id,
                    job_id=job.id,
                    appointment_id=appointment.id,
                    visit_sequence=1,
                ),
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate_kind", ["appointment", "visit"])
async def test_duplicate_job_appointment_or_visit_is_rejected(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    duplicate_kind: str,
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        job = await JobRepository.create_job(session, job=build_job(fixture))
        first = build_appointment(fixture, appointment_number="APT-900004")
        second = build_appointment(fixture, appointment_number="APT-900005")
        session.add_all([first, second])
        await session.flush()
        await JobRepository.create_appointment_link(
            session,
            link=JobAppointmentLink(
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                job_id=job.id,
                appointment_id=first.id,
                visit_sequence=1,
            ),
        )
    async with factory() as session:
        session.add(
            JobAppointmentLink(
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                job_id=job.id,
                appointment_id=(
                    first.id if duplicate_kind == "appointment" else second.id
                ),
                visit_sequence=(2 if duplicate_kind == "appointment" else 1),
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_same_visit_sequence_is_permitted_across_jobs(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        first_job = await JobRepository.create_job(session, job=build_job(fixture))
        second_job = await JobRepository.create_job(
            session, job=build_job(fixture, job_number="JOB-000002")
        )
        appointments = [
            build_appointment(fixture, appointment_number="APT-900006"),
            build_appointment(fixture, appointment_number="APT-900007"),
        ]
        session.add_all(appointments)
        await session.flush()
        for job, appointment in zip((first_job, second_job), appointments, strict=True):
            await JobRepository.create_appointment_link(
                session,
                link=JobAppointmentLink(
                    company_id=fixture.company_id,
                    branch_id=fixture.branch_id,
                    job_id=job.id,
                    appointment_id=appointment.id,
                    visit_sequence=1,
                ),
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("customer_field", "location_field"),
    [
        ("second_customer_id", "second_location_id"),
        ("customer_id", "alternate_location_id"),
    ],
)
async def test_link_rejects_customer_and_service_location_mismatch(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    customer_field: str,
    location_field: str,
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        job = await JobRepository.create_job(session, job=build_job(fixture))
        appointment = build_appointment(
            fixture,
            appointment_number="APT-900008",
            customer_id=getattr(fixture, customer_field),
            location_id=getattr(fixture, location_field),
        )
        session.add(appointment)
    async with factory() as session:
        session.add(
            JobAppointmentLink(
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                job_id=job.id,
                appointment_id=appointment.id,
                visit_sequence=1,
            )
        )
        with pytest.raises(DBAPIError):
            await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("company_field", "branch_field"),
    [
        ("other_company_id", "other_branch_id"),
        ("company_id", "secondary_branch_id"),
    ],
)
async def test_link_rejects_company_and_branch_mismatch(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    company_field: str,
    branch_field: str,
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        job = await JobRepository.create_job(session, job=build_job(fixture))
        appointment = build_appointment(fixture, appointment_number="APT-900009")
        session.add(appointment)
    async with factory() as session:
        session.add(
            JobAppointmentLink(
                company_id=getattr(fixture, company_field),
                branch_id=getattr(fixture, branch_field),
                job_id=job.id,
                appointment_id=appointment.id,
                visit_sequence=1,
            )
        )
        with pytest.raises((IntegrityError, DBAPIError)):
            await session.commit()


@pytest.mark.asyncio
async def test_parent_changes_cannot_invalidate_job_or_appointment_link(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        job = await JobRepository.create_job(session, job=build_job(fixture))
        appointment = build_appointment(fixture, appointment_number="APT-900010")
        session.add(appointment)
        await session.flush()
        await JobRepository.create_appointment_link(
            session,
            link=JobAppointmentLink(
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                job_id=job.id,
                appointment_id=appointment.id,
                visit_sequence=1,
            ),
        )
    async with factory() as session:
        job_record = await session.get(Job, job.id)
        assert job_record is not None
        job_record.customer_id = fixture.second_customer_id
        job_record.service_location_id = fixture.second_location_id
        with pytest.raises(DBAPIError):
            await session.commit()
    async with factory() as session:
        appointment_record = await session.get(Appointment, appointment.id)
        assert appointment_record is not None
        appointment_record.customer_id = fixture.second_customer_id
        appointment_record.service_location_id = fixture.second_location_id
        with pytest.raises(DBAPIError):
            await session.commit()


@pytest.mark.asyncio
async def test_restrict_deletion_preserves_referenced_records(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        job = await JobRepository.create_job(session, job=build_job(fixture))
        appointment = build_appointment(fixture, appointment_number="APT-900011")
        session.add(appointment)
        await session.flush()
        await JobRepository.create_appointment_link(
            session,
            link=JobAppointmentLink(
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                job_id=job.id,
                appointment_id=appointment.id,
                visit_sequence=1,
            ),
        )
    async with factory() as session:
        customer = await session.get(Customer, fixture.customer_id)
        assert customer is not None
        await session.delete(customer)
        with pytest.raises(IntegrityError):
            await session.commit()
    async with factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(delete(Job).where(Job.id == job.id))
    async with factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                delete(Appointment).where(Appointment.id == appointment.id)
            )


@pytest.mark.asyncio
async def test_repository_conceals_and_locks_by_company(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        job = await JobRepository.create_job(session, job=build_job(fixture))
    async with factory() as session:
        assert (
            await JobRepository.get_job(
                session, company_id=fixture.other_company_id, job_id=job.id
            )
            is None
        )
        assert (
            await JobRepository.get_job_for_update(
                session, company_id=fixture.other_company_id, job_id=job.id
            )
            is None
        )

    locked = asyncio.Event()
    release = asyncio.Event()
    second_acquired = asyncio.Event()

    async def first_writer() -> None:
        async with factory() as session, session.begin():
            assert (
                await JobRepository.get_job_for_update(
                    session, company_id=fixture.company_id, job_id=job.id
                )
                is not None
            )
            locked.set()
            await release.wait()

    async def second_writer() -> None:
        await locked.wait()
        async with factory() as session, session.begin():
            assert (
                await JobRepository.get_job_for_update(
                    session, company_id=fixture.company_id, job_id=job.id
                )
                is not None
            )
            second_acquired.set()

    first_task = asyncio.create_task(first_writer())
    second_task = asyncio.create_task(second_writer())
    await locked.wait()
    await asyncio.sleep(0.05)
    assert not second_acquired.is_set()
    release.set()
    await asyncio.gather(first_task, second_task)


@pytest.mark.asyncio
async def test_jobs_migration_objects_and_triggers_exist(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, _ = jobs_database
    async with factory() as session:
        tables = set(
            (
                await session.scalars(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' AND tablename LIKE 'job%'"
                    )
                )
            ).all()
        )
        triggers = int(
            await session.scalar(
                text(
                    "SELECT count(*) FROM pg_trigger "
                    "WHERE NOT tgisinternal AND tgname LIKE '%job%'"
                )
            )
            or 0
        )
        functions = int(
            await session.scalar(
                text("SELECT count(*) FROM pg_proc WHERE proname LIKE '%job%'")
            )
            or 0
        )
        assert tables == {"job_number_sequences", "jobs", "job_appointment_links"}
        assert triggers == 6
        assert functions == 6
