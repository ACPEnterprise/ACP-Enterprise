import hashlib
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.business_economics.profitability_computation import (
    ProfitabilityAllocationInput,
    ProfitabilityComputationError,
    ProfitabilityComputationRequest,
    ProfitabilityComputationService,
    ProfitabilityFactInput,
)
from app.business_economics.profitability_domain import EconomicCategory
from app.business_economics.profitability_intelligence import (
    AllocationBoundary,
    AllocationPolicyReference,
    ProfitabilityBasis,
    ProfitabilityEvidence,
    ProfitabilityPeriod,
    ProfitabilityScope,
    ProfitabilityValueState,
)

NOW = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
COMPANY_ID = UUID("10000000-0000-0000-0000-000000000001")
BRANCH_ID = UUID("20000000-0000-0000-0000-000000000001")
SUBJECT_ID = UUID("30000000-0000-0000-0000-000000000001")
PROJECTION_ID = UUID("40000000-0000-0000-0000-000000000001")


class FactPort:
    def __init__(self, values: list[ProfitabilityFactInput]) -> None:
        self.values = values

    def facts_for(
        self, request: ProfitabilityComputationRequest
    ) -> tuple[ProfitabilityFactInput, ...]:
        return tuple(self.values)


class AllocationPort:
    def __init__(self, values: list[ProfitabilityAllocationInput]) -> None:
        self.values = values

    def allocations_for(
        self, request: ProfitabilityComputationRequest
    ) -> tuple[ProfitabilityAllocationInput, ...]:
        return tuple(self.values)


def request(
    *,
    scope: ProfitabilityScope = ProfitabilityScope.JOB,
    basis: ProfitabilityBasis = ProfitabilityBasis.ACTUAL,
) -> ProfitabilityComputationRequest:
    return ProfitabilityComputationRequest(
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
        scope=scope,
        subject_id=SUBJECT_ID,
        period=ProfitabilityPeriod(
            start=date(2026, 8, 3),
            end=date(2026, 8, 9),
            as_of=NOW,
            close_state="open",
            accounting_basis="accrual",
        ),
        basis=basis,
        currency="USD",
        projection_ids=(PROJECTION_ID,),
        responsible_owner="finance owner",
        maximum_evidence_age=timedelta(days=30),
    )


def evidence(
    category: EconomicCategory, *, effective_at: datetime = NOW
) -> ProfitabilityEvidence:
    return ProfitabilityEvidence(
        owner="operational-owner",
        source_system="acp-enterprise",
        record_type=category.value,
        record_id=f"{category.value}-1",
        source_version="1",
        content_digest=hashlib.sha256(category.value.encode()).hexdigest(),
        effective_at=effective_at,
    )


def fact(
    item_request: ProfitabilityComputationRequest,
    category: EconomicCategory,
    amount: int,
    *,
    state: ProfitabilityValueState | None = None,
    item_evidence: ProfitabilityEvidence | None = None,
) -> ProfitabilityFactInput:
    value_state = state or (
        ProfitabilityValueState.ESTIMATED
        if item_request.basis is ProfitabilityBasis.ESTIMATED
        else ProfitabilityValueState.MEASURED
    )
    return ProfitabilityFactInput(
        fact_id=uuid4(),
        measurement_id=uuid4(),
        company_id=item_request.company_id,
        branch_id=item_request.branch_id,
        scope=item_request.scope,
        subject_id=item_request.subject_id,
        period_start=item_request.period.start,
        period_end=item_request.period.end,
        basis=item_request.basis,
        category=category,
        fact_key=f"{category.value}-fact",
        version=1,
        state=value_state,
        amount_minor=amount,
        currency=item_request.currency,
        confidence_percent=(
            90 if value_state is ProfitabilityValueState.ESTIMATED else 100
        ),
        evidence=(item_evidence or evidence(category),),
    )


def inputs(
    item_request: ProfitabilityComputationRequest,
) -> list[ProfitabilityFactInput]:
    amounts = {
        EconomicCategory.REVENUE: 513_500,
        EconomicCategory.LABOR: 150_000,
        EconomicCategory.MATERIALS: 100_000,
        EconomicCategory.EQUIPMENT: 10_000,
        EconomicCategory.TRUCK: 20_000,
        EconomicCategory.OVERHEAD: 50_000,
    }
    return [
        fact(item_request, category, amount) for category, amount in amounts.items()
    ]


def allocation(
    item_request: ProfitabilityComputationRequest,
) -> ProfitabilityAllocationInput:
    return ProfitabilityAllocationInput(
        allocation_id=uuid4(),
        company_id=item_request.company_id,
        branch_id=item_request.branch_id,
        scope=item_request.scope,
        subject_id=item_request.subject_id,
        period_start=item_request.period.start,
        period_end=item_request.period.end,
        basis=item_request.basis,
        category=EconomicCategory.OVERHEAD,
        amount_minor=5_000,
        currency=item_request.currency,
        confidence_percent=95,
        policy=AllocationPolicyReference(
            policy_id=uuid4(),
            policy_key="company-overhead",
            policy_version=1,
            run_id=uuid4(),
            run_version=1,
            boundary=AllocationBoundary.COMPANY,
            driver="revenue",
            input_digest="f" * 64,
            explanation="Approved overhead policy.",
        ),
        evidence=(evidence(EconomicCategory.OVERHEAD),),
    )


