from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import app.workforce.simple_onboarding as module
import pytest
from app.platform.employees.models import Employee
from app.platform.permissions.codes import AdministrationPermission
from app.workforce.real_roster import REAL_ALL_COUNTY_ROSTER
from app.workforce.simple_onboarding import (
    ROLE_CODES,
    AccessProfile,
    MatchOutcome,
    SimpleEmployeeOnboardingService,
    SimpleOnboardingConflict,
    normalize_phone,
)


def context(company_id, branch_id):  # type: ignore[no-untyped-def]
    return SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        active_branch=SimpleNamespace(id=branch_id),
        permission_codes=frozenset(
            {AdministrationPermission.IDENTITY_ONBOARDING_MANAGE}
        ),
        has_permission=lambda code: (
            code is AdministrationPermission.IDENTITY_ONBOARDING_MANAGE
        ),
        can_access_branch=lambda value: value == branch_id,
    )


def employee(company_id, branch_id, name="Alex Donahue"):  # type: ignore[no-untyped-def]
    first, last = name.split(" ", 1)
    return Employee(
        id=uuid4(),
        company_id=company_id,
        home_branch_id=branch_id,
        employee_number=f"HCP-{uuid4().hex[:8]}",
        first_name=first,
        last_name=last,
        display_name=name,
        employee_type="employee",
        status="inactive",
    )


@pytest.mark.asyncio
async def test_alex_is_single_and_historical_email_is_not_login_authority(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    company_id, branch_id = uuid4(), uuid4()
    alex = employee(company_id, branch_id)
    source = SimpleNamespace(native_employee_id="pro_10853bfb63874a0b9d17cab14d1da20b")
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=[alex]), scalar=AsyncMock(return_value=source)
    )
    monkeypatch.setattr(module, "employee_is_synthetic", AsyncMock(return_value=False))
    result = await SimpleEmployeeOnboardingService().match(
        session,
        context=context(company_id, branch_id),
        branch_id=branch_id,
        first_name="Alex",
        last_name="Donahue",
        email="alexallcountyplumbingandleak@gmail.com",
        phone=None,
    )
    assert result.outcome is MatchOutcome.SINGLE
    assert result.candidates[0].employee_id == alex.id
    assert result.candidates[0].source_employee_id == source.native_employee_id
    assert (
        next(
            item for item in REAL_ALL_COUNTY_ROSTER if item.key == "alex-donahue"
        ).source_login_email
        == "alexallcountyleaks@gmail.com"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first", "last", "email", "phone"),
    (
        ("Kamen", "Wilmington", "kamencwilmington@gmail.com", "(727) 598-6848"),
        ("Malcolm", "Calci", "malcolmcalci04@gmail.com", "(727) 478-9760"),
    ),
)
async def test_new_hires_have_no_source_match(first, last, email, phone) -> None:  # type: ignore[no-untyped-def]
    company_id, branch_id = uuid4(), uuid4()
    session = SimpleNamespace(scalars=AsyncMock(return_value=[]))
    result = await SimpleEmployeeOnboardingService().match(
        session,
        context=context(company_id, branch_id),
        branch_id=branch_id,
        first_name=first,
        last_name=last,
        email=email,
        phone=phone,
    )
    assert result.outcome is MatchOutcome.NONE


@pytest.mark.asyncio
async def test_synthetic_and_terminated_adam_are_excluded(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    company_id, branch_id = uuid4(), uuid4()
    synthetic = employee(company_id, branch_id)
    session = SimpleNamespace(scalars=AsyncMock(return_value=[synthetic]))
    monkeypatch.setattr(module, "employee_is_synthetic", AsyncMock(return_value=True))
    result = await SimpleEmployeeOnboardingService().match(
        session,
        context=context(company_id, branch_id),
        branch_id=branch_id,
        first_name="Alex",
        last_name="Donahue",
        email="alexallcountyplumbingandleak@gmail.com",
        phone=None,
    )
    assert result.outcome is MatchOutcome.NONE

    adam = employee(company_id, branch_id, "Adam Mari")
    adam.status = "terminated"
    session.scalars = AsyncMock(return_value=[adam])
    result = await SimpleEmployeeOnboardingService().match(
        session,
        context=context(company_id, branch_id),
        branch_id=branch_id,
        first_name="Adam",
        last_name="Mari",
        email="ajjmari3516@gmail.com",
        phone=None,
    )
    assert result.outcome is MatchOutcome.NONE


@pytest.mark.asyncio
async def test_multiple_exact_source_candidates_are_ambiguous(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    company_id, branch_id = uuid4(), uuid4()
    first, second = employee(company_id, branch_id), employee(company_id, branch_id)
    original = next(
        item for item in REAL_ALL_COUNTY_ROSTER if item.key == "alex-donahue"
    )
    duplicate = replace(original, source_employee_id="pro_duplicate_alex")
    monkeypatch.setattr(
        module, "REAL_ALL_COUNTY_ROSTER", (*REAL_ALL_COUNTY_ROSTER, duplicate)
    )
    monkeypatch.setattr(module, "employee_is_synthetic", AsyncMock(return_value=False))
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=[first, second]),
        scalar=AsyncMock(
            side_effect=[
                SimpleNamespace(native_employee_id=original.source_employee_id),
                SimpleNamespace(native_employee_id=duplicate.source_employee_id),
            ]
        ),
    )
    result = await SimpleEmployeeOnboardingService().match(
        session,
        context=context(company_id, branch_id),
        branch_id=branch_id,
        first_name="Alex",
        last_name="Donahue",
        email="alexallcountyplumbingandleak@gmail.com",
        phone=None,
    )
    assert result.outcome is MatchOutcome.AMBIGUOUS


@pytest.mark.asyncio
async def test_stale_revisions_for_one_source_identity_resolve_to_latest_employee(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    company_id, branch_id = uuid4(), uuid4()
    first, stale = employee(company_id, branch_id), employee(company_id, branch_id)
    source_id = "pro_10853bfb63874a0b9d17cab14d1da20b"
    monkeypatch.setattr(module, "employee_is_synthetic", AsyncMock(return_value=False))
    source = SimpleNamespace(native_employee_id=source_id)
    latest = SimpleNamespace(native_employee_id=source_id, employee_id=first.id)
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=[first, stale]),
        scalar=AsyncMock(side_effect=[source, source, latest]),
    )
    result = await SimpleEmployeeOnboardingService().match(
        session,
        context=context(company_id, branch_id),
        branch_id=branch_id,
        first_name="Alex",
        last_name="Donahue",
        email="alexallcountyplumbingandleak@gmail.com",
        phone=None,
    )
    assert result.outcome is MatchOutcome.SINGLE
    assert result.candidates[0].employee_id == first.id


def test_phone_and_access_profiles_are_canonical() -> None:
    assert normalize_phone("(727) 598-6848") == "+17275986848"
    assert normalize_phone("(727) 478-9760") == "+17274789760"
    with pytest.raises(SimpleOnboardingConflict):
        normalize_phone("555")
    assert ROLE_CODES[AccessProfile.FIELD_TECHNICIAN] == {
        "TECHNICIAN",
        "ACP_EMPLOYEE_MOBILE",
    }
    assert ROLE_CODES[AccessProfile.FIELD_MANAGER] == {
        "FIELD_MANAGER",
        "TECHNICIAN",
        "ACP_EMPLOYEE_MOBILE",
        "DISPATCHER",
    }
