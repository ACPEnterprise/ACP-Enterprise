from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from app.business_economics.findings import SubjectKind
from app.business_economics.measurement_admission import (
    AdmissionState,
    CalculationAdmissionRequest,
    evaluate_calculation_admission,
)
from app.business_economics.measurement_contract import (
    MeasurementComponent,
    PrerequisiteState,
    evaluate_contribution_measurement_gate,
)
from app.business_economics.measurement_package import (
    MEASUREMENT_PACKAGE_VERSION,
    seal_measurement_readiness_package,
)
from app.business_economics.policy_authority import (
    POLICY_DEFINITION_VERSION,
    CompanyPolicyVersion,
    PolicyDisposition,
    PolicyLifecycle,
    PolicyResolutionState,
    build_policy_snapshot,
    resolve_policy_authority,
    seal_policy,
    seal_policy_parameter,
)
from app.business_economics.policy_measurement_bridge import (
    policy_snapshot_to_prerequisites,
)

NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)


def _policy(
    company: UUID,
    family: str,
    strategy: str | None,
    *,
    deferred: bool = False,
    parameters: dict[str, object] | None = None,
) -> CompanyPolicyVersion:
    return seal_policy(
        policy_id=uuid4(),
        company_id=company,
        branch_id=None,
        family_key=family,
        policy_version=1,
        disposition=PolicyDisposition.DEFERRED
        if deferred
        else PolicyDisposition.SELECTED,
        strategy_key=None if deferred else strategy,
        parameters={} if deferred else (parameters or {}),
        evidence_acceptance_rule_refs=("separate-evidence-acceptance:v1",),
        effective_start=date(2026, 1, 1),
        effective_end=None,
        lifecycle=PolicyLifecycle.APPROVED,
        definition_version=POLICY_DEFINITION_VERSION,
        approved_by_user_id=uuid4(),
        approved_at=NOW,
        decision_evidence_digest="a" * 64,
        supersedes_policy_id=None,
    )


def _all_county_shape(company: UUID) -> list[CompanyPolicyVersion]:
    selected = {
        "job_lifecycle_cutoff": "completed_only",
        "revenue_recognition": "accepted_earned_value_at_completion",
        "direct_labor_measurement": "approved_actual_job_time",
        "labor_burden": "standard_by_worker_class",
        "direct_material_costing": "accepted_inventory_issue_layers",
        "other_attributable_direct_costs": "category_inclusion_exclusion",
        "reconciliation_source_precedence": "reject_conflicting_component",
        "accounting_reconciliation_admission": "integrity_reconciled_provisional",
    }
    policies = [
        _policy(company, family, strategy) for family, strategy in selected.items()
    ]
    policies.extend(
        _policy(company, family, None, deferred=True)
        for family in (
            "payment_settlement_acceptance",
            "overhead_pool_definitions",
            "overhead_allocation",
            "monetary_materiality",
        )
    )
    return policies


def test_all_county_choices_and_explicit_deferrals_are_representable_only_as_synthetic_configuration() -> (
    None
):
    company = uuid4()
    policies = _all_county_shape(company)
    snapshot = build_policy_snapshot(
        policies,
        company_id=company,
        branch_id=None,
        subject_identity="job:synthetic",
        reconciliation_key="job:synthetic",
        as_of=date(2026, 8, 28),
        required_families=tuple(policy.family_key for policy in policies),
    )
    assert set(snapshot.deferred_family_keys) == {
        "payment_settlement_acceptance",
        "overhead_pool_definitions",
        "overhead_allocation",
        "monetary_materiality",
    }
    prerequisites = policy_snapshot_to_prerequisites(snapshot)
    assert (
        next(
            item
            for item in prerequisites
            if item.dependency_id == "payment_settlement_acceptance"
        ).state
        is PrerequisiteState.UNRESOLVED
    )
    assert (
        next(
            item for item in prerequisites if item.dependency_id == "labor_burden"
        ).state
        is PrerequisiteState.UNRESOLVED
    )


def test_second_company_can_select_cash_behavior_without_cross_company_effect() -> None:
    first, second = uuid4(), uuid4()
    policies = [
        _policy(first, "revenue_recognition", "accepted_earned_value_at_completion"),
        _policy(second, "revenue_recognition", "cash_settlement"),
    ]
    one = resolve_policy_authority(
        policies,
        company_id=first,
        family_key="revenue_recognition",
        as_of=date(2026, 8, 28),
    )
    two = resolve_policy_authority(
        policies,
        company_id=second,
        family_key="revenue_recognition",
        as_of=date(2026, 8, 28),
    )
    assert one.state is two.state is PolicyResolutionState.APPROVED
    assert (
        one.policy is not None
        and one.policy.strategy_key == "accepted_earned_value_at_completion"
    )
    assert two.policy is not None and two.policy.strategy_key == "cash_settlement"


def test_deferred_snapshot_blocks_readiness_package_and_admission_without_calculation() -> (
    None
):
    company = uuid4()
    policy = _policy(company, "revenue_recognition", None, deferred=True)
    snapshot = build_policy_snapshot(
        [policy],
        company_id=company,
        branch_id=None,
        subject_identity="job:synthetic",
        reconciliation_key="job:synthetic",
        as_of=date(2026, 8, 28),
        required_families=("revenue_recognition",),
    )
    prerequisites = policy_snapshot_to_prerequisites(snapshot)
    gate = evaluate_contribution_measurement_gate(
        subject_id="job:synthetic",
        subject_kind=SubjectKind.JOB,
        reconciliation_key="job:synthetic",
        required_components=(MeasurementComponent.REVENUE_EARNED_VALUE,),
        evidence=(),
        findings=(),
        policy_dependencies=prerequisites,
    )
    package = seal_measurement_readiness_package(
        company_id=company, branch_id=None, gate=gate, findings=()
    )
    result = evaluate_calculation_admission(
        package,
        CalculationAdmissionRequest(
            company_id=company,
            branch_id=None,
            subject_id="job:synthetic",
            subject_kind=SubjectKind.JOB,
            reconciliation_key="job:synthetic",
            supported_package_versions=(MEASUREMENT_PACKAGE_VERSION,),
            supported_measurement_versions=(gate.definition_version,),
            permitted_accepted_authorities=(),
            required_policy_dependency_ids=("revenue_recognition",),
        ),
    )
    assert result.state is AdmissionState.REJECTED_UNRESOLVED_POLICY


def test_effective_dated_typed_parameter_is_versioned_and_tamper_evident() -> None:
    parameter = seal_policy_parameter(
        parameter_id=uuid4(),
        company_id=uuid4(),
        branch_id=None,
        family_key="labor_burden",
        parameter_key="worker_class_rate_table_ref",
        parameter_version=1,
        value="synthetic-rate-table:v1",
        effective_start=date(2026, 1, 1),
        effective_end=date(2027, 1, 1),
        approved_by_user_id=uuid4(),
        approved_at=NOW,
        definition_version=POLICY_DEFINITION_VERSION,
    )
    parameter.validate()
    assert parameter.parameter_digest
