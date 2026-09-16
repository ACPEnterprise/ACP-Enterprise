from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.business_economics.native_evidence import NativeEconomicsEvidenceService


def _result(rows: list[object]) -> MagicMock:
    value = MagicMock()
    value.all.return_value = rows
    return value


@pytest.mark.asyncio
async def test_native_facts_are_admitted_without_inventing_profitability() -> None:
    company_id, branch_id, customer_id, job_id = (uuid4() for _ in range(4))
    now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    invoice = SimpleNamespace(
        id=uuid4(),
        company_id=company_id,
        branch_id=branch_id,
        customer_id=customer_id,
        job_id=job_id,
        status="issued",
        accounting_status="pending",
        currency="USD",
        issue_date=date(2026, 9, 15),
        total_amount=Decimal("125.50"),
        version=2,
        issued_at=now,
        updated_at=now,
    )
    interval = SimpleNamespace(
        id=uuid4(),
        interval_id=uuid4(),
        revision_number=1,
        company_id=company_id,
        branch_id=branch_id,
        employee_id=uuid4(),
        job_id=job_id,
        duration_seconds=3600,
        validity="valid",
        confidence="authoritative",
        created_at=now,
    )
    reservation = SimpleNamespace(demand_id=job_id)
    issue = SimpleNamespace(
        id=uuid4(),
        item_id=uuid4(),
        issue_type="issue",
        quantity=Decimal(2),
        stocking_unit="each",
        posted_at=now,
    )
    movement = SimpleNamespace(
        unit_cost=Decimal("10.00"), currency="USD", valuation_method="fifo"
    )
    settlement = SimpleNamespace(
        id=uuid4(),
        entry_type="payment_application",
        amount=Decimal("-25.00"),
        currency="USD",
        source_version=1,
        occurred_at=now,
    )
    receipt = SimpleNamespace(receipt_id=uuid4(), evidence_digest="c" * 64)
    job = SimpleNamespace(
        id=job_id,
        company_id=company_id,
        branch_id=branch_id,
        customer_id=customer_id,
        job_number="JOB-000001",
        status="completed",
        job_type_code="drain",
        concurrency_version=3,
        updated_at=now,
    )
    customer = SimpleNamespace(id=customer_id, display_name="Accepted Customer")
    branch = SimpleNamespace(id=branch_id, name="Main")
    session = SimpleNamespace(
        scalars=AsyncMock(side_effect=[_result([invoice]), _result([interval])]),
        execute=AsyncMock(
            side_effect=[
                _result([(issue, reservation, movement)]),
                _result([(settlement, invoice, receipt)]),
                _result([(job, customer, branch)]),
            ]
        ),
    )
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        active_branch=SimpleNamespace(id=branch_id),
        authorized_branch_ids=frozenset({branch_id}),
    )

    result = await NativeEconomicsEvidenceService().project(
        session,
        context=context,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )

    assert result["admitted_reference_count"] == 6
    assert result["families"]["REVENUE"]["state"] == "AVAILABLE"
    assert result["families"]["DIRECT_LABOR"]["state"] == "AVAILABLE"
    assert result["families"]["DIRECT_MATERIAL"]["state"] == "AVAILABLE"
    assert result["families"]["SERVICE_CATEGORY"]["state"] == "AVAILABLE"
    assert result["families"]["WORKFORCE_ATTRIBUTION"]["state"] == "AVAILABLE"
    assert result["families"]["SETTLEMENT"]["state"] == "AVAILABLE"
    assert result["families"]["ACCOUNTING"]["state"] == "PARTIAL"
    projected = result["jobs"][0]
    assert projected["invoiced_revenue_minor"] == 12_550
    assert projected["accepted_worked_seconds"] == 3600
    assert projected["material_cost_minor"] == 2_000
    assert projected["settlement_applied_minor"] == -2_500
    assert "contribution_minor" not in projected


@pytest.mark.asyncio
async def test_missing_material_cost_remains_partial_and_missing() -> None:
    company_id, branch_id, customer_id, job_id = (uuid4() for _ in range(4))
    now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    issue = SimpleNamespace(
        id=uuid4(),
        item_id=uuid4(),
        issue_type="issue",
        quantity=Decimal(1),
        stocking_unit="each",
        posted_at=now,
    )
    reservation = SimpleNamespace(demand_id=job_id)
    movement = SimpleNamespace(unit_cost=None, currency=None, valuation_method=None)
    job = SimpleNamespace(
        id=job_id,
        company_id=company_id,
        branch_id=branch_id,
        customer_id=customer_id,
        job_number="JOB-000002",
        status="completed",
        job_type_code=None,
        concurrency_version=1,
        updated_at=now,
    )
    session = SimpleNamespace(
        scalars=AsyncMock(side_effect=[_result([]), _result([])]),
        execute=AsyncMock(
            side_effect=[
                _result([(issue, reservation, movement)]),
                _result([]),
                _result(
                    [
                        (
                            job,
                            SimpleNamespace(id=customer_id, display_name="Customer"),
                            SimpleNamespace(id=branch_id, name="Main"),
                        )
                    ]
                ),
            ]
        ),
    )
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        active_branch=SimpleNamespace(id=branch_id),
        authorized_branch_ids=frozenset({branch_id}),
    )

    result = await NativeEconomicsEvidenceService().project(
        session,
        context=context,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )

    assert result["families"]["DIRECT_MATERIAL"]["state"] == "PARTIAL"
    assert result["jobs"][0]["material_cost_minor"] is None
