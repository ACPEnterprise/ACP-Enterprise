from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.business_economics.overhead_authority import (
    AllocationBasisEvidence,
    AllocationBasisType,
    AllocationPolicyAuthority,
    AllocationReadiness,
    OverheadAuthorityError,
    OverheadPoolAuthority,
    OverheadSourceEvidence,
    allocate_overhead,
    assess_allocation_readiness,
    assess_configuration_readiness,
    callback_economics_requirements,
)

NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)
START = date(2026, 8, 1)
END = date(2026, 8, 31)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def authority_fixture():
    company = uuid4()
    branch = uuid4()
    pool = OverheadPoolAuthority(
        uuid4(),
        company,
        branch,
        "synthetic_facility",
        1,
        START,
        None,
        "USD",
        ("synthetic_accounting_pool",),
        True,
        DIGEST_A,
    )
    policy = AllocationPolicyAuthority(
        uuid4(),
        company,
        branch,
        "synthetic_labor_hours",
        1,
        pool.pool_id,
        AllocationBasisType.LABOR_HOURS,
        "accepted_job_labor_hours",
        START,
        None,
        45,
        True,
        DIGEST_B,
    )
    sources = (
        OverheadSourceEvidence(
            "synthetic-pool",
            DIGEST_A,
            company,
            branch,
            START,
            END,
            "USD",
            1001,
            NOW,
            True,
        ),
    )
    basis = (
        AllocationBasisEvidence(
            "job",
            UUID(int=1),
            company,
            branch,
            START,
            END,
            Decimal(1),
            "basis-1",
            DIGEST_A,
            NOW,
            True,
        ),
        AllocationBasisEvidence(
            "job",
            UUID(int=2),
            company,
            branch,
            START,
            END,
            Decimal(1),
            "basis-2",
            DIGEST_B,
            NOW,
            True,
        ),
        AllocationBasisEvidence(
            "job",
            UUID(int=3),
            company,
            branch,
            START,
            END,
            Decimal(1),
            "basis-3",
            "c" * 64,
            NOW,
            True,
        ),
    )
    return company, branch, pool, policy, sources, basis


def assess(company, branch, pool, policy, sources, basis):
    return assess_allocation_readiness(
        company_id=company,
        branch_id=branch,
        period_start=START,
        period_end=END,
        currency="USD",
        as_of=NOW,
        pools=(pool,),
        policies=(policy,),
        sources=sources,
        basis=basis,
    )


def test_complete_allocation_reconciles_rounding_and_replays() -> None:
    company, branch, pool, policy, sources, basis = authority_fixture()
    result = allocate_overhead(
        company_id=company,
        branch_id=branch,
        period_start=START,
        period_end=END,
        currency="usd",
        as_of=NOW,
        pool=pool,
        policy=policy,
        sources=sources,
        basis=basis,
    )
    replay = allocate_overhead(
        company_id=company,
        branch_id=branch,
        period_start=START,
        period_end=END,
        currency="USD",
        as_of=NOW,
        pool=pool,
        policy=policy,
        sources=sources,
        basis=basis,
    )
    assert result == replay
    assert [line.amount_minor for line in result.lines] == [334, 334, 333]
    assert (
        sum(line.amount_minor for line in result.lines) == result.amount_minor == 1001
    )
    assert result.currency == "USD"


def test_configured_is_distinct_from_economic_readiness() -> None:
    _company, _branch, pool, policy, _sources, _basis = authority_fixture()
    configured = assess_configuration_readiness((pool,), (policy,))
    assert configured.state is AllocationReadiness.CONFIGURED


