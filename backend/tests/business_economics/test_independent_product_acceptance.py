from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.business_economics.profitability_computation import (
    ProfitabilityComputationError,
)
from app.business_economics.profitability_domain import EconomicCategory
from app.business_economics.workspace import EconomicsWorkspaceService, JobIdentity
from tests.business_economics.test_profitability_computation import (
    compute,
    inputs,
    request,
)


def _component(amount: int | None) -> dict[str, object]:
    return {
        "state": "measured" if amount is not None else "missing",
        "amount_minor": amount,
    }


def _record(
    *,
    revenue: int = 100_000,
    labor: int = 30_000,
    materials: int | None = 20_000,
    equipment: int = 0,
    truck: int = 0,
    overhead: int | None = None,
    freshness: str = "current",
) -> SimpleNamespace:
    gross = (
        None if materials is None else revenue - labor - materials - equipment - truck
    )
    net = None if gross is None or overhead is None else gross - overhead
    missing = [
        name
        for name, amount in {
            "materials": materials,
            "overhead": overhead,
        }.items()
        if amount is None
    ]
    return SimpleNamespace(
        id=uuid4(),
        subject_id=uuid4(),
        scope="job",
        currency="USD",
        components={
            "revenue": _component(revenue),
            "labor": _component(labor),
            "materials": _component(materials),
            "equipment": _component(equipment),
            "truck": _component(truck),
            "overhead": _component(overhead),
            "gross_profit": _component(gross),
            "net_profit": _component(net),
        },
        quality={
            "freshness_status": freshness,
            "completeness_percent": ((6 - len(missing)) * 100) // 6,
            "confidence_percent": 0 if materials is None else 100,
            "missing_categories": missing,
        },
        metrics={},
        branch_id=uuid4(),
    )


def _identity(record: SimpleNamespace, *, branch: str = "Main") -> JobIdentity:
    identity = JobIdentity(
        f"JOB-{str(record.subject_id)[:8]}",
        "completed",
        uuid4(),
        branch,
        uuid4(),
        "Synthetic Customer",
        "repair",
    )
    record.branch_id = identity.branch_id
    return identity


def test_profitable_break_even_losing_and_rollups_reconcile() -> None:
    profitable = _record(revenue=100_000, labor=30_000, materials=20_000)
    break_even = _record(revenue=50_000, labor=30_000, materials=20_000)
    losing = _record(revenue=40_000, labor=30_000, materials=20_000)
    identities = {
        item.subject_id: _identity(item, branch="North" if item is losing else "Main")
        for item in (profitable, break_even, losing)
    }

    value = EconomicsWorkspaceService._project(
        (profitable, break_even, losing), identities
    )

    assert value["totals"]["revenue"] == 190_000
    assert value["totals"]["gross_profit"] == 40_000
    assert sum(item["revenue_minor"] for item in value["branches"]) == 190_000
    assert sum(item["contribution_minor"] for item in value["branches"]) == 40_000
    assert [item["contribution_minor"] for item in value["jobs"]] == [
        50_000,
        0,
        -10_000,
    ]


@pytest.mark.parametrize("freshness", ["current", "stale"])
def test_comparison_requires_complete_current_populations(freshness: str) -> None:
    partial = _record(overhead=None, freshness=freshness)
    identities = {partial.subject_id: _identity(partial)}
    projection = EconomicsWorkspaceService._project((partial,), identities)

    comparison = EconomicsWorkspaceService._comparison(projection, projection)

    assert comparison["state"] == "unavailable"
    assert "complete" in comparison["reason"].lower()


def test_rollup_does_not_label_partial_job_complete() -> None:
    partial = _record(overhead=None)
    identities = {partial.subject_id: _identity(partial)}

    value = EconomicsWorkspaceService._project((partial,), identities)

    assert value["quality_state"] == "partial"
    assert value["service_categories"][0]["complete_jobs"] == 0
    assert value["service_categories"][0]["quality_state"] == "partial"
    assert value["fully_allocated_available"] is False
    assert value["jobs"][0]["contribution_minor"] == 50_000
    assert value["jobs"][0]["net_profit_minor"] is None


def test_unattributed_admitted_result_is_explicitly_excluded() -> None:
    attributed = _record(overhead=0)
    missing_identity = _record(overhead=0)

    value = EconomicsWorkspaceService._project(
        (attributed, missing_identity),
        {attributed.subject_id: _identity(attributed)},
    )

    assert value["source_result_count"] == 2
    assert value["excluded_job_count"] == 1
    assert value["quality_state"] == "partial"
    assert "attribution" in value["explanation"].lower()


def test_duplicate_source_lineage_cannot_double_economic_truth() -> None:
    item_request = request()
    values = inputs(item_request)
    revenue = next(item for item in values if item.category is EconomicCategory.REVENUE)
    duplicate = replace(
        revenue,
        fact_id=uuid4(),
        measurement_id=uuid4(),
        fact_key="revenue-duplicate-fact",
    )

    with pytest.raises(ProfitabilityComputationError, match="source lineage"):
        compute(item_request, [*values, duplicate])

    contradiction = replace(duplicate, amount_minor=duplicate.amount_minor + 1)
    with pytest.raises(ProfitabilityComputationError, match="source lineage"):
        compute(item_request, [*values, contradiction])


@pytest.mark.parametrize(
    ("source_system", "record_type"),
    [
        ("acp_jobs", "job_completion"),
        ("acp_invoicing", "invoice_line"),
        ("acp_payments", "payment_application"),
        ("acp_payroll", "payroll_cost_fact"),
        ("acp_inventory", "material_consumption"),
        ("acp_purchasing", "vendor_bill_match"),
        ("acp_accounting", "posting_fact"),
        ("quickbooks_online", "source_assertion"),
        ("housecall_pro", "source_assertion"),
        ("acp_events", "business_event"),
    ],
)
def test_logical_source_record_versions_cannot_double_economic_truth(
    source_system: str, record_type: str
) -> None:
    item_request = request()
    values = inputs(item_request)
    original = next(
        item for item in values if item.category is EconomicCategory.REVENUE
    )
    original_evidence = replace(
        original.evidence[0],
        source_system=source_system,
        record_type=record_type,
        record_id="canonical-source-record",
    )
    original = replace(original, evidence=(original_evidence,))
    corrected_evidence = replace(
        original_evidence,
        source_version="2",
        content_digest="a" * 64,
    )
    correction = replace(
        original,
        fact_id=uuid4(),
        measurement_id=uuid4(),
        fact_key="revenue-corrected-technical-identity",
        version=2,
        amount_minor=original.amount_minor + 1,
        evidence=(corrected_evidence,),
    )
    remaining = [
        item for item in values if item.category is not EconomicCategory.REVENUE
    ]

    with pytest.raises(ProfitabilityComputationError, match="source lineage"):
        compute(item_request, [original, correction, *remaining])


def test_distinct_authoritative_source_records_remain_distinct_economic_facts() -> None:
    item_request = request()
    values = inputs(item_request)
    original = next(
        item for item in values if item.category is EconomicCategory.REVENUE
    )
    second_evidence = replace(
        original.evidence[0],
        record_id="revenue-2",
        content_digest="b" * 64,
    )
    second = replace(
        original,
        fact_id=uuid4(),
        measurement_id=uuid4(),
        fact_key="second-legitimate-revenue-fact",
        amount_minor=86_500,
        evidence=(second_evidence,),
    )

    result = compute(item_request, [*values, second])

    assert result.analysis.revenue.amount_minor == 600_000
