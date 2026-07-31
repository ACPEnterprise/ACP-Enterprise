from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.economics.allocation import AllocationTarget, allocation_registry
from app.economics.domain import (
    BusinessFact,
    Confidence,
    EconomicCategory,
    EvidenceKind,
    EvidenceReference,
    MeasurementStatus,
)
from app.economics.measurement import MeasurementEngine


def fact(
    category: EconomicCategory,
    amount_minor: int | None,
    *,
    company_id=None,
    subject_id=None,
    status: MeasurementStatus = MeasurementStatus.MEASURED,
) -> BusinessFact:
    fact_id = uuid4()
    return BusinessFact(
        id=fact_id,
        company_id=company_id or uuid4(),
        branch_id=None,
        subject_type="job",
        subject_id=subject_id or uuid4(),
        category=category,
        amount_minor=amount_minor,
        currency="USD",
        confidence=Confidence(
            status,
            0
            if status is MeasurementStatus.UNKNOWN
            else (80 if status is MeasurementStatus.ESTIMATED else 100),
            "Backed by source records."
            if status is not MeasurementStatus.UNKNOWN
            else "No value available.",
        ),
        evidence=()
        if amount_minor is None
        else (
            EvidenceReference(
                kind=EvidenceKind.SOURCE_RECORD,
                reference_id=str(fact_id),
                source_system="test_ledger",
                source_version="1",
                explanation="Test source record.",
            ),
        ),
        occurred_at=datetime.now(timezone.utc),
    )


def complete_facts(subject_id, company_id) -> tuple[BusinessFact, ...]:
    amounts = {
        EconomicCategory.REVENUE: 100_000,
        EconomicCategory.LABOR: 20_000,
        EconomicCategory.MATERIALS: 15_000,
        EconomicCategory.EQUIPMENT: 5_000,
        EconomicCategory.TRUCK: 2_000,
        EconomicCategory.OVERHEAD: 10_000,
    }
    return tuple(
        fact(category, amount, company_id=company_id, subject_id=subject_id)
        for category, amount in amounts.items()
    )


def test_measurement_engine_computes_profit_from_measured_facts() -> None:
    subject_id, company_id = uuid4(), uuid4()
    result = MeasurementEngine.measure(
        "job", subject_id, complete_facts(subject_id, company_id)
    )

    assert result.revenue.amount_minor == 100_000
    assert result.gross_profit.amount_minor == 58_000
    assert result.net_profit.amount_minor == 48_000
    assert result.confidence.status is MeasurementStatus.MEASURED
    assert result.confidence.percentage == 100
    assert len(result.evidence) == 7
    assert result.gross_profit.category is EconomicCategory.GROSS_PROFIT
    assert result.net_profit.category is EconomicCategory.NET_PROFIT
    assert result.evidence[-1].kind is EvidenceKind.REASONING


def test_unknown_component_propagates_instead_of_becoming_zero() -> None:
    subject_id, company_id = uuid4(), uuid4()
    facts = tuple(
        item
        for item in complete_facts(subject_id, company_id)
        if item.category is not EconomicCategory.TRUCK
    ) + (
        fact(
            EconomicCategory.TRUCK,
            None,
            company_id=company_id,
            subject_id=subject_id,
            status=MeasurementStatus.UNKNOWN,
        ),
    )

    result = MeasurementEngine.measure("job", subject_id, facts)

    assert result.truck.amount_minor is None
    assert result.gross_profit.amount_minor is None
    assert result.net_profit.amount_minor is None
    assert result.confidence.status is MeasurementStatus.UNKNOWN


def test_domain_models_are_immutable() -> None:
    measured = Confidence(MeasurementStatus.MEASURED, 100, "Direct measurement.")
    with pytest.raises(FrozenInstanceError):
        measured.percentage = 50  # type: ignore[misc]


def test_allocation_strategies_preserve_every_minor_unit() -> None:
    source = fact(EconomicCategory.OVERHEAD, 100)
    targets = (
        AllocationTarget("job", uuid4(), 1),
        AllocationTarget("job", uuid4(), 1),
        AllocationTarget("job", uuid4(), 1),
    )

    for strategy in (
        "labor_hours",
        "revenue",
        "truck_days",
        "job_duration",
        "branch",
        "company",
    ):
        allocations = allocation_registry.allocate(strategy, source, targets)
        assert sum(item.allocated_amount_minor for item in allocations) == 100
        assert {item.strategy for item in allocations} == {strategy}
        assert {item.strategy_version for item in allocations} == {"1"}


def test_engine_rejects_mixed_currency_and_subjects() -> None:
    subject_id, company_id = uuid4(), uuid4()
    facts = list(complete_facts(subject_id, company_id))
    other = facts[-1]
    facts[-1] = BusinessFact(
        id=other.id,
        company_id=other.company_id,
        branch_id=other.branch_id,
        subject_type=other.subject_type,
        subject_id=other.subject_id,
        category=other.category,
        amount_minor=other.amount_minor,
        currency="EUR",
        confidence=other.confidence,
        evidence=other.evidence,
        occurred_at=other.occurred_at,
    )
    with pytest.raises(ValueError, match="mix currencies"):
        MeasurementEngine.measure("job", subject_id, tuple(facts))