@pytest.mark.parametrize(
    ("mutation", "state"),
    [
        ("unconfigured", AllocationReadiness.UNCONFIGURED),
        ("policy_missing", AllocationReadiness.POLICY_REQUIRED),
        ("source_missing", AllocationReadiness.INSUFFICIENT_SOURCE),
        ("stale", AllocationReadiness.STALE),
        ("conflicting", AllocationReadiness.CONFLICTING),
    ],
)
def test_readiness_is_explicit_and_fail_closed(
    mutation: str, state: AllocationReadiness
) -> None:
    company, branch, pool, policy, sources, basis = authority_fixture()
    pools = () if mutation == "unconfigured" else (pool,)
    policies = () if mutation == "policy_missing" else (policy,)
    if mutation == "source_missing":
        sources = ()
    if mutation == "stale":
        sources = (
            replace(sources[0], accepted_at=datetime(2020, 1, 1, tzinfo=timezone.utc)),
        )
    if mutation == "conflicting":
        policies = (
            policy,
            replace(policy, policy_id=uuid4(), authority_digest="d" * 64),
        )
    result = assess_allocation_readiness(
        company_id=company,
        branch_id=branch,
        period_start=START,
        period_end=END,
        currency="USD",
        as_of=NOW,
        pools=pools,
        policies=policies,
        sources=sources,
        basis=basis,
    )
    assert result.state is state


def test_period_currency_and_branch_mismatches_fail_closed() -> None:
    company, branch, pool, policy, sources, basis = authority_fixture()
    assert (
        assess(
            company, branch, pool, policy, (replace(sources[0], currency="CAD"),), basis
        ).state
        is AllocationReadiness.CONFLICTING
    )
    assert (
        assess(
            company,
            branch,
            pool,
            policy,
            sources,
            (replace(basis[0], period_start=date(2026, 7, 1)), *basis[1:]),
        ).state
        is AllocationReadiness.CONFLICTING
    )
    assert (
        assess(
            company,
            branch,
            pool,
            policy,
            sources,
            (replace(basis[0], branch_id=uuid4()), *basis[1:]),
        ).state
        is AllocationReadiness.CONFLICTING
    )


def test_policy_successor_and_source_correction_create_new_history() -> None:
    company, branch, pool, policy, sources, basis = authority_fixture()
    original = allocate_overhead(
        company_id=company,
        branch_id=branch,
        period_start=START,
        period_end=END,
        currency="USD",
        as_of=NOW,
        pool=pool,
        policy=policy,
        sources=sources,
        basis=basis,
    )
    successor_policy = replace(
        policy,
        policy_id=uuid4(),
        version=2,
        authority_digest="e" * 64,
        supersedes_policy_id=policy.policy_id,
    )
    successor = allocate_overhead(
        company_id=company,
        branch_id=branch,
        period_start=START,
        period_end=END,
        currency="USD",
        as_of=NOW,
        pool=pool,
        policy=successor_policy,
        sources=sources,
        basis=basis,
        predecessor_allocation_id=original.allocation_id,
    )
    corrected = allocate_overhead(
        company_id=company,
        branch_id=branch,
        period_start=START,
        period_end=END,
        currency="USD",
        as_of=NOW,
        pool=pool,
        policy=policy,
        sources=(replace(sources[0], digest="f" * 64),),
        basis=basis,
        predecessor_allocation_id=original.allocation_id,
    )
    assert successor.allocation_id != original.allocation_id
    assert corrected.allocation_digest != original.allocation_digest
    assert successor.predecessor_allocation_id == original.allocation_id


def test_zero_basis_and_unsupported_scope_do_not_allocate() -> None:
    company, branch, pool, policy, sources, basis = authority_fixture()
    zero = tuple(replace(item, basis_value=Decimal(0)) for item in basis)
    with pytest.raises(OverheadAuthorityError, match="insufficient_source"):
        allocate_overhead(
            company_id=company,
            branch_id=branch,
            period_start=START,
            period_end=END,
            currency="USD",
            as_of=NOW,
            pool=pool,
            policy=policy,
            sources=sources,
            basis=zero,
        )


def test_callback_seam_is_truthfully_external_gated() -> None:
    seam = callback_economics_requirements()
    assert seam["state"] == "external_gate"
    assert (
        "authoritative_callback_or_warranty_job_relationship"
        in seam["required_authorities"]
    )
