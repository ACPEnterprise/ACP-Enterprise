from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

from app.business_economics.findings import FindingState, SubjectKind
from app.business_economics.measurement_admission import (
    AdmissionState,
    CalculationAdmissionRequest,
    evaluate_calculation_admission,
)
from app.business_economics.measurement_contract import (
    MEASUREMENT_DEFINITION_VERSION,
    MeasurementComponent,
    MeasurementEvidenceInput,
    PolicyPrerequisite,
    PrerequisiteState,
    evaluate_contribution_measurement_gate,
)
from app.business_economics.measurement_package import (
    MEASUREMENT_PACKAGE_VERSION,
    seal_measurement_readiness_package,
)
from app.business_economics.source_conformance import EvidenceConfidence

COMPANY = UUID("00000000-0000-0000-0000-000000000001")
BRANCH = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)
ACCEPTED_AUTHORITY = "acp_job_domain_accepted"


def _input(
    component: MeasurementComponent = MeasurementComponent.JOB_CONTEXT,
    *,
    identity: str = "job-context",
    authority: str = ACCEPTED_AUTHORITY,
    accepted: bool = True,
    state: FindingState = FindingState.READY,
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
        source_value=None,
        currency=None,
        unit=None,
        effective_date=None,
        as_of=NOW,
        accepted_for_measurement=accepted,
        limitations=(),
        evidence_digest="a" * 64,
        value_digest=value_digest,
        package_digest="c" * 64,
        company_id=COMPANY,
        branch_id=BRANCH,
    )


def _package(*, required, evidence=(), policies=()):
    gate = evaluate_contribution_measurement_gate(
        subject_id="job-synthetic",
        subject_kind=SubjectKind.JOB,
        reconciliation_key="job:synthetic",
        required_components=required,
        evidence=evidence,
        findings=(),
        policy_dependencies=policies,
    )
    return seal_measurement_readiness_package(
        company_id=COMPANY, branch_id=BRANCH, gate=gate, findings=()
    )


def _request(**changes) -> CalculationAdmissionRequest:
    values = {
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "subject_id": "job-synthetic",
        "subject_kind": SubjectKind.JOB,
        "reconciliation_key": "job:synthetic",
        "supported_package_versions": (MEASUREMENT_PACKAGE_VERSION,),
        "supported_measurement_versions": (MEASUREMENT_DEFINITION_VERSION,),
        "permitted_accepted_authorities": (ACCEPTED_AUTHORITY,),
        "required_policy_dependency_ids": (),
    }
    values.update(changes)
    return CalculationAdmissionRequest(**values)


def test_valid_package_is_admitted_deterministically() -> None:
    package = _package(
        required=(MeasurementComponent.JOB_CONTEXT,), evidence=(_input(),)
    )
    first = evaluate_calculation_admission(package, _request())
    second = evaluate_calculation_admission(package, _request())
    assert first == second
    assert first.state is AdmissionState.ADMITTED
    assert first.admission_id.endswith(first.result_digest)
    assert first.rejection_reasons == ()


def test_not_measurable_and_partial_are_distinct() -> None:
    not_measurable = _package(required=(MeasurementComponent.JOB_CONTEXT,))
    assert (
        evaluate_calculation_admission(not_measurable, _request()).state
        is AdmissionState.REJECTED_NOT_MEASURABLE
    )
    partial = _package(
        required=(
            MeasurementComponent.JOB_CONTEXT,
            MeasurementComponent.REVENUE_EARNED_VALUE,
        ),
        evidence=(_input(),),
    )
    assert (
        evaluate_calculation_admission(partial, _request()).state
        is AdmissionState.REJECTED_PARTIAL
    )


def test_conflicting_evidence_is_rejected() -> None:
    package = _package(
        required=(MeasurementComponent.JOB_CONTEXT,),
        evidence=(
            _input(value_digest="a" * 64),
            _input(identity="job-context-other", value_digest="b" * 64),
        ),
    )
    result = evaluate_calculation_admission(package, _request())
    assert result.state is AdmissionState.REJECTED_CONFLICTING
    assert "measurement_evidence_conflicting" in result.rejection_reasons


