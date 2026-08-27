from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from app.business_economics.findings import FindingState, SubjectKind
from app.business_economics.measurement_contract import (
    MeasurementComponent,
    MeasurementEvidenceInput,
    MeasurementGateState,
    PolicyPrerequisite,
    PrerequisiteState,
    evaluate_contribution_measurement_gate,
)
from app.business_economics.source_conformance import EvidenceConfidence


def _input(
    identity: str,
    component: MeasurementComponent,
    *,
    state: FindingState = FindingState.READY,
    accepted: bool = True,
    value: Decimal | None = Decimal(10),
    authority: str = "acp_accepted_domain_fact",
    value_digest: str = "b" * 64,
) -> MeasurementEvidenceInput:
    return MeasurementEvidenceInput(
        input_id=identity,
        subject_id="job-synthetic",
        reconciliation_key="job:synthetic",
        component=component,
        source_authority=authority,
        evidence_state=state,
        confidence=(
            EvidenceConfidence.AVAILABLE
            if state is FindingState.READY
            else EvidenceConfidence.PARTIAL
        ),
        source_value=value,
        currency="USD" if value is not None else None,
        unit=None,
        effective_date=date(2026, 8, 25),
        as_of=datetime(2026, 8, 27, tzinfo=timezone.utc),
        accepted_for_measurement=accepted,
        limitations=(),
        evidence_digest="a" * 64,
        value_digest=value_digest,
        package_digest="c" * 64,
    )


def _gate(required, evidence=(), policies=()):
    return evaluate_contribution_measurement_gate(
        subject_id="job-synthetic",
        subject_kind=SubjectKind.JOB,
        reconciliation_key="job:synthetic",
        required_components=required,
        evidence=evidence,
        findings=(),
        policy_dependencies=policies,
    )


def test_identical_inputs_produce_identical_gate_identity() -> None:
    evidence = (_input("revenue", MeasurementComponent.REVENUE_EARNED_VALUE),)
    assert _gate((MeasurementComponent.REVENUE_EARNED_VALUE,), evidence) == _gate(
        (MeasurementComponent.REVENUE_EARNED_VALUE,), evidence
    )


def test_missing_values_are_not_zero_and_gate_is_not_measurable() -> None:
    gate = _gate((MeasurementComponent.REVENUE_EARNED_VALUE,))
    assert gate.state is MeasurementGateState.NOT_MEASURABLE
    assert gate.components[0].state is FindingState.ABSENT
    assert "required_evidence_absent_not_zero" in gate.components[0].blocking_reasons


def test_ready_and_missing_components_are_partially_measurable() -> None:
    gate = _gate(
        (MeasurementComponent.REVENUE_EARNED_VALUE, MeasurementComponent.DIRECT_LABOR),
        (_input("revenue", MeasurementComponent.REVENUE_EARNED_VALUE),),
    )
    assert gate.state is MeasurementGateState.PARTIALLY_MEASURABLE
    assert gate.blocking_components == (MeasurementComponent.DIRECT_LABOR,)


def test_conflicting_value_digests_fail_closed() -> None:
    gate = _gate(
        (MeasurementComponent.SETTLEMENT,),
        (
            _input("payment-a", MeasurementComponent.SETTLEMENT, value_digest="a" * 64),
            _input("payment-b", MeasurementComponent.SETTLEMENT, value_digest="b" * 64),
        ),
    )
    assert gate.state is MeasurementGateState.CONFLICTING
    assert "evidence_values_conflict" in gate.components[0].blocking_reasons


def test_qbo_source_reported_cannot_be_accepted_measurement_truth() -> None:
    with pytest.raises(ValueError, match="not accepted economic truth"):
        _input(
            "qbo-revenue",
            MeasurementComponent.REVENUE_EARNED_VALUE,
            authority="quickbooks_online_source_reported",
        )
    qbo = _input(
        "qbo-revenue",
        MeasurementComponent.REVENUE_EARNED_VALUE,
        state=FindingState.PARTIAL,
        accepted=False,
        authority="quickbooks_online_source_reported",
    )
    assert (
        _gate((MeasurementComponent.REVENUE_EARNED_VALUE,), (qbo,)).state
        is MeasurementGateState.NOT_MEASURABLE
    )


def test_unresolved_policy_is_explicit_and_prevents_full_measurement() -> None:
    evidence = (_input("labor", MeasurementComponent.LABOR_BURDEN, value=None),)
    policy = PolicyPrerequisite(
        dependency_id="labor-burden-policy",
        component=MeasurementComponent.LABOR_BURDEN,
        state=PrerequisiteState.UNRESOLVED,
        authority="finance_owner_decision_required",
    )
    gate = _gate((MeasurementComponent.LABOR_BURDEN,), evidence, (policy,))
    assert gate.state is MeasurementGateState.NOT_MEASURABLE
    assert "required_policy_unresolved" in gate.components[0].blocking_reasons
    assert policy.policy_version is None


def test_supported_job_context_and_service_attribution_can_be_measurable() -> None:
    evidence = (
        _input("job", MeasurementComponent.JOB_CONTEXT, value=None),
        _input("service", MeasurementComponent.SERVICE_LINE_ATTRIBUTION, value=None),
        _input("posting", MeasurementComponent.ACCOUNTING_RECONCILIATION, value=None),
    )
    gate = _gate(
        (
            MeasurementComponent.JOB_CONTEXT,
            MeasurementComponent.SERVICE_LINE_ATTRIBUTION,
            MeasurementComponent.ACCOUNTING_RECONCILIATION,
        ),
        evidence,
    )
    assert gate.state is MeasurementGateState.MEASURABLE
    assert all(item.state is FindingState.READY for item in gate.components)


def test_contract_preserves_value_currency_dates_and_digests_without_calculation() -> (
    None
):
    evidence = _input("material", MeasurementComponent.DIRECT_MATERIAL)
    gate = _gate((MeasurementComponent.DIRECT_MATERIAL,), (evidence,))
    retained = gate.evidence[0]
    assert retained.source_value == Decimal(10)
    assert retained.currency == "USD"
    assert retained.effective_date == date(2026, 8, 25)
    assert retained.evidence_digest == "a" * 64
    assert not hasattr(gate, "profit")
    assert not hasattr(gate, "contribution_margin")