def compute(
    item_request: ProfitabilityComputationRequest,
    facts: list[ProfitabilityFactInput],
    allocations: list[ProfitabilityAllocationInput] | None = None,
):
    return ProfitabilityComputationService(
        FactPort(facts), AllocationPort(allocations or [])
    ).compute(item_request)


def test_computes_reconciled_actual_profit_and_explanation() -> None:
    item_request = request()
    result = compute(item_request, inputs(item_request))

    assert result.analysis.gross_profit.amount_minor == 233_500
    assert result.analysis.net_profit.amount_minor == 183_500
    assert result.analysis.quality.completeness_percent == 100
    assert result.explanation.analysis_id == result.analysis.analysis_id
    assert "183500" in result.explanation.answer


@pytest.mark.parametrize("scope", tuple(ProfitabilityScope))
@pytest.mark.parametrize("basis", tuple(ProfitabilityBasis))
def test_supports_every_scope_and_basis(
    scope: ProfitabilityScope, basis: ProfitabilityBasis
) -> None:
    item_request = request(scope=scope, basis=basis)
    result = compute(item_request, inputs(item_request))

    assert result.analysis.scope is scope
    assert result.analysis.basis is basis
    expected = (
        ProfitabilityValueState.ESTIMATED
        if basis is ProfitabilityBasis.ESTIMATED
        else ProfitabilityValueState.MEASURED
    )
    assert result.analysis.revenue.state is expected


def test_replay_is_identical_despite_input_order() -> None:
    item_request = request()
    values = inputs(item_request)
    allocation_value = allocation(item_request)
    first = compute(item_request, values, [allocation_value])
    second = compute(item_request, list(reversed(values)), [allocation_value])

    assert first == second
    assert first.analysis.analysis_id == second.analysis.analysis_id
    assert first.analysis.lineage_digest == second.analysis.lineage_digest


def test_missing_evidence_fails_closed_with_unknown_profit() -> None:
    item_request = request()
    values = [
        item
        for item in inputs(item_request)
        if item.category is not EconomicCategory.MATERIALS
    ]
    result = compute(item_request, values)

    assert result.analysis.materials.state is ProfitabilityValueState.MISSING
    assert result.analysis.gross_profit.amount_minor is None
    assert result.analysis.net_profit.amount_minor is None
    assert result.analysis.quality.completeness_percent == 83
    assert result.analysis.quality.confidence_percent == 0
    assert "unknown" in result.explanation.answer.lower()


def test_rejects_conflicting_fact_and_evidence_versions() -> None:
    item_request = request()
    values = inputs(item_request)
    original = values[0]
    conflict = replace(original, amount_minor=original.amount_minor + 1)

    with pytest.raises(ProfitabilityComputationError, match="contradictory fact"):
        compute(item_request, [*values, conflict])

    conflicting_evidence = replace(values[1].evidence[0], content_digest="e" * 64)
    conflicting_fact = replace(
        values[1],
        fact_id=uuid4(),
        fact_key="different-fact",
        evidence=(conflicting_evidence,),
    )
    with pytest.raises(ProfitabilityComputationError, match="contradictory digests"):
        compute(item_request, [*values, conflicting_fact])


def test_rejects_stale_future_and_out_of_scope_evidence() -> None:
    item_request = request()
    values = inputs(item_request)
    stale = replace(
        values[0],
        evidence=(
            evidence(
                EconomicCategory.REVENUE,
                effective_at=NOW - timedelta(days=31),
            ),
        ),
    )
    with pytest.raises(ProfitabilityComputationError, match="stale"):
        compute(item_request, [stale, *values[1:]])

    future = replace(
        values[0],
        evidence=(
            evidence(
                EconomicCategory.REVENUE,
                effective_at=NOW + timedelta(seconds=1),
            ),
        ),
    )
    with pytest.raises(ProfitabilityComputationError, match="future"):
        compute(item_request, [future, *values[1:]])

    foreign = replace(values[0], company_id=uuid4())
    with pytest.raises(ProfitabilityComputationError, match="outside"):
        compute(item_request, [foreign, *values[1:]])


def test_actual_basis_rejects_estimated_fact() -> None:
    item_request = request()
    values = inputs(item_request)
    estimated = replace(
        values[0],
        state=ProfitabilityValueState.ESTIMATED,
        confidence_percent=90,
    )

    with pytest.raises(ProfitabilityComputationError, match="actual analysis"):
        compute(item_request, [estimated, *values[1:]])
