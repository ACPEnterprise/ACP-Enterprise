from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.business_economics.direct_wage_cost_readiness import (
    DirectWageCostReadinessService,
)


def _result(rows: list[object]) -> MagicMock:
    value = MagicMock()
    value.all.return_value = rows
    return value


def _context(company_id: object, branch_id: object) -> SimpleNamespace:
    return SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        active_branch=SimpleNamespace(id=branch_id),
        authorized_branch_ids=frozenset({branch_id}),
    )


def _interval(*, company_id: object, branch_id: object, employee_id: object) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        interval_id=uuid4(),
        employee_id=employee_id,
        job_id=uuid4(),
        company_id=company_id,
        branch_id=branch_id,
        start_at=datetime(2026, 9, 8, 14, tzinfo=timezone.utc),
        duration_seconds=3600,
    )


@pytest.mark.asyncio
async def test_hourly_interval_blocks_without_complete_overtime_allocation() -> None:
    company_id, branch_id, employee_id = uuid4(), uuid4(), uuid4()
    interval = _interval(
        company_id=company_id, branch_id=branch_id, employee_id=employee_id
    )
    authority = SimpleNamespace(
        id=uuid4(),
        employee_id=employee_id,
        effective_start=date(2026, 1, 1),
        effective_end=None,
        compensation_type="hourly",
        authority_version=2,
        authority_digest="a" * 64,
    )
    session = SimpleNamespace(
        scalars=AsyncMock(side_effect=[_result([interval]), _result([authority])])
    )

    result = await DirectWageCostReadinessService().project(
        session,
        context=_context(company_id, branch_id),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )

    projected = result["employee_job_periods"][0]
    assert projected["readiness"] == "OVERTIME_POLICY_REQUIRED"
    assert projected["direct_wage_cost_minor"] is None
    assert result["readiness_counts"]["DIRECT_WAGE_COST_READY"] == 0


@pytest.mark.asyncio
async def test_salary_and_missing_compensation_remain_explicit() -> None:
    company_id, branch_id = uuid4(), uuid4()
    salary_employee, missing_employee = uuid4(), uuid4()
    intervals = [
        _interval(
            company_id=company_id,
            branch_id=branch_id,
            employee_id=salary_employee,
        ),
        _interval(
            company_id=company_id,
            branch_id=branch_id,
            employee_id=missing_employee,
        ),
    ]
    authority = SimpleNamespace(
        id=uuid4(),
        employee_id=salary_employee,
        effective_start=date(2026, 1, 1),
        effective_end=None,
        compensation_type="salaried",
        authority_version=1,
        authority_digest="b" * 64,
    )
    session = SimpleNamespace(
        scalars=AsyncMock(side_effect=[_result(intervals), _result([authority])])
    )

    result = await DirectWageCostReadinessService().project(
        session,
        context=_context(company_id, branch_id),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )

    by_employee = {
        row["employee_id"]: row for row in result["employee_job_periods"]
    }
    assert (
        by_employee[str(salary_employee)]["readiness"]
        == "OWNER_CERTIFICATION_REQUIRED"
    )
    assert (
        by_employee[str(missing_employee)]["readiness"] == "COMPENSATION_MISSING"
    )
    assert all(
        row["direct_wage_cost_minor"] is None
        for row in result["employee_job_periods"]
    )


@pytest.mark.asyncio
async def test_no_accepted_job_time_is_unknown_not_zero_cost() -> None:
    company_id, branch_id = uuid4(), uuid4()
    session = SimpleNamespace(scalars=AsyncMock(side_effect=[_result([])]))

    result = await DirectWageCostReadinessService().project(
        session,
        context=_context(company_id, branch_id),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )

    assert result["accepted_job_interval_count"] == 0
    assert result["employee_job_periods"] == []
    assert "direct_wage_cost_minor" not in result
