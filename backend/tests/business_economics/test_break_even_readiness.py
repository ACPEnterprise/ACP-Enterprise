from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.business_economics.break_even_readiness import (
    BREAK_EVEN_READINESS_VERSION,
    BreakEvenInputKind,
    break_even_input_contract,
    build_break_even_input_readiness,
)
from app.business_economics.findings import FindingState
from app.business_economics.measurement_contract import (
    MeasurementComponent,
    MeasurementEvidenceInput,
)
from app.business_economics.source_conformance import EvidenceConfidence
from app.operational_measurement.labor_evidence import (
    EmployeeJobLink,
    IntervalKind,
    LaborInterval,
    ProvenanceRef,
    compose_labor_evidence,
)
from app.operational_measurement.productive_hour_readiness import (
    build_productive_hour_readiness,
)

START = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)


def _productive_packet():
    company, branch, employee, job, appointment = (uuid4() for _ in range(5))
    ref = ProvenanceRef("accepted_source", "record-1", "v1", "source-digest")
    labor = compose_labor_evidence(
        company_id=company,
        links=(EmployeeJobLink(company, branch, employee, job, appointment, ref),),
        intervals=(
            LaborInterval(
                company,
                None,
                employee,
                IntervalKind.PAID,
                START,
                START + timedelta(hours=8),
                ref,
            ),
            LaborInterval(
                company,
                branch,
                employee,
                IntervalKind.WORKED,
                START,
                START + timedelta(hours=5),
                ref,
                job,
                appointment,
            ),
            LaborInterval(
                company,
                branch,
                employee,
                IntervalKind.PRODUCTIVE,
                START,
                START + timedelta(hours=4),
                ref,
                job,
                appointment,
            ),
        ),
    )
    return build_productive_hour_readiness(labor), company


def _cost(
    company: UUID, *, authority: str = "accepted_payroll"
) -> MeasurementEvidenceInput:
    accepted = authority != "quickbooks_online_source_reported"
    return MeasurementEvidenceInput(
        input_id=f"labor:{authority}",
        subject_id=str(company),
        reconciliation_key="company-period:2026-09",
        component=MeasurementComponent.DIRECT_LABOR,
        source_authority=authority,
        evidence_state=FindingState.READY if accepted else FindingState.PARTIAL,
        confidence=EvidenceConfidence.AVAILABLE
        if accepted
        else EvidenceConfidence.PARTIAL,
        source_value=Decimal("1200.00") if accepted else None,
        currency="USD" if accepted else None,
        unit=None,
        effective_date=START.date(),
        as_of=START,
        accepted_for_measurement=accepted,
        limitations=() if accepted else ("source_reported_only",),
        evidence_digest="a" * 64,
        value_digest="b" * 64,
        package_digest="c" * 64,
        company_id=company,
        branch_id=None,
    )


def test_packet_preserves_facts_and_never_selects_break_even_policy() -> None:
    productive, company = _productive_packet()
    packet = build_break_even_input_readiness(
        productive, economic_evidence=(_cost(company),)
    )
    facts = {item.kind: item for item in packet.facts}
    assert packet.contract_version == BREAK_EVEN_READINESS_VERSION
    assert facts[BreakEvenInputKind.PAID_MINUTES].value == 480
    assert facts[BreakEvenInputKind.ACTUAL_WORKED_MINUTES].value == 300
    assert facts[BreakEvenInputKind.PRODUCTIVE_JOB_MINUTES].value == 240
    assert facts[BreakEvenInputKind.ACTUAL_LABOR_COST].value == Decimal("1200.00")
    assert "actual_direct_material_cost" in packet.missing_inputs
    assert "labor_burden_prerequisites" in packet.missing_inputs
    assert packet.branch_id is None
    assert "break_even_method" in packet.policy_gates
    assert packet.model_output is None
    assert packet.recommendation is None
    contract = break_even_input_contract()
    assert contract["canonical_break_even_rate"] is None
    assert contract["mutation_authority"] == "none"


def test_qbo_source_reported_cost_is_not_promoted() -> None:
    productive, company = _productive_packet()
    packet = build_break_even_input_readiness(
        productive,
        economic_evidence=(
            _cost(company, authority="quickbooks_online_source_reported"),
        ),
    )
    labor = next(
        item
        for item in packet.facts
        if item.kind is BreakEvenInputKind.ACTUAL_LABOR_COST
    )
    assert labor.state == "PARTIAL"
    assert labor.value is None
    assert (
        "accepted_authoritative_evidence_required; missing is not zero"
        in labor.limitations
    )


def test_source_metadata_and_exact_required_matrix_are_preserved() -> None:
    productive, company = _productive_packet()
    packet = build_break_even_input_readiness(
        productive,
        economic_evidence=(_cost(company),),
        period_start=START.date(),
        period_end=START.date(),
    )
    labor = next(
        item
        for item in packet.facts
        if item.kind is BreakEvenInputKind.COMPENSATION_LABOR_COST_AUTHORITY
    )
    assert labor.source_authorities == ("accepted_payroll",)
    assert labor.source_dates == (START.isoformat(),)
    assert labor.confidence == "available"
    assert packet.period_start == START.date()
    assert packet.model_output is None


def test_mixed_periods_and_duplicate_semantic_facts_fail_closed() -> None:
    productive, company = _productive_packet()
    first = _cost(company)
    second = _cost(company)
    object.__setattr__(second, "input_id", "labor:second")
    object.__setattr__(second, "reconciliation_key", "company-period:2026-10")
    with pytest.raises(ValueError, match="mixed reconciliation periods"):
        build_break_even_input_readiness(productive, economic_evidence=(first, second))
    object.__setattr__(second, "reconciliation_key", first.reconciliation_key)
    with pytest.raises(ValueError, match="duplicate break-even economic fact"):
        build_break_even_input_readiness(productive, economic_evidence=(first, second))


def test_foreign_company_and_branch_aggregation_fail_closed() -> None:
    productive, company = _productive_packet()
    with pytest.raises(ValueError, match="foreign Company"):
        build_break_even_input_readiness(
            productive, economic_evidence=(_cost(uuid4()),)
        )
    branch_cost = _cost(company)
    object.__setattr__(branch_cost, "branch_id", uuid4())
    with pytest.raises(ValueError, match="Branch evidence"):
        build_break_even_input_readiness(productive, economic_evidence=(branch_cost,))
