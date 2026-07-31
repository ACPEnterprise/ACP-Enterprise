from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.economics.adapters import (
    AdapterContext,
    AppointmentSourceAdapter,
    BusinessEventSourceAdapter,
    InvoiceSourceAdapter,
    JobSourceAdapter,
    MeasuredOperationalCost,
    PaymentSourceAdapter,
    equipment_utilization_adapter,
    labor_time_entry_adapter,
    material_usage_adapter,
    truck_activity_adapter,
)
from app.economics.domain import EconomicCategory, MeasurementStatus
from app.economics.ingestion import EconomicsIngestionService
from app.economics.ledger import EconomicsLedgerError, EconomicsLedgerService


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


def test_business_event_adapter_accepts_only_explicit_measured_values() -> None:
    now = datetime.now(timezone.utc)
    company_id = uuid4()
    event = SimpleNamespace(
        id=uuid4(),
        company_id=company_id,
        branch_id=uuid4(),
        entity_type="job",
        entity_id=uuid4(),
        event_type="economics.material_recorded",
        occurred_at=now,
        payload={
            "economics": {
                "category": "materials",
                "fact_key": "material_usage_cost",
                "amount_minor": 2300,
                "currency": "USD",
                "period_start": "2026-07-31",
                "period_end": "2026-07-31",
                "measurement_status": "measured",
            }
        },
    )
    command = BusinessEventSourceAdapter().adapt(event, context()).commands[0]
    assert command.amount_minor == 2300
    assert command.confidence.status is MeasurementStatus.MEASURED
    assert command.evidence[0].business_event_id == event.id

    event.payload["economics"]["measurement_status"] = "estimated"
    result = BusinessEventSourceAdapter().adapt(event, context())
    assert result.commands == ()
    assert "not measured" in (result.omission_reason or "")


@pytest.mark.asyncio
async def test_ingestion_routes_through_ledger_and_enforces_company_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = uuid4()
    source = MeasuredOperationalCost(
        id=uuid4(),
        company_id=company_id,
        branch_id=uuid4(),
        job_id=uuid4(),
        amount_minor=500,
        currency="USD",
        period_start=date(2026, 7, 31),
        period_end=date(2026, 7, 31),
        occurred_at=datetime.now(timezone.utc),
        source_version="1",
        measurement_method="recorded_usage_cost",
    )
    recorded: list[object] = []

    async def record_fact(session, scoped_company_id, command):
        del session
        assert scoped_company_id == company_id
        recorded.append(command)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(EconomicsLedgerService, "record_fact", record_fact)
    facts = await EconomicsIngestionService.ingest(
        object(),  # type: ignore[arg-type]
        company_id=company_id,
        adapter=material_usage_adapter,
        source=source,
        context=context(),
    )
    assert len(facts) == len(recorded) == 1

    with pytest.raises(EconomicsLedgerError, match="Company"):
        await EconomicsIngestionService.ingest(
            object(),  # type: ignore[arg-type]
            company_id=uuid4(),
            adapter=material_usage_adapter,
            source=source,
            context=context(),
        )
