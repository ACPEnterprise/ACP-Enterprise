from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Literal, cast
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from app.database.session import get_database_session
from app.employee_operations.errors import EmployeeIdentityNotReady
from app.employee_operations.permissions import EmployeeOperationsPermission
from app.employee_operations.repository import EmployeeDayRecord, EmployeeDayRepository
from app.employee_operations.service import EmployeeDayService, employee_day_service
from app.main import app
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.dependencies import get_authorization_context

COMPANY_ID = UUID("10000000-0000-0000-0000-000000000001")
MEMBERSHIP_ID = UUID("20000000-0000-0000-0000-000000000001")
EMPLOYEE_ID = UUID("30000000-0000-0000-0000-000000000001")
BRANCH_ID = UUID("40000000-0000-0000-0000-000000000001")
OTHER_BRANCH_ID = UUID("40000000-0000-0000-0000-000000000002")


class FakeContext:
    def __init__(
        self,
        *,
        branches: frozenset[UUID] = frozenset({BRANCH_ID}),
        permitted: bool = True,
    ):
        self.company = SimpleNamespace(id=COMPANY_ID, timezone="America/New_York")
        self.user = SimpleNamespace(id=uuid4())
        self.membership = SimpleNamespace(id=MEMBERSHIP_ID)
        self.active_branch = SimpleNamespace(id=BRANCH_ID, timezone="America/New_York")
        self.authorized_branch_ids = branches
        self.permitted = permitted

    def has_permission(self, code: str) -> bool:
        return self.permitted and code == EmployeeOperationsPermission.OWN_DAY_READ


def record(
    *,
    appointment_id: UUID | None = None,
    start: datetime | None = None,
    role: str = "primary",
    appointment_status: str = "scheduled",
    assignment_status: str = "assigned",
) -> EmployeeDayRecord:
    begin = start or datetime(2026, 8, 28, 13, 0, tzinfo=timezone.utc)
    return EmployeeDayRecord(
        appointment_id=appointment_id or uuid4(),
        appointment_number="APT-900001",
        appointment_status=appointment_status,
        job_id=uuid4(),
        job_number="JOB-900001",
        job_status="active",
        service_category="repair",
        window_start_at=begin,
        window_end_at=begin.replace(hour=begin.hour + 1),
        assignment_role=cast(Literal["primary", "crew"], role),
        assignment_status=assignment_status,
        customer_display_name="Synthetic Customer",
        location_nickname="Synthetic Service Site",
        address_line_1="100 Test Avenue",
        address_line_2=None,
        city="Testville",
        state="NY",
        postal_code="10000",
        country="US",
    )


class FakeRepository:
    def __init__(self, records: tuple[EmployeeDayRecord, ...] = ()):
        self.records = records
        self.employee: object | None = SimpleNamespace(id=EMPLOYEE_ID)
        self.calls: list[dict[str, object]] = []

    async def employee_for_membership(self, _session, **kwargs):
        self.calls.append(kwargs)
        return self.employee

    async def assignments_for_day(self, _session, **kwargs):
        self.calls.append(kwargs)
        return self.records


async def project(
    repository: FakeRepository,
    *,
    business_date: date | None = date(2026, 8, 28),
    context: FakeContext | None = None,
):
    service = EmployeeDayService(repository=repository)  # type: ignore[arg-type]
    return await service.day(
        None,  # type: ignore[arg-type]
        context=context or FakeContext(),  # type: ignore[arg-type]
        business_date=business_date,
        observed_at=datetime(2026, 8, 29, 3, 30, tzinfo=timezone.utc),
    )


def test_permission_is_narrow_and_catalogued() -> None:
    permission_catalog.validate()
    definition = next(
        item
        for item in permission_catalog.definitions
        if item.code == EmployeeOperationsPermission.OWN_DAY_READ
    )
    assert definition.resource == "employee_operations"
    assert definition.action == "own_day_read"


