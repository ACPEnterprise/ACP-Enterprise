from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from app.business_economics.findings import (
    FindingState,
    FindingSubject,
    SubjectKind,
    evaluate_economic_findings,
)
from app.business_economics.measurement_contract import (
    MeasurementComponent,
    MeasurementEvidenceInput,
    MeasurementGateState,
    PolicyPrerequisite,
    PrerequisiteState,
    evaluate_contribution_measurement_gate,
)
from app.business_economics.measurement_package import (
    MeasurementPackageIntegrityError,
    seal_measurement_readiness_package,
    verify_measurement_readiness_package,
)
from app.business_economics.source_conformance import (
    EconomicComponent,
    EvidenceAssertion,
    EvidenceConfidence,
)

COMPANY = UUID("00000000-0000-0000-0000-000000000001")
BRANCH = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)


def _input(
    *,
    authority: str = "acp_accepted_domain_fact",
    accepted: bool = True,
    state: FindingState = FindingState.READY,
    value_digest: str = "b" * 64,
    company_id: UUID = COMPANY,
    branch_id: UUID | None = BRANCH,
) -> MeasurementEvidenceInput:
    return MeasurementEvidenceInput(
        input_id="revenue-synthetic",
        subject_id="job-synthetic",
        reconciliation_key="job:synthetic",
        component=MeasurementComponent.REVENUE_EARNED_VALUE,
        source_authority=authority,
        evidence_state=state,
        confidence=(
            EvidenceConfidence.AVAILABLE
            if state is FindingState.READY
            else EvidenceConfidence.PARTIAL
        ),
        source_value=Decimal(10),
        currency="USD",
        unit=None,
        effective_date=date(2026, 8, 25),
        as_of=NOW,
        accepted_for_measurement=accepted,
        limitations=(),
        evidence_digest="a" * 64,
        value_digest=value_digest,
        package_digest="c" * 64,
        company_id=company_id,
        branch_id=branch_id,
    )


def _findings():
    assertion = EvidenceAssertion(
        assertion_id="revenue-assertion",
        source_system="acp",
        source_authority="acp_accepted_domain_fact",
        component=EconomicComponent.REVENUE,
        semantic_key="job:synthetic",
        value_digest="b" * 64,
        evidence_digest="a" * 64,
        package_digest="c" * 64,
        confidence=EvidenceConfidence.AVAILABLE,
        limitations=(
            "satisfies:source_reported_revenue",
            "satisfies:finance_accepted_revenue_basis",
        ),
    )
    return evaluate_economic_findings(
        subjects=(
            FindingSubject(
                subject_id="job-synthetic",
                subject_kind=SubjectKind.JOB,
                reconciliation_key="job:synthetic",
                required_components=(EconomicComponent.REVENUE,),
            ),
        ),
        assertions=(assertion,),
    )


def _gate(evidence, findings=(), policies=()):
    return evaluate_contribution_measurement_gate(
        subject_id="job-synthetic",
        subject_kind=SubjectKind.JOB,
        reconciliation_key="job:synthetic",
        required_components=(MeasurementComponent.REVENUE_EARNED_VALUE,),
        evidence=evidence,
        findings=findings,
        policy_dependencies=policies,
    )


def _seal(evidence, findings=(), policies=()):
    return seal_measurement_readiness_package(
        company_id=COMPANY,
        branch_id=BRANCH,
        gate=_gate(evidence, findings, policies),
        findings=findings,
    )


def test_identical_state_has_identical_package_identity_digest_and_replay() -> None:
    evidence = (_input(),)
    findings = _findings()
    first = _seal(evidence, findings)
    second = _seal(evidence, findings)
    assert first == second
    assert first.package_id.endswith(first.package_digest)
    verify_measurement_readiness_package(first)


