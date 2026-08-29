import hashlib
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.business_economics.profitability_computation import (
    ProfitabilityComputationRequest,
    ProfitabilityFactInput,
)
from app.business_economics.profitability_domain import EconomicCategory
from app.business_economics.profitability_engine import (
    AcquiredProfitabilityFact,
    ProfitabilityEngineError,
    ReconciledProfitabilityEngine,
)
from app.business_economics.profitability_intelligence import (
    ProfitabilityBasis,
    ProfitabilityEvidence,
    ProfitabilityPeriod,
    ProfitabilityScope,
    ProfitabilityValueState,
)

NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)
COMPANY = UUID("10000000-0000-0000-0000-000000000001")
BRANCH = UUID("20000000-0000-0000-0000-000000000001")
SUBJECT = UUID("30000000-0000-0000-0000-000000000001")


def request(basis: ProfitabilityBasis = ProfitabilityBasis.ACTUAL):
    return ProfitabilityComputationRequest(
        company_id=COMPANY,
        branch_id=BRANCH,
        scope=ProfitabilityScope.JOB,
        subject_id=SUBJECT,
        period=ProfitabilityPeriod(
            date(2026, 8, 1), date(2026, 8, 31), NOW, "open", "accrual"
        ),
        basis=basis,
        currency="USD",
        projection_ids=(uuid4(),),
        responsible_owner="finance",
        maximum_evidence_age=timedelta(days=30),
    )


def facts(item_request: ProfitabilityComputationRequest):
    values = {
        EconomicCategory.REVENUE: 100_000,
        EconomicCategory.LABOR: 20_000,
        EconomicCategory.MATERIALS: 10_000,
        EconomicCategory.EQUIPMENT: 5_000,
        EconomicCategory.TRUCK: 5_000,
        EconomicCategory.OVERHEAD: 10_000,
    }
    state = (
        ProfitabilityValueState.MEASURED
        if item_request.basis is ProfitabilityBasis.ACTUAL
        else ProfitabilityValueState.ESTIMATED
    )
    confidence = 100 if state is ProfitabilityValueState.MEASURED else 90
    return tuple(
        AcquiredProfitabilityFact(
            fact=ProfitabilityFactInput(
                fact_id=uuid4(),
                measurement_id=uuid4(),
                company_id=COMPANY,
                branch_id=BRANCH,
                scope=item_request.scope,
                subject_id=SUBJECT,
                period_start=item_request.period.start,
                period_end=item_request.period.end,
                basis=item_request.basis,
                category=category,
                fact_key=category.value,
                version=1,
                state=state,
                amount_minor=amount,
                currency="USD",
                confidence_percent=confidence,
                evidence=(
                    ProfitabilityEvidence(
                        owner="source",
                        source_system="acp",
                        record_type=category.value,
                        record_id=category.value,
                        source_version="1",
                        content_digest=hashlib.sha256(
                            category.value.encode()
                        ).hexdigest(),
                        effective_at=NOW,
                    ),
                ),
            ),
            acquisition_digest=hashlib.sha256(
                f"acq:{category.value}".encode()
            ).hexdigest(),
            completeness_percent=100,
            explanation_id=uuid4(),
        )
        for category, amount in values.items()
    )


def test_computes_metrics_and_replays_identically() -> None:
    item_request = request()
    values = facts(item_request)
    engine = ReconciledProfitabilityEngine()
    first = engine.compute(item_request, values, ())
    replay = engine.compute(item_request, tuple(reversed(values)), ())

    assert first == replay
    assert first.metrics.contribution_margin_minor == 60_000
    assert first.metrics.gross_margin_basis_points == 6_000
    assert first.metrics.net_margin_basis_points == 5_000
    assert first.metrics.allocated_cost_minor == 0
    assert first.metrics.fully_burdened_cost_minor == 50_000


def test_compares_actual_estimated_and_rejects_cross_scope() -> None:
    engine = ReconciledProfitabilityEngine()
    actual_request = request()
    estimated_request = request(ProfitabilityBasis.ESTIMATED)
    actual = engine.compute(actual_request, facts(actual_request), ())
    estimated = engine.compute(estimated_request, facts(estimated_request), ())
    comparison = engine.compare(actual, estimated)

    assert comparison.left_basis is ProfitabilityBasis.ACTUAL
    assert comparison.right_basis is ProfitabilityBasis.ESTIMATED
    assert comparison.net_profit_variance_minor == 0
    foreign_request = replace(actual_request, scope=ProfitabilityScope.BRANCH)
    foreign_facts = tuple(
        replace(item, fact=replace(item.fact, scope=ProfitabilityScope.BRANCH))
        for item in facts(actual_request)
    )
    foreign = engine.compute(foreign_request, foreign_facts, ())
    with pytest.raises(ProfitabilityEngineError, match="scopes"):
        engine.compare(actual, foreign)


@pytest.mark.parametrize("scope", tuple(ProfitabilityScope))
def test_compares_every_like_scope(scope: ProfitabilityScope) -> None:
    engine = ReconciledProfitabilityEngine()
    left_request = replace(request(), scope=scope)
    right_request = replace(request(), scope=scope, subject_id=uuid4())
    left_facts = tuple(
        replace(item, fact=replace(item.fact, scope=scope))
        for item in facts(left_request)
    )
    right_facts = tuple(
        replace(
            item,
            fact=replace(item.fact, scope=scope, subject_id=right_request.subject_id),
        )
        for item in facts(right_request)
    )
    comparison = engine.compare(
        engine.compute(left_request, left_facts, ()),
        engine.compute(right_request, right_facts, ()),
    )
    assert comparison.scope is scope


def test_rejects_invalid_acquisition_lineage() -> None:
    item_request = request()
    invalid = replace(facts(item_request)[0], acquisition_digest="bad")
    with pytest.raises(ProfitabilityEngineError, match="SHA-256"):
        ReconciledProfitabilityEngine().compute(
            item_request, (invalid, *facts(item_request)[1:]), ()
        )