def test_unresolved_policy_is_rejected_without_resolving_it() -> None:
    policy = PolicyPrerequisite(
        dependency_id="revenue-recognition",
        component=MeasurementComponent.JOB_CONTEXT,
        state=PrerequisiteState.UNRESOLVED,
        authority="finance_owner_decision_required",
    )
    package = _package(
        required=(MeasurementComponent.JOB_CONTEXT,),
        evidence=(_input(),),
        policies=(policy,),
    )
    result = evaluate_calculation_admission(
        package,
        _request(required_policy_dependency_ids=("revenue-recognition",)),
    )
    assert result.state is AdmissionState.REJECTED_UNRESOLVED_POLICY
    assert result.unresolved_policy_ids == ("revenue-recognition",)


def test_tampered_package_is_integrity_rejected_not_raised() -> None:
    package = _package(
        required=(MeasurementComponent.JOB_CONTEXT,), evidence=(_input(),)
    )
    tampered = replace(package, package_digest="d" * 64)
    result = evaluate_calculation_admission(tampered, _request())
    assert result.state is AdmissionState.REJECTED_INTEGRITY
    assert "package_integrity_verification_failed" in result.rejection_reasons


def test_scope_and_company_branch_isolation_are_rejected() -> None:
    package = _package(
        required=(MeasurementComponent.JOB_CONTEXT,), evidence=(_input(),)
    )
    for request in (
        _request(company_id=UUID("00000000-0000-0000-0000-000000000099")),
        _request(branch_id=None),
        _request(subject_id="another-job"),
        _request(reconciliation_key="job:other"),
    ):
        assert (
            evaluate_calculation_admission(package, request).state
            is AdmissionState.REJECTED_SCOPE
        )


def test_qbo_and_public_hcp_unaccepted_authority_are_rejected() -> None:
    for authority in (
        "quickbooks_online_source_reported",
        "hcp_authoritative_operational_source",
    ):
        evidence = _input(
            authority=authority, accepted=False, state=FindingState.PARTIAL
        )
        package = _package(
            required=(MeasurementComponent.JOB_CONTEXT,), evidence=(evidence,)
        )
        request = _request(permitted_accepted_authorities=(authority,))
        result = evaluate_calculation_admission(package, request)
        assert result.state is AdmissionState.REJECTED_AUTHORITY
        assert result.authority_limitations == ("unaccepted:job-context",)


def test_disallowed_accepted_authority_is_rejected_without_precedence() -> None:
    package = _package(
        required=(MeasurementComponent.JOB_CONTEXT,), evidence=(_input(),)
    )
    result = evaluate_calculation_admission(
        package, _request(permitted_accepted_authorities=("another_authority",))
    )
    assert result.state is AdmissionState.REJECTED_AUTHORITY
    assert result.authority_limitations == (
        f"authority_not_permitted:{ACCEPTED_AUTHORITY}",
    )


def test_unsupported_definition_version_is_integrity_rejected() -> None:
    package = _package(
        required=(MeasurementComponent.JOB_CONTEXT,), evidence=(_input(),)
    )
    result = evaluate_calculation_admission(
        package, _request(supported_measurement_versions=("unsupported",))
    )
    assert result.state is AdmissionState.REJECTED_INTEGRITY
    assert "unsupported_definition_version" in result.rejection_reasons


def test_changed_package_changes_admission_identity() -> None:
    first_package = _package(
        required=(MeasurementComponent.JOB_CONTEXT,), evidence=(_input(),)
    )
    second_package = _package(
        required=(MeasurementComponent.JOB_CONTEXT,),
        evidence=(_input(value_digest="d" * 64),),
    )
    first = evaluate_calculation_admission(first_package, _request())
    second = evaluate_calculation_admission(second_package, _request())
    assert first.result_digest != second.result_digest
    assert first.package_digest != second.package_digest


def test_missing_required_policy_identity_is_rejected() -> None:
    package = _package(
        required=(MeasurementComponent.JOB_CONTEXT,), evidence=(_input(),)
    )
    result = evaluate_calculation_admission(
        package,
        _request(required_policy_dependency_ids=("material-costing",)),
    )
    assert result.state is AdmissionState.REJECTED_UNRESOLVED_POLICY
    assert result.unresolved_policy_ids == ("material-costing",)


def test_admission_contract_exposes_no_calculation_result() -> None:
    package = _package(
        required=(MeasurementComponent.JOB_CONTEXT,), evidence=(_input(),)
    )
    result = evaluate_calculation_admission(package, _request())
    assert not hasattr(result, "profit")
    assert not hasattr(result, "contribution")
    assert not hasattr(result, "margin")
