from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.workforce.notification_targeting import (
    SUPPORTED_EVENTS,
    EmployeeNotificationTargetingService,
)


def authority(company_id):
    return SimpleNamespace(company=SimpleNamespace(id=company_id))


@pytest.mark.asyncio
async def test_active_mobile_employee_is_exact_ready_target():
    company_id, employee_id, membership_id = uuid4(), uuid4(), uuid4()
    branch_id, user_id = uuid4(), uuid4()
    employee = SimpleNamespace(
        id=employee_id,
        company_id=company_id,
        membership_id=membership_id,
        home_branch_id=branch_id,
        status="active",
        archived_at=None,
    )
    membership = SimpleNamespace(
        id=membership_id,
        user_id=user_id,
        status="active",
        revoked_at=None,
        has_all_branch_access=False,
        default_branch_id=branch_id,
    )
    user = SimpleNamespace(
        id=user_id,
        status="active",
        archived_at=None,
        authorization_version=7,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[employee, membership, user, None, uuid4()])
    )

    result = await EmployeeNotificationTargetingService().resolve(
        session,
        context=authority(company_id),
        employee_id=employee_id,
        event_type="NEW_ASSIGNMENT",
        branch_id=branch_id,
    )

    assert result is not None
    assert result.state == "READY"
    assert result.blockers == ()
    assert result.user_id == user_id
    assert result.authorization_version == 7
    assert result.external_push_state == "PROVIDER_REQUIRED"


@pytest.mark.asyncio
async def test_inactive_authority_returns_transparent_blockers():
    company_id, employee_id, membership_id = uuid4(), uuid4(), uuid4()
    home_branch_id, requested_branch_id, user_id = uuid4(), uuid4(), uuid4()
    employee = SimpleNamespace(
        id=employee_id,
        company_id=company_id,
        membership_id=membership_id,
        home_branch_id=home_branch_id,
        status="terminated",
        archived_at=None,
    )
    membership = SimpleNamespace(
        id=membership_id,
        user_id=user_id,
        status="revoked",
        revoked_at=object(),
        has_all_branch_access=False,
        default_branch_id=home_branch_id,
    )
    user = SimpleNamespace(
        id=user_id,
        status="disabled",
        archived_at=None,
        authorization_version=11,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[employee, membership, user, None, None])
    )

    result = await EmployeeNotificationTargetingService().resolve(
        session,
        context=authority(company_id),
        employee_id=employee_id,
        event_type="TIMEKEEPING_ISSUE",
        branch_id=requested_branch_id,
    )

    assert result is not None
    assert result.state == "BLOCKED"
    assert result.blockers == (
        "EMPLOYEE_INACTIVE",
        "MEMBERSHIP_INACTIVE",
        "USER_INACTIVE",
        "BRANCH_NOT_AUTHORIZED",
        "MOBILE_ROLE_MISSING",
    )


@pytest.mark.asyncio
async def test_cross_company_employee_is_not_resolved():
    session = SimpleNamespace(scalar=AsyncMock(return_value=None))
    result = await EmployeeNotificationTargetingService().resolve(
        session,
        context=authority(uuid4()),
        employee_id=uuid4(),
        event_type="ASSIGNMENT_CHANGED",
        branch_id=uuid4(),
    )
    assert result is None


@pytest.mark.asyncio
async def test_unknown_event_fails_closed_without_querying():
    session = SimpleNamespace(scalar=AsyncMock())
    with pytest.raises(ValueError, match="Unsupported"):
        await EmployeeNotificationTargetingService().resolve(
            session,
            context=authority(uuid4()),
            employee_id=uuid4(),
            event_type="PAYROLL_AVAILABLE",
            branch_id=uuid4(),
        )
    session.scalar.assert_not_awaited()
    assert SUPPORTED_EVENTS == {
        "NEW_ASSIGNMENT",
        "ASSIGNMENT_CHANGED",
        "JOB_CANCELED",
        "EMPLOYEE_ACTION_REQUIRED",
        "TIMEKEEPING_ISSUE",
    }
