from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.economics.adapters import (
    AdapterContext,
    AppointmentSourceAdapter,
    InvoiceSourceAdapter,
    JobSourceAdapter,
    MeasuredOperationalCost,
    PaymentSourceAdapter,
    equipment_utilization_adapter,
    labor_time_entry_adapter,
    material_usage_adapter,
    truck_activity_adapter,
)
from app.economics.domain import EconomicCategory


def context() -> AdapterContext:
    return AdapterContext(uuid4(), "1", datetime.now(timezone.utc))


def test_invoice_and_payment_adapters_separate_accrual_and_cash_revenue() -> None:
    now = datetime.now(timezone.utc)
    invoice = SimpleNamespace(
        id=uuid4(),
        company_id=uuid4(),
        branch_id=uuid4(),
        job_id=uuid4(),
        customer_id=uuid4(),
        service_location_id=uuid4(),
        invoice_number="INV-1",
        status="issued",
        currency="USD",
        subtotal_amount=Decimal("100.00"),
        tax_amount=Decimal("8.00"),
        total_amount=Decimal("108.00"),
        issued_at=now,
        created_by_user_id=uuid4(),
        created_at=now,
    )
    payment = SimpleNamespace(
        id=uuid4(),
        company_id=invoice.company_id,
        branch_id=invoice.branch_id,
        invoice_id=invoice.id,
        customer_id=invoice.customer_id,
        amount=Decimal("108.00"),
        currency="USD",
        status="succeeded",
        paid_at=now,
        created_by_user_id=uuid4(),
        created_at=now,
    )

    invoice_fact = InvoiceSourceAdapter().adapt(invoice, context()).commands[0]
    payment_fact = PaymentSourceAdapter().adapt(payment, context()).commands[0]

    assert invoice_fact.amount_minor == 10_800
    assert invoice_fact.accounting_basis == "accrual"
    assert payment_fact.amount_minor == 10_800
    assert payment_fact.accounting_basis == "cash"
    assert all(item.business_event_id for item in invoice_fact.evidence[1:])


@pytest.mark.parametrize(
    ("adapter", "category"),
    [
        (labor_time_entry_adapter, EconomicCategory.LABOR),
        (material_usage_adapter, EconomicCategory.MATERIALS),
        (equipment_utilization_adapter, EconomicCategory.EQUIPMENT),
        (truck_activity_adapter, EconomicCategory.TRUCK),
    ],
)
def test_operational_adapters_accept_only_measured_costs(adapter, category) -> None:
    now = datetime.now(timezone.utc)
    source = MeasuredOperationalCost(
        id=uuid4(),
        company_id=uuid4(),
        branch_id=uuid4(),
        job_id=uuid4(),
        amount_minor=1_250,
        currency="USD",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 1),
        occurred_at=now,
        source_version="1",
        measurement_method="recorded_usage_cost",
    )

    fact = adapter.adapt(source, context()).commands[0]

    assert fact.category is category
    assert fact.amount_minor == 1_250
    assert fact.confidence.percentage == 100


def test_job_and_appointment_adapters_do_not_infer_values() -> None:
    job = SimpleNamespace(id=uuid4(), company_id=uuid4(), branch_id=uuid4())
    appointment = SimpleNamespace(id=uuid4(), company_id=uuid4(), branch_id=uuid4())

    job_result = JobSourceAdapter().adapt(job, context())
    appointment_result = AppointmentSourceAdapter().adapt(appointment, context())

    assert job_result.commands == ()
    assert "no measured monetary" in (job_result.omission_reason or "")
    assert appointment_result.commands == ()
    assert "expected, not measured" in (appointment_result.omission_reason or "")