def test_tampering_evidence_fails_integrity_verification() -> None:
    package = _seal((_input(),))
    tampered_input = replace(package.evidence[0], value_digest="d" * 64)
    tampered = replace(package, evidence=(tampered_input,))
    with pytest.raises(MeasurementPackageIntegrityError):
        verify_measurement_readiness_package(tampered)


def test_evidence_acceptance_and_authority_changes_change_package_digest() -> None:
    accepted = _seal((_input(),))
    unaccepted_input = _input(accepted=False)
    unaccepted = _seal((unaccepted_input,))
    different_authority = _seal((_input(authority="another_accepted_domain"),))
    assert accepted.package_digest != unaccepted.package_digest
    assert accepted.package_digest != different_authority.package_digest
    assert unaccepted.gate.state is MeasurementGateState.NOT_MEASURABLE


def test_finding_change_changes_package_digest() -> None:
    findings = _findings()
    original = _seal((_input(),), findings)
    changed_finding = replace(
        findings[0], limitations=(*findings[0].limitations, "synthetic_new_limitation")
    )
    changed = _seal((_input(),), (changed_finding,))
    assert original.package_digest != changed.package_digest


def test_unresolved_policy_is_packaged_and_changes_digest() -> None:
    first_policy = PolicyPrerequisite(
        dependency_id="revenue-recognition",
        component=MeasurementComponent.REVENUE_EARNED_VALUE,
        state=PrerequisiteState.UNRESOLVED,
        authority="finance_owner_decision_required",
    )
    second_policy = replace(first_policy, authority="finance_review_required")
    first = _seal((_input(),), policies=(first_policy,))
    second = _seal((_input(),), policies=(second_policy,))
    assert first.package_digest != second.package_digest
    assert first.policy_dependencies[0].state is PrerequisiteState.UNRESOLVED
    assert first.gate.state is MeasurementGateState.NOT_MEASURABLE


def test_inconsistent_gate_fails_closed() -> None:
    evidence = (_input(),)
    gate = _gate(evidence)
    inconsistent = replace(gate, state=MeasurementGateState.NOT_MEASURABLE)
    with pytest.raises(MeasurementPackageIntegrityError, match="inconsistent"):
        seal_measurement_readiness_package(
            company_id=COMPANY,
            branch_id=BRANCH,
            gate=inconsistent,
            findings=(),
        )


def test_company_and_branch_isolation_fail_closed() -> None:
    wrong_company = _input(company_id=UUID("00000000-0000-0000-0000-000000000099"))
    with pytest.raises(MeasurementPackageIntegrityError, match="Company"):
        _seal((wrong_company,))
    with pytest.raises(MeasurementPackageIntegrityError, match="Branch"):
        _seal((_input(branch_id=None),))


def test_missing_and_conflicting_evidence_states_are_preserved() -> None:
    missing = _seal(())
    assert missing.gate.state is MeasurementGateState.NOT_MEASURABLE
    assert missing.gate.components[0].blocking_reasons == (
        "required_evidence_absent_not_zero",
    )
    conflict = _seal(
        (
            _input(value_digest="a" * 64),
            replace(_input(value_digest="b" * 64), input_id="revenue-synthetic-other"),
        )
    )
    assert conflict.gate.state is MeasurementGateState.CONFLICTING


def test_qbo_and_public_hcp_authority_barriers_survive_packaging() -> None:
    for authority in (
        "quickbooks_online_source_reported",
        "hcp_authoritative_operational_source",
    ):
        evidence = _input(
            authority=authority,
            accepted=False,
            state=FindingState.PARTIAL,
        )
        package = _seal((evidence,))
        assert not package.evidence[0].accepted_for_measurement
        assert package.gate.state is MeasurementGateState.NOT_MEASURABLE


def test_adapter_compatible_scope_fields_are_required_for_sealing() -> None:
    missing_scope = replace(_input(), company_id=None, branch_id=None)
    with pytest.raises(MeasurementPackageIntegrityError):
        _seal((missing_scope,))
