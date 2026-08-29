import hashlib
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.business_economics.allocation_engine import (
    AllocationPolicyInput,
    AllocationStrategyKind,
    AllocationTargetInput,
    CostPoolInput,
    DeterministicAllocationEngine,
    DeterministicAllocationError,
)
from app.business_economics.profitability_domain import EconomicCategory
from app.business_economics.profitability_intelligence import (
    AllocationBoundary,
    ProfitabilityEvidence,
    ProfitabilityValueState,
)

COMPANY = UUID("10000000-0000-0000-0000-000000000001")
BRANCH = UUID("20000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)


def evidence(key: str) -> ProfitabilityEvidence:
    return ProfitabilityEvidence(
        owner="economics",
        source_system="acp-enterprise",
        record_type="allocation-driver",
        record_id=key,
        source_version="1",
        content_digest=hashlib.sha256(key.encode()).hexdigest(),
        effective_at=NOW,
    )


def pool(amount: int = 10_001) -> CostPoolInput:
    return CostPoolInput(
        source_fact_id=UUID("30000000-0000-0000-0000-000000000001"),
        source_version=1,
        company_id=COMPANY,
        branch_id=BRANCH,
        category=EconomicCategory.OVERHEAD,
        amount_minor=amount,
        currency="USD",
        state=ProfitabilityValueState.MEASURED,
        confidence_percent=100,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        evidence=(evidence("pool"),),
        acquisition_digest="a" * 64,
        completeness_percent=100,
    )


def policy(boundary: AllocationBoundary) -> AllocationPolicyInput:
    return AllocationPolicyInput(
        policy_id=UUID("40000000-0000-0000-0000-000000000001"),
        policy_key=f"{boundary.value}-policy",
        policy_version=2,
        run_version=3,
        boundary=boundary,
        strategy=(
            AllocationStrategyKind.DIRECT
            if boundary is AllocationBoundary.DIRECT
            else AllocationStrategyKind.PROPORTIONAL
        ),
        driver="measured-weight",
        effective_start=date(2026, 1, 1),
        effective_end=None,
        explanation="Approved measured allocation policy.",
        as_of=NOW,
        maximum_evidence_age=timedelta(days=30),
    )


def target(index: int, weight: int = 1) -> AllocationTargetInput:
    return AllocationTargetInput(
        company_id=COMPANY,
        branch_id=BRANCH,
        subject_type="job",
        subject_id=UUID(f"50000000-0000-0000-0000-{index:012d}"),
        weight=weight,
        confidence_percent=100,
        completeness_percent=100,
        driver_evidence=(evidence(f"target-{index}"),),
    )


@pytest.mark.parametrize(
    "boundary",
    (
        AllocationBoundary.DIRECT,
        AllocationBoundary.TECHNICIAN,
        AllocationBoundary.TRUCK_DAY,
        AllocationBoundary.BRANCH,
        AllocationBoundary.COMPANY,
    ),
)
def test_supports_approved_boundaries(boundary: AllocationBoundary) -> None:
    targets = (
        (target(1),)
        if boundary is AllocationBoundary.DIRECT
        else (target(1), target(2))
    )
    result = DeterministicAllocationEngine().allocate(pool(), policy(boundary), targets)

    assert sum(item.allocated_amount_minor for item in result.lines) == 10_001
    assert result.residual_minor == 0
    assert result.policy.boundary is boundary
    assert all(item.evidence for item in result.lines)


def test_replay_is_identical_and_remainder_order_is_canonical() -> None:
    engine = DeterministicAllocationEngine()
    targets = (target(2), target(1), target(3))
    first = engine.allocate(pool(), policy(AllocationBoundary.TECHNICIAN), targets)
    replay = engine.allocate(
        pool(), policy(AllocationBoundary.TECHNICIAN), tuple(reversed(targets))
    )

    assert first == replay
    assert [item.allocated_amount_minor for item in first.lines] == [3334, 3334, 3333]


def test_negative_correction_balances() -> None:
    result = DeterministicAllocationEngine().allocate(
        pool(-101),
        policy(AllocationBoundary.TRUCK_DAY),
        (target(1), target(2)),
    )

    assert [item.allocated_amount_minor for item in result.lines] == [-51, -50]
    assert sum(item.allocated_amount_minor for item in result.lines) == -101


def test_direct_cost_requires_one_target() -> None:
    with pytest.raises(DeterministicAllocationError, match="exactly one"):
        DeterministicAllocationEngine().allocate(
            pool(), policy(AllocationBoundary.DIRECT), (target(1), target(2))
        )


def test_rejects_cross_company_duplicate_and_ineffective_inputs() -> None:
    engine = DeterministicAllocationEngine()
    with pytest.raises(DeterministicAllocationError, match="Company"):
        engine.allocate(
            pool(),
            policy(AllocationBoundary.COMPANY),
            (
                target(1),
                AllocationTargetInput(
                    company_id=UUID(int=99),
                    branch_id=BRANCH,
                    subject_type="job",
                    subject_id=UUID(int=98),
                    weight=1,
                    confidence_percent=100,
                    completeness_percent=100,
                    driver_evidence=(evidence("foreign"),),
                ),
            ),
        )
    with pytest.raises(DeterministicAllocationError, match="unique"):
        engine.allocate(
            pool(), policy(AllocationBoundary.BRANCH), (target(1), target(1))
        )
    expired = replace(
        policy(AllocationBoundary.COMPANY), effective_end=date(2026, 7, 31)
    )
    with pytest.raises(DeterministicAllocationError, match="not effective"):
        engine.allocate(pool(), expired, (target(1),))


@pytest.mark.parametrize("strategy", tuple(AllocationStrategyKind))
def test_supports_every_policy_strategy(strategy: AllocationStrategyKind) -> None:
    boundary = (
        AllocationBoundary.DIRECT
        if strategy is AllocationStrategyKind.DIRECT
        else AllocationBoundary.COMPANY
    )
    result = DeterministicAllocationEngine().allocate(
        pool(), replace(policy(boundary), strategy=strategy), (target(1),)
    )
    assert result.policy.policy_version == 2


def test_rejects_circular_stale_conflicting_currency_and_duplicate_replay() -> None:
    engine = DeterministicAllocationEngine()
    circular_pool = replace(pool(), source_subject_ids=(target(1).subject_id,))
    with pytest.raises(DeterministicAllocationError, match="circular"):
        engine.allocate(circular_pool, policy(AllocationBoundary.COMPANY), (target(1),))

    stale_policy = replace(
        policy(AllocationBoundary.COMPANY),
        as_of=NOW + timedelta(days=31),
    )
    with pytest.raises(DeterministicAllocationError, match="stale"):
        engine.allocate(pool(), stale_policy, (target(1),))

    with pytest.raises(DeterministicAllocationError, match="currency"):
        engine.allocate(
            replace(pool(), currency="EUR"),
            policy(AllocationBoundary.COMPANY),
            (target(1),),
        )

    first = engine.allocate(pool(), policy(AllocationBoundary.COMPANY), (target(1),))
    with pytest.raises(DeterministicAllocationError, match="duplicate"):
        engine.allocate(
            pool(),
            policy(AllocationBoundary.COMPANY),
            (target(1),),
            prior_allocation_ids=(first.allocation_id,),
        )

    conflict = replace(evidence("pool"), content_digest="e" * 64)
    with pytest.raises(DeterministicAllocationError, match="contradictory"):
        engine.allocate(
            replace(pool(), evidence=(evidence("pool"), conflict)),
            policy(AllocationBoundary.COMPANY),
            (target(1),),
        )
