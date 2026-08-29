from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from app.business_economics.profitability_domain import EconomicCategory
from app.business_economics.profitability_intelligence import (
    AllocationBoundary,
    AllocationPolicyReference,
    ProfitabilityActionKind,
    ProfitabilityAnalysis,
    ProfitabilityBasis,
    ProfitabilityComponent,
    ProfitabilityEvidence,
    ProfitabilityExplanation,
    ProfitabilityFinding,
    ProfitabilityFindingKind,
    ProfitabilityPeriod,
    ProfitabilityQuality,
    ProfitabilityRecommendation,
    ProfitabilityScope,
    ProfitabilityValueState,
)

NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)
DIGEST = "a" * 64


def evidence() -> ProfitabilityEvidence:
    return ProfitabilityEvidence(
        owner="financial",
        source_system="acp_enterprise",
        record_type="invoice",
        record_id="invoice-1",
        source_version="1",
        content_digest=DIGEST,
        effective_at=NOW,
    )


def component(
    category: EconomicCategory,
    amount_minor: int,
    *,
    state: ProfitabilityValueState = ProfitabilityValueState.MEASURED,
) -> ProfitabilityComponent:
    allocations: tuple[AllocationPolicyReference, ...] = ()
    if state is ProfitabilityValueState.ALLOCATED:
        allocations = (
            AllocationPolicyReference(
                policy_id=uuid4(),
                policy_key="fixed-overhead",
                policy_version=1,
                run_id=uuid4(),
                run_version=1,
                boundary=AllocationBoundary.COMPANY,
                driver="revenue",
                input_digest=DIGEST,
                explanation="Approved company overhead allocation.",
            ),
        )
    return ProfitabilityComponent(
        category=category,
        state=state,
        amount_minor=amount_minor,
        currency="USD",
        confidence_percent=100,
        explanation="Evidence-backed component.",
        evidence=(evidence(),),
        allocations=allocations,
    )


def missing(category: EconomicCategory) -> ProfitabilityComponent:
    return ProfitabilityComponent(
        category=category,
        state=ProfitabilityValueState.MISSING,
        amount_minor=None,
        currency="USD",
        confidence_percent=0,
        explanation="Authoritative evidence is missing.",
    )


def analysis(*, missing_overhead: bool = False) -> ProfitabilityAnalysis:
    overhead = (
        missing(EconomicCategory.OVERHEAD)
        if missing_overhead
        else component(
            EconomicCategory.OVERHEAD,
            20_000,
            state=ProfitabilityValueState.ALLOCATED,
        )
    )
    return ProfitabilityAnalysis(
        analysis_id=uuid4(),
        company_id=uuid4(),
        branch_id=uuid4(),
        scope=ProfitabilityScope.TECHNICIAN,
        subject_id=uuid4(),
        period=ProfitabilityPeriod(
            start=date(2026, 7, 27),
            end=date(2026, 8, 2),
            as_of=NOW,
            close_state="open",
            accounting_basis="accrual",
        ),
        basis=ProfitabilityBasis.ACTUAL,
        revenue=component(EconomicCategory.REVENUE, 513_500),
        labor=component(EconomicCategory.LABOR, 150_000),
        materials=component(EconomicCategory.MATERIALS, 292_500),
        equipment=component(EconomicCategory.EQUIPMENT, 0),
        truck=component(EconomicCategory.TRUCK, 30_000),
        overhead=overhead,
        gross_profit=(
            component(EconomicCategory.GROSS_PROFIT, 41_000)
        ),
        net_profit=(
            missing(EconomicCategory.NET_PROFIT)
            if missing_overhead
            else component(EconomicCategory.NET_PROFIT, 21_000)
        ),
        quality=ProfitabilityQuality(
            confidence_percent=0 if missing_overhead else 100,
            completeness_percent=80 if missing_overhead else 100,
            fresh_as_of=NOW,
            freshness_status="current",
            explanation="All required evidence is current.",
            missing_categories=(
                (EconomicCategory.OVERHEAD,) if missing_overhead else ()
            ),
        ),
        measurement_ids=(uuid4(),),
        projection_ids=(uuid4(),),
        lineage_digest=DIGEST,
        engine_version="profitability-contract-v1",
        version=1,
    )


def test_contracts_are_immutable_and_reconcile_known_profit() -> None:
    result = analysis()

    assert result.gross_profit.amount_minor == 41_000
    assert result.net_profit.amount_minor == 21_000
    with pytest.raises(FrozenInstanceError):
        result.version = 2  # type: ignore[misc]


def test_missing_cost_keeps_profit_unknown() -> None:
    result = analysis(missing_overhead=True)

    assert result.overhead.state is ProfitabilityValueState.MISSING
    assert result.gross_profit.amount_minor == 41_000
    assert result.net_profit.amount_minor is None
    with pytest.raises(ValueError, match="net profit remains missing"):
        replace(
            result,
            net_profit=component(EconomicCategory.NET_PROFIT, 21_000),
        )


def test_measured_and_allocated_cost_boundaries_are_explicit() -> None:
    with pytest.raises(ValueError, match="measured component"):
        ProfitabilityComponent(
            category=EconomicCategory.OVERHEAD,
            state=ProfitabilityValueState.MEASURED,
            amount_minor=20_000,
            currency="USD",
            confidence_percent=100,
            explanation="Invalid mixed authority.",
            evidence=(evidence(),),
            allocations=(
                AllocationPolicyReference(
                    policy_id=uuid4(),
                    policy_key="overhead",
                    policy_version=1,
                    run_id=uuid4(),
                    run_version=1,
                    boundary=AllocationBoundary.COMPANY,
                    driver="revenue",
                    input_digest=DIGEST,
                    explanation="Allocation lineage.",
                ),
            ),
        )


def test_explanation_requires_evidence_and_limitations() -> None:
    finding = ProfitabilityFinding(
        kind=ProfitabilityFindingKind.DRIVER,
        summary="Unassigned purchasing materially reduced known margin.",
        component_categories=(EconomicCategory.MATERIALS,),
        evidence_digests=(DIGEST,),
        explanation="Purchase evidence is measured; Job consumption is missing.",
    )
    explanation = ProfitabilityExplanation(
        analysis_id=uuid4(),
        analysis_version=1,
        answer="The exact weekly profit is unknown until overhead is complete.",
        findings=(finding,),
        recommendations=(
            ProfitabilityRecommendation(
                kind=ProfitabilityActionKind.ATTRIBUTE,
                action="Assign supported purchase lines to Jobs.",
                responsible_owner="operations manager",
                expected_evidence="Versioned material-consumption records.",
                rationale="Purchased material is not Job consumption.",
            ),
        ),
        limitations=("Burdened labor and fixed overhead are incomplete.",),
        lineage_digest=DIGEST,
    )

    assert explanation.findings == (finding,)
    with pytest.raises(ValueError, match="requires limitations"):
        ProfitabilityExplanation(
            analysis_id=uuid4(),
            analysis_version=1,
            answer="Unsupported answer.",
            findings=(finding,),
            recommendations=(),
            limitations=(),
            lineage_digest=DIGEST,
        )