def test_openapi_contract_is_self_scoped_and_employee_safe() -> None:
    operation = app.openapi()["paths"]["/api/v1/employee-operations/me/day"]["get"]
    parameters = {item["name"] for item in operation["parameters"]}
    assert "business_date" in parameters
    assert "employee_id" not in parameters
    document = str(operation).lower()
    for forbidden in (
        "invoice",
        "estimate",
        "payment",
        "balance",
        "margin",
        "cost",
        "payroll",
        "compensation",
        "phone",
        "email",
        "internal_description",
        "note",
    ):
        assert forbidden not in document


@pytest.mark.asyncio
async def test_endpoint_requires_authentication() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/employee-operations/me/day")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_http_semantics_distinguish_empty_forbidden_identity_and_bad_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeRepository()
    monkeypatch.setattr(employee_day_service, "repository", repository)

    async def database_override():
        yield None

    async def permitted_context():
        return FakeContext()

    app.dependency_overrides[get_database_session] = database_override
    app.dependency_overrides[get_authorization_context] = permitted_context
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            empty = await client.get(
                "/api/v1/employee-operations/me/day",
                params={"business_date": "2026-08-28"},
            )
            invalid = await client.get(
                "/api/v1/employee-operations/me/day",
                params={"business_date": "2026-08-28T12:00:00Z"},
            )
            repository.employee = None
            not_ready = await client.get("/api/v1/employee-operations/me/day")
        assert empty.status_code == 200
        assert empty.json()["assignments"] == []
        assert invalid.status_code == 422
        assert not_ready.status_code == 422
        assert "not ready" in not_ready.json()["detail"].lower()

        async def forbidden_context():
            return FakeContext(permitted=False)

        app.dependency_overrides[get_authorization_context] = forbidden_context
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            forbidden = await client.get("/api/v1/employee-operations/me/day")
        assert forbidden.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_employee_sees_primary_and_active_crew_assignments() -> None:
    repository = FakeRepository((record(role="primary"), record(role="crew")))
    result = await project(repository)
    assert [item.assignment_role for item in result.assignments] == ["primary", "crew"]
    query_call = repository.calls[1]
    assert query_call["company_id"] == COMPANY_ID
    assert query_call["employee_id"] == EMPLOYEE_ID
    assert query_call["authorized_branch_ids"] == frozenset({BRANCH_ID})


@pytest.mark.asyncio
async def test_empty_day_is_success_not_error() -> None:
    result = await project(FakeRepository())
    assert result.business_date == date(2026, 8, 28)
    assert result.assignments == ()


@pytest.mark.asyncio
async def test_identity_not_ready_is_distinct_from_empty() -> None:
    repository = FakeRepository()
    repository.employee = None
    with pytest.raises(EmployeeIdentityNotReady):
        await project(repository)


@pytest.mark.asyncio
async def test_default_business_day_uses_authoritative_timezone() -> None:
    result = await project(FakeRepository(), business_date=None)
    assert result.business_date == date(2026, 8, 28)
    assert result.timezone == "America/New_York"
    query_call = result  # Response proves no client timezone input is needed.
    assert query_call.timezone == "America/New_York"


@pytest.mark.asyncio
async def test_dst_business_day_bounds_are_authoritative() -> None:
    repository = FakeRepository()
    await project(repository, business_date=date(2026, 11, 1))
    query_call = repository.calls[1]
    duration = cast(datetime, query_call["end_at"]) - cast(
        datetime, query_call["start_at"]
    )
    assert duration.total_seconds() == 25 * 60 * 60


@pytest.mark.asyncio
async def test_branch_scope_is_passed_unchanged() -> None:
    branches = frozenset({BRANCH_ID, OTHER_BRANCH_ID})
    repository = FakeRepository()
    await project(repository, context=FakeContext(branches=branches))
    assert repository.calls[1]["authorized_branch_ids"] == branches


@pytest.mark.asyncio
async def test_reassignment_and_crew_removal_disappear_on_next_read() -> None:
    repository = FakeRepository((record(),))
    assert len((await project(repository)).assignments) == 1
    repository.records = ()
    assert (await project(repository)).assignments == ()


