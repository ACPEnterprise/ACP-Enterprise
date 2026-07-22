from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.jobs.errors import JobNotFoundError, JobQueryValidationError
from app.jobs.models import JobAppointmentLink
from app.jobs.query import (
    JobDateRange,
    JobDetailQuery,
    JobQueryScope,
    JobSearchQuery,
    JobSortField,
    SortDirection,
)
from app.jobs.query_service import JobsQueryService
from app.jobs.query_types import JobDetail, JobListItem
from app.jobs.repository import JobRepository
from app.jobs.types import JobPriority, JobStatus
from tests.jobs.test_jobs_persistence import (
    JobsFixture,
    build_appointment,
    build_job,
    utc_now,
)

pytest_plugins = ("tests.jobs.test_jobs_persistence",)


def test_public_query_intent_has_no_security_scope() -> None:
    forbidden = {"company_id", "authorized_branch_ids", "scope", "context"}
    assert not forbidden.intersection(field.name for field in fields(JobDetailQuery))
    assert not forbidden.intersection(field.name for field in fields(JobSearchQuery))


@pytest.mark.asyncio
async def test_detail_is_immutable_scoped_and_orders_appointments(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        job = await JobRepository.create_job(session, job=build_job(fixture))
        second = build_appointment(fixture, appointment_number="APT-880002")
        first = build_appointment(fixture, appointment_number="APT-880001")
        session.add_all([second, first])
        await session.flush()
        await JobRepository.create_appointment_link(
            session,
            link=JobAppointmentLink(
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                job_id=job.id,
                appointment_id=second.id,
                visit_sequence=2,
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
            ),
        )
    context = _context_from_fixture(fixture)
    async with factory() as session:
        detail = await JobsQueryService().get_job_detail(
            session, context=context, query=JobDetailQuery(job.id)
        )
    assert isinstance(detail, JobDetail)
    assert [item.visit_sequence for item in detail.appointments] == [1, 2]
    assert detail.customer.id == fixture.customer_id
    assert detail.service_location.id == fixture.location_id
    assert not session.new and not session.dirty and not session.deleted


@pytest.mark.asyncio
async def test_search_filters_counts_appointment_minimum_and_exact_number(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    now = utc_now()
    async with factory() as session, session.begin():
        job = await JobRepository.create_job(
            session, job=build_job(fixture, status=JobStatus.READY, now=now)
        )
        early = build_appointment(fixture, appointment_number="APT-770001")
        late = build_appointment(fixture, appointment_number="APT-770002")
        early.arrival_window_start_at = now - timedelta(days=2)
        early.arrival_window_end_at = early.arrival_window_start_at + timedelta(hours=2)
        late.arrival_window_start_at = now + timedelta(days=2)
        late.arrival_window_end_at = late.arrival_window_start_at + timedelta(hours=2)
        session.add_all([late, early])
        await session.flush()
        for sequence, appointment in enumerate((late, early), start=1):
            await JobRepository.create_appointment_link(
                session,
                link=JobAppointmentLink(
                    company_id=fixture.company_id,
                    branch_id=fixture.branch_id,
                    job_id=job.id,
                    appointment_id=appointment.id,
                    visit_sequence=sequence,
                ),
            )
    async with factory() as session:
        result = await JobsQueryService().search_jobs(
            session,
            context=_context_from_fixture(fixture),
            query=JobSearchQuery(
                job_number="job-000001",
                search_text="APT-770",
                priorities=frozenset({JobPriority.NORMAL}),
                has_appointment=True,
                sort_field=JobSortField.EARLIEST_APPOINTMENT_START_AT,
            ),
        )
    assert result.total_count == result.total_pages == 1
    assert isinstance(result.items[0], JobListItem)
    assert result.items[0].appointment_count == 2
    assert (
        result.items[0].earliest_appointment_start_at == early.arrival_window_start_at
    )


@pytest.mark.asyncio
async def test_concealment_and_query_validation(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    context = _context_from_fixture(fixture)
    async with factory() as session:
        with pytest.raises(JobNotFoundError):
            await JobsQueryService().get_job_detail(
                session, context=context, query=JobDetailQuery(uuid4())
            )
        with pytest.raises(JobNotFoundError):
            await JobsQueryService().search_jobs(
                session,
                context=context,
                query=JobSearchQuery(branch_id=fixture.other_branch_id),
            )
        with pytest.raises(JobQueryValidationError):
            await JobsQueryService().search_jobs(
                session, context=context, query=JobSearchQuery(search_text="  ")
            )
        with pytest.raises(JobQueryValidationError):
            await JobsQueryService().search_jobs(
                session, context=context, query=JobSearchQuery(page_size=201)
            )


def _context_from_fixture(fixture: JobsFixture):
    from app.platform.branch.models import Branch
    from app.platform.company.membership_models import Membership
    from app.platform.company.models import Company
    from app.platform.permissions.authorization import AuthorizationContext
    from app.platform.users.models import User

    now = utc_now()
    return AuthorizationContext(
        user=User(
            id=fixture.user_id,
            normalized_email="query@example.test",
            first_name="Query",
            last_name="User",
            display_name="Query User",
            status="active",
            created_at=now,
            updated_at=now,
        ),
        company=Company(
            id=fixture.company_id,
            name="Query Company",
            code="QUERY",
            status="active",
            timezone="UTC",
            created_at=now,
            updated_at=now,
        ),
        membership=Membership(
            id=uuid4(),
            user_id=fixture.user_id,
            company_id=fixture.company_id,
            status="active",
            has_all_branch_access=False,
            created_at=now,
            updated_at=now,
        ),
        authorized_branches=(
            Branch(
                id=fixture.branch_id,
                company_id=fixture.company_id,
                name="Query Branch",
                code="QUERY",
                status="active",
                timezone="UTC",
                is_primary=True,
                created_at=now,
                updated_at=now,
            ),
        ),
        active_branch=None,
        effective_roles=(),
        effective_permissions=(),
        credential_version=1,
        authorization_version=1,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query_factory",
    [
        lambda f, j: JobSearchQuery(branch_id=f.branch_id),
        lambda f, j: JobSearchQuery(statuses=frozenset({JobStatus.DRAFT})),
        lambda f, j: JobSearchQuery(statuses=frozenset()),
        lambda f, j: JobSearchQuery(priorities=frozenset({JobPriority.NORMAL})),
        lambda f, j: JobSearchQuery(priorities=frozenset()),
        lambda f, j: JobSearchQuery(job_type_codes=frozenset({"service_call"})),
        lambda f, j: JobSearchQuery(job_type_codes=frozenset()),
        lambda f, j: JobSearchQuery(job_number=j.job_number.lower()),
        lambda f, j: JobSearchQuery(customer_id=f.customer_id),
        lambda f, j: JobSearchQuery(service_location_id=f.location_id),
        lambda f, j: JobSearchQuery(has_appointment=False),
        lambda f, j: JobSearchQuery(has_historical_completion=False),
        lambda f, j: JobSearchQuery(has_historical_cancellation=False),
    ],
)
async def test_filter_matrix_matches_expected_job(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    query_factory: Callable[[JobsFixture, Any], JobSearchQuery],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        job = await JobRepository.create_job(session, job=build_job(fixture))
    query = query_factory(fixture, job)
    async with factory() as session:
        result = await JobsQueryService().search_jobs(
            session, context=_context_from_fixture(fixture), query=query
        )
    assert [item.id for item in result.items] == [job.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", list(JobSortField))
@pytest.mark.parametrize("direction", list(SortDirection))
async def test_every_controlled_sort_is_supported(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    field: JobSortField,
    direction: SortDirection,
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        first = await JobRepository.create_job(
            session, job=build_job(fixture, job_number="JOB-000001")
        )
        second = await JobRepository.create_job(
            session, job=build_job(fixture, job_number="JOB-000002")
        )
    async with factory() as session:
        result = await JobsQueryService().search_jobs(
            session,
            context=_context_from_fixture(fixture),
            query=JobSearchQuery(sort_field=field, sort_direction=direction),
        )
    assert {item.id for item in result.items} == {first.id, second.id}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        "created_range",
        "updated_range",
        "activated_range",
        "started_range",
        "completed_range",
        "cancelled_range",
    ],
)
async def test_all_date_ranges_use_half_open_boundaries(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    field: str,
) -> None:
    _, factory, fixture = jobs_database
    at_start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    at_end = datetime(2022, 1, 2, tzinfo=timezone.utc)
    status = JobStatus.DRAFT
    if field == "activated_range":
        status = JobStatus.READY
    elif field == "started_range":
        status = JobStatus.IN_PROGRESS
    elif field == "completed_range":
        status = JobStatus.COMPLETED
    elif field == "cancelled_range":
        status = JobStatus.CANCELLED
    async with factory() as session, session.begin():
        included = build_job(
            fixture, job_number="JOB-000001", status=status, now=at_start
        )
        excluded = build_job(
            fixture, job_number="JOB-000002", status=status, now=at_end
        )
        if field in {"created_range", "updated_range"}:
            included.created_at = included.updated_at = at_start
            excluded.created_at = excluded.updated_at = at_end
        session.add_all([included, excluded])
    ranges: dict[str, JobDateRange | None] = {
        "created_range": None,
        "updated_range": None,
        "activated_range": None,
        "started_range": None,
        "completed_range": None,
        "cancelled_range": None,
    }
    ranges[field] = JobDateRange(at_start, at_end)
    query = JobSearchQuery(
        created_range=ranges["created_range"],
        updated_range=ranges["updated_range"],
        activated_range=ranges["activated_range"],
        started_range=ranges["started_range"],
        completed_range=ranges["completed_range"],
        cancelled_range=ranges["cancelled_range"],
    )
    async with factory() as session:
        result = await JobsQueryService().search_jobs(
            session, context=_context_from_fixture(fixture), query=query
        )
    assert [item.id for item in result.items] == [included.id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "search",
    ["job-000", "jobs a customer", "100 JOBS TEST", "testville", "10001", "hot water"],
)
async def test_operational_search_is_partial_case_insensitive_and_trimmed(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    search: str,
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        job = await JobRepository.create_job(session, job=build_job(fixture))
    async with factory() as session:
        result = await JobsQueryService().search_jobs(
            session,
            context=_context_from_fixture(fixture),
            query=JobSearchQuery(search_text=f"  {search}  "),
        )
    assert [item.id for item in result.items] == [job.id]


@pytest.mark.asyncio
async def test_pagination_metadata_boundaries_and_immutable_results(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        for number in range(1, 6):
            session.add(build_job(fixture, job_number=f"JOB-{number:06d}"))
    service = JobsQueryService()
    async with factory() as session:
        first = await service.search_jobs(
            session,
            context=_context_from_fixture(fixture),
            query=JobSearchQuery(
                page=1,
                page_size=2,
                sort_field=JobSortField.JOB_NUMBER,
                sort_direction=SortDirection.ASC,
            ),
        )
        middle = await service.search_jobs(
            session,
            context=_context_from_fixture(fixture),
            query=JobSearchQuery(
                page=2,
                page_size=2,
                sort_field=JobSortField.JOB_NUMBER,
                sort_direction=SortDirection.ASC,
            ),
        )
        final = await service.search_jobs(
            session,
            context=_context_from_fixture(fixture),
            query=JobSearchQuery(
                page=3,
                page_size=2,
                sort_field=JobSortField.JOB_NUMBER,
                sort_direction=SortDirection.ASC,
            ),
        )
        empty = await service.search_jobs(
            session,
            context=_context_from_fixture(fixture),
            query=JobSearchQuery(page=4, page_size=2),
        )
    assert (first.total_count, first.total_pages) == (5, 3)
    assert len(first.items) == len(middle.items) == 2 and len(final.items) == 1
    assert not {item.id for item in first.items}.intersection(
        item.id for item in middle.items
    )
    assert empty.items == () and empty.total_count == 5 and empty.total_pages == 3
    with pytest.raises(FrozenInstanceError):
        first.page = 9  # type: ignore[misc]


@pytest.mark.parametrize(
    "value",
    [
        JobDetailQuery(uuid4()),
        JobSearchQuery(),
        JobDateRange(utc_now(), utc_now() + timedelta(days=800)),
        JobQueryScope(uuid4(), frozenset()),
    ],
)
def test_query_contracts_are_frozen(value: object) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(value, next(iter(value.__dataclass_fields__)), None)  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        JobSearchQuery(search_text=" " * 4),
        JobSearchQuery(search_text="x" * 201),
        JobSearchQuery(job_type_codes=frozenset({"INVALID-TYPE"})),
        JobSearchQuery(page=0),
        JobSearchQuery(page=-1),
        JobSearchQuery(page_size=0),
        JobSearchQuery(page_size=-1),
        JobSearchQuery(page_size=201),
        JobSearchQuery(
            created_range=JobDateRange(
                datetime(2020, 1, 1), datetime(2020, 1, 2, tzinfo=timezone.utc)
            )
        ),
        JobSearchQuery(
            created_range=JobDateRange(
                datetime(2020, 1, 1, tzinfo=timezone.utc), datetime(2020, 1, 2)
            )
        ),
        JobSearchQuery(
            created_range=JobDateRange(
                datetime(2020, 1, 1, tzinfo=timezone.utc),
                datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
        ),
        JobSearchQuery(
            created_range=JobDateRange(
                datetime(2020, 1, 2, tzinfo=timezone.utc),
                datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
        ),
    ],
)
async def test_invalid_query_inputs_are_controlled(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    query: JobSearchQuery,
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session:
        with pytest.raises(JobQueryValidationError):
            await JobsQueryService().search_jobs(
                session, context=_context_from_fixture(fixture), query=query
            )


@pytest.mark.asyncio
async def test_long_date_range_and_maximum_search_and_page_size_are_valid(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    query = JobSearchQuery(
        created_range=JobDateRange(
            datetime(2018, 1, 1, tzinfo=timezone.utc),
            datetime(2022, 1, 1, tzinfo=timezone.utc),
        ),
        search_text="x" * 200,
        page_size=200,
    )
    async with factory() as session:
        result = await JobsQueryService().search_jobs(
            session, context=_context_from_fixture(fixture), query=query
        )
    assert result.page_size == 200


@pytest.mark.asyncio
async def test_set_filters_relationship_filter_and_boolean_true_filters(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    now = utc_now()
    async with factory() as session, session.begin():
        job = build_job(fixture, status=JobStatus.READY, now=now)
        job.priority = JobPriority.HIGH.value
        job.job_type_code = "repair"
        job.completed_at = now - timedelta(days=2)
        job.completed_by_user_id = fixture.user_id
        job.cancelled_at = now - timedelta(days=1)
        job.cancelled_by_user_id = fixture.user_id
        job.cancellation_reason_code = "customer_cancelled"
        appointment = build_appointment(fixture, appointment_number="APT-990001")
        session.add_all([job, appointment])
        await session.flush()
        session.add(
            JobAppointmentLink(
                company_id=fixture.company_id,
                branch_id=fixture.branch_id,
                job_id=job.id,
                appointment_id=appointment.id,
                visit_sequence=1,
            )
        )
    queries = (
        JobSearchQuery(statuses=frozenset({JobStatus.DRAFT, JobStatus.READY})),
        JobSearchQuery(priorities=frozenset({JobPriority.LOW, JobPriority.HIGH})),
        JobSearchQuery(job_type_codes=frozenset({"service_call", "REPAIR"})),
        JobSearchQuery(appointment_id=appointment.id),
        JobSearchQuery(has_appointment=True),
        JobSearchQuery(has_historical_completion=True),
        JobSearchQuery(has_historical_cancellation=True),
    )
    async with factory() as session:
        for query in queries:
            result = await JobsQueryService().search_jobs(
                session, context=_context_from_fixture(fixture), query=query
            )
            assert [item.id for item in result.items] == [job.id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "expected"),
    [
        (
            JobSortField.PRIORITY,
            [
                JobPriority.LOW,
                JobPriority.NORMAL,
                JobPriority.HIGH,
                JobPriority.URGENT,
                JobPriority.EMERGENCY,
            ],
        ),
        (
            JobSortField.STATUS,
            [
                JobStatus.DRAFT,
                JobStatus.READY,
                JobStatus.IN_PROGRESS,
                JobStatus.PAUSED,
                JobStatus.COMPLETED,
                JobStatus.CANCELLED,
            ],
        ),
    ],
)
async def test_controlled_rank_sorts_use_domain_order(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
    field: JobSortField,
    expected: list[JobPriority] | list[JobStatus],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        for index, value in enumerate(expected, start=1):
            kwargs: dict[str, Any] = {"job_number": f"JOB-{index:06d}"}
            if field is JobSortField.PRIORITY:
                job = build_job(fixture, **kwargs)
                job.priority = value.value
            else:
                kwargs["status"] = value
                kwargs["now"] = utc_now()
                job = build_job(fixture, **kwargs)
            session.add(job)
    async with factory() as session:
        ascending = await JobsQueryService().search_jobs(
            session,
            context=_context_from_fixture(fixture),
            query=JobSearchQuery(sort_field=field, sort_direction=SortDirection.ASC),
        )
        descending = await JobsQueryService().search_jobs(
            session,
            context=_context_from_fixture(fixture),
            query=JobSearchQuery(sort_field=field, sort_direction=SortDirection.DESC),
        )
    observed = [
        item.priority if field is JobSortField.PRIORITY else item.status
        for item in ascending.items
    ]
    reverse_observed = [
        item.priority if field is JobSortField.PRIORITY else item.status
        for item in descending.items
    ]
    assert observed == expected
    assert reverse_observed == list(reversed(expected))
