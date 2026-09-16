from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.workforce.employee_timeline import EmployeeTimelineService


class Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


@pytest.mark.asyncio
async def test_timeline_composes_native_authority_without_payroll_details():
    company_id, employee_id, membership_id, actor_id = (
        uuid4(), uuid4(), uuid4(), uuid4()
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
    role = SimpleNamespace(code="ACP_EMPLOYEE_MOBILE", display_name="ACP Employee Mobile")
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
            side_effect=[Rows([]), Rows([]), Rows([clock]), Rows([actor])]
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