@pytest.mark.asyncio
async def test_cancellation_is_explicit_when_active_assignment_remains() -> None:
    result = await project(FakeRepository((record(appointment_status="cancelled"),)))
    assert result.assignments[0].appointment_status == "cancelled"


@pytest.mark.asyncio
async def test_rescheduling_moves_assignment_between_dates() -> None:
    repository = FakeRepository((record(),))
    assert len((await project(repository)).assignments) == 1
    repository.records = ()
    assert (
        await project(repository, business_date=date(2026, 8, 28))
    ).assignments == ()
    repository.records = (
        record(start=datetime(2026, 8, 29, 13, 0, tzinfo=timezone.utc)),
    )
    result = await project(repository, business_date=date(2026, 8, 29))
    assert len(result.assignments) == 1


@pytest.mark.asyncio
async def test_repository_order_is_preserved_and_designation_not_fabricated() -> None:
    first_id = UUID("50000000-0000-0000-0000-000000000001")
    second_id = UUID("50000000-0000-0000-0000-000000000002")
    repository = FakeRepository(
        (
            record(appointment_id=first_id),
            record(appointment_id=second_id),
        )
    )
    result = await project(repository)
    assert [item.appointment_id for item in result.assignments] == [first_id, second_id]
    assert all(item.designation is None for item in result.assignments)


@pytest.mark.asyncio
async def test_projection_contains_only_bounded_operational_fields() -> None:
    result = await project(FakeRepository((record(),)))
    payload = result.model_dump(mode="json")
    text = str(payload).lower()
    assert payload["assignments"][0]["customer_display_name"] == "Synthetic Customer"
    for forbidden in (
        "financial",
        "payroll",
        "compensation",
        "phone",
        "email",
        "internal",
        "notes",
        "rate",
        "wage",
    ):
        assert forbidden not in text


def test_query_constrains_tenant_employee_branch_and_active_crew_in_sql() -> None:
    statement = EmployeeDayRepository.day_statement(
        company_id=COMPANY_ID,
        employee_id=EMPLOYEE_ID,
        authorized_branch_ids=frozenset({BRANCH_ID}),
        start_at=datetime(2026, 8, 28, 4, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 8, 29, 4, 0, tzinfo=timezone.utc),
    )
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()
    assert "dispatch_assignments.company_id" in sql
    assert "dispatch_assignments.branch_id in" in sql
    assert "dispatch_assignments.primary_employee_id" in sql
    assert "dispatch_crew_members.employee_id" in sql
    assert "dispatch_crew_members.status = 'active'" in sql
    assert "appointments.arrival_window_start_at" in sql
    assert "order by appointments.arrival_window_start_at, appointments.id" in sql
    assert "customers.company_id = appointments.company_id" in sql
    assert "jobs.company_id = dispatch_assignments.company_id" in sql
    assert "customer_contacts" not in sql
    assert "customer_notes" not in sql


def test_query_excludes_inactive_assignment_and_removed_crew_states() -> None:
    statement = EmployeeDayRepository.day_statement(
        company_id=COMPANY_ID,
        employee_id=EMPLOYEE_ID,
        authorized_branch_ids=frozenset({BRANCH_ID}),
        start_at=datetime(2026, 8, 28, 4, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 8, 29, 4, 0, tzinfo=timezone.utc),
    )
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()
    for active in ("assigned", "acknowledged", "reconciliation_required"):
        assert active in sql
    for inactive in ("released", "replaced", "cancelled"):
        assert inactive not in sql


def test_query_is_one_joined_projection_not_per_assignment_loading() -> None:
    statement = EmployeeDayRepository.day_statement(
        company_id=COMPANY_ID,
        employee_id=EMPLOYEE_ID,
        authorized_branch_ids=frozenset({BRANCH_ID}),
        start_at=datetime(2026, 8, 28, 4, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 8, 29, 4, 0, tzinfo=timezone.utc),
    )
    sql = str(statement.compile(dialect=postgresql.dialect())).lower()
    assert sql.count("select ") == 2  # Main projection plus correlated crew EXISTS.
    assert all(
        name in sql
        for name in ("appointments", "customers", "service_locations", "jobs")
    )
