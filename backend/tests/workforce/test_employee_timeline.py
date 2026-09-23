from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.permissions.models import MembershipRole, Role
from app.platform.users.models import User
from app.workforce.employee_timeline import EmployeeTimelineService


class Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


@pytest.mark.asyncio
async def test_timeline_composes_native_authority_without_payroll_details():
    company_id, employee_id, membership_id, actor_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    created_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    assigned_at = datetime(2026, 9, 2, tzinfo=timezone.utc)
    clock_at = datetime(2026, 9, 3, tzinfo=timezone.utc)
    employee = SimpleNamespace(
        id=employee_id,
        company_id=company_id,
        membership_id=membership_id,
        created_at=created_at,
        created_by_user_id=actor_id,
    )
    membership = SimpleNamespace(
        id=membership_id,
        status="active",
        created_at=created_at,
    )
    role_assignment = SimpleNamespace(
        assigned_at=assigned_at,
        assigned_by_user_id=actor_id,
        revoked_at=None,
    )
    role = SimpleNamespace(code="ACP_EMPLOYEE_MOBILE", name="ACP Employee Mobile")
    clock = SimpleNamespace(
        kind="start",
        occurred_at=clock_at,
        recorded_by_user_id=actor_id,
        job_id=uuid4(),
    )
    actor = SimpleNamespace(id=actor_id, display_name="Authorized Owner")
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[employee, None, membership, None]),
        execute=AsyncMock(side_effect=[Rows([(role_assignment, role)])]),
        scalars=AsyncMock(
            side_effect=[Rows([]), Rows([]), Rows([]), Rows([clock]), Rows([actor])]
        ),
    )

    result = await EmployeeTimelineService().read(
        session,
        context=SimpleNamespace(company=SimpleNamespace(id=company_id)),
        employee_id=employee_id,
    )

    assert result is not None
    assert [item.event_type for item in result.items] == [
        "JOB_CLOCK_STARTED",
        "MOBILE_ROLE_ASSIGNED",
        "EMPLOYEE_CREATED",
        "MEMBERSHIP_CREATED",
    ]
    assert all(item.authority == "ACP_NATIVE" for item in result.items)
    assert result.items[0].actor_display_name == "Authorized Owner"
    assert "pay" not in " ".join(item.description.lower() for item in result.items)


@pytest.mark.asyncio
async def test_timeline_does_not_resolve_employee_outside_company():
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=None),
        execute=AsyncMock(),
        scalars=AsyncMock(),
    )
    result = await EmployeeTimelineService().read(
        session,
        context=SimpleNamespace(company=SimpleNamespace(id=uuid4())),
        employee_id=uuid4(),
    )
    assert result is None
    session.execute.assert_not_awaited()
    session.scalars.assert_not_awaited()


@pytest_asyncio.fixture
async def timeline_database():
    engine = create_async_engine(settings.database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(connection, expire_on_commit=False)
    try:
        yield factory
    finally:
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_role_model_renders_assigned_and_revoked_history(
    timeline_database,
):
    company_id, user_id, membership_id, employee_id, role_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    assigned_at = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
    revoked_at = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
    async with timeline_database() as session:
        session.add_all(
            [
                Company(
                    id=company_id,
                    name="Timeline Company",
                    code=f"TL{uuid4().hex[:8].upper()}",
                    status="active",
                    timezone="America/New_York",
                ),
                User(
                    id=user_id,
                    normalized_email=f"timeline-{uuid4().hex}@example.test",
                    first_name="Timeline",
                    last_name="Owner",
                    display_name="Timeline Owner",
                    status="active",
                ),
            ]
        )
        await session.flush()
        session.add(
            Membership(
                id=membership_id,
                user_id=user_id,
                company_id=company_id,
                status="active",
            )
        )
        session.add(
            Role(
                id=role_id,
                company_id=company_id,
                code="ACP_EMPLOYEE_MOBILE",
                name="ACP Employee Mobile",
                status="active",
                is_system=True,
            )
        )
        await session.flush()
        session.add(
            Employee(
                id=employee_id,
                company_id=company_id,
                membership_id=membership_id,
                employee_number=f"E{uuid4().hex[:8]}",
                first_name="Field",
                last_name="Employee",
                display_name="Field Employee",
                employee_type="employee",
                status="active",
                created_by_user_id=user_id,
            )
        )
        session.add(
            MembershipRole(
                company_id=company_id,
                membership_id=membership_id,
                role_id=role_id,
                assigned_at=assigned_at,
                assigned_by_user_id=user_id,
                revoked_at=revoked_at,
            )
        )
        await session.flush()

        result = await EmployeeTimelineService().read(
            session,
            context=SimpleNamespace(company=SimpleNamespace(id=company_id)),
            employee_id=employee_id,
        )

    assert result is not None
    role_events = [item for item in result.items if item.source == "membership_role"]
    assert [(item.event_type, item.description) for item in role_events] == [
        ("MOBILE_ROLE_REMOVED", "ACP Employee Mobile role removed."),
        ("MOBILE_ROLE_ASSIGNED", "ACP Employee Mobile role assigned."),
    ]
    assert all(item.authority == "ACP_NATIVE" for item in role_events)
