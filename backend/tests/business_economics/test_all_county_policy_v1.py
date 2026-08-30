from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.business_economics.company_policy_configurations.all_county_v1 import (
    CONFIGURATION_ID,
    DEFERRED_FAMILIES,
    EFFECTIVE_START,
    METRIC_NAME,
    SELECTED_STRATEGIES,
    build_all_county_policy_v1,
)
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
    PolicyDisposition,
    PolicyResolutionState,
    resolve_policy_authority,
)
from app.business_economics.policy_measurement_bridge import (
    policy_snapshot_to_prerequisites,
)
from app.business_economics.policy_repository import persist_all_county_policy_v1

COMPANY = UUID("10000000-0000-0000-0000-000000000001")
OWNER = UUID("10000000-0000-0000-0000-000000000002")
APPROVED_AT = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _bundle(company: UUID = COMPANY):
    return build_all_county_policy_v1(
        company_id=company, approver_user_id=OWNER, approved_at=APPROVED_AT
    )


def test_all_county_v1_seals_eight_selected_and_four_deferred_company_policies() -> (
    None
):
    bundle = _bundle()
    assert bundle.configuration_id == CONFIGURATION_ID
    assert bundle.effective_start == EFFECTIVE_START
    assert bundle.metric.display_name == METRIC_NAME
    assert len(bundle.policies) == 12
    assert {
        item.family_key: item.strategy_key
        for item in bundle.policies
        if item.disposition is PolicyDisposition.SELECTED
    } == dict(SELECTED_STRATEGIES)
    assert {
        item.family_key
        for item in bundle.policies
        if item.disposition is PolicyDisposition.DEFERRED
    } == set(DEFERRED_FAMILIES)
    assert all(item.company_id == COMPANY for item in bundle.policies)
    assert all(item.policy_version == 1 for item in bundle.policies)
    assert all(item.approved_by_user_id == OWNER for item in bundle.policies)


def test_all_parameter_and_authority_gaps_are_durable_unvalued_and_snapshot_bound() -> (
    None
):
    bundle = _bundle()
    required = {
        "accepted_earned_job_value",
        "approved_actual_job_time",
        "technician_participation_identity",
        "worker_class_definitions",
        "worker_class_assignments",
        "standard_burden_rates",
        "burden_true_up",
        "job_linked_inventory_issues",
        "inventory_cost_layers",
        "direct_cost_categories",
        "direct_cost_job_linkage",
        "conflict_identity",
        "conflict_exclusion",
        "accounting_completeness",
        "accounting_freshness",
        "accounting_reconciliation",
        "accounting_integrity",
        "provisional_review_label",
    }
    assert required <= {gap.gap_key for gap in bundle.parameter_gaps}
    assert all("value" not in gap.canonical_content() for gap in bundle.parameter_gaps)
    assert len(bundle.snapshot.parameter_gaps) == len(bundle.parameter_gaps)
    bundle.snapshot.verify()


def test_bundle_and_snapshot_are_deterministic_and_future_policy_cannot_rewrite_snapshot() -> (
    None
):
    first = _bundle()
    second = _bundle()
    assert first.decision_digest == second.decision_digest
    assert first.snapshot.snapshot_digest == second.snapshot.snapshot_digest
    historical_digest = first.snapshot.snapshot_digest
    other = _bundle(UUID("20000000-0000-0000-0000-000000000001"))
    assert other.snapshot.snapshot_digest != historical_digest
    assert first.snapshot.snapshot_digest == historical_digest


def test_every_selected_policy_remains_blocked_by_explicit_gap_and_deferral_is_visible() -> (
    None
):
    bundle = _bundle()
    prerequisites = policy_snapshot_to_prerequisites(bundle.snapshot)
    by_family = {item.dependency_id: item for item in prerequisites}
    for family in SELECTED_STRATEGIES:
        if family in by_family:
            assert by_family[family].state is PrerequisiteState.UNRESOLVED
    for family in DEFERRED_FAMILIES:
        if family in by_family:
            assert by_family[family].state is PrerequisiteState.UNRESOLVED


def test_measurement_package_and_admission_explain_fail_closed_policy_state() -> None:
    bundle = _bundle()
    prerequisites = policy_snapshot_to_prerequisites(bundle.snapshot)
    required_components = (
        MeasurementComponent.JOB_CONTEXT,
        MeasurementComponent.REVENUE_EARNED_VALUE,
        MeasurementComponent.DIRECT_LABOR,
        MeasurementComponent.LABOR_BURDEN,
        MeasurementComponent.DIRECT_MATERIAL,
        MeasurementComponent.OTHER_DIRECT_COST,
        MeasurementComponent.ACCOUNTING_RECONCILIATION,
    )
    gate = evaluate_contribution_measurement_gate(
        subject_id="job:qualification-only",
        subject_kind=SubjectKind.JOB,
        reconciliation_key="job:qualification-only",
        required_components=required_components,
        evidence=(),
        findings=(),
        policy_dependencies=prerequisites,
    )
    package = seal_measurement_readiness_package(
        company_id=COMPANY, branch_id=None, gate=gate, findings=()
    )
    result = evaluate_calculation_admission(
        package,
        CalculationAdmissionRequest(
            company_id=COMPANY,
            branch_id=None,
            subject_id="job:qualification-only",
            subject_kind=SubjectKind.JOB,
            reconciliation_key="job:qualification-only",
            supported_package_versions=(MEASUREMENT_PACKAGE_VERSION,),
            supported_measurement_versions=(gate.definition_version,),
            permitted_accepted_authorities=(),
            required_policy_dependency_ids=tuple(
                item.dependency_id for item in prerequisites
            ),
        ),
    )
    assert result.state is AdmissionState.REJECTED_UNRESOLVED_POLICY
    assert "revenue_recognition" in result.unresolved_policy_ids
    assert "labor_burden" in result.unresolved_policy_ids


def test_other_company_and_branch_resolution_remain_isolated_and_fail_closed() -> None:
    bundle = _bundle()
    other = resolve_policy_authority(
        bundle.policies,
        company_id=UUID("30000000-0000-0000-0000-000000000001"),
        family_key="revenue_recognition",
        as_of=EFFECTIVE_START,
    )
    branch = resolve_policy_authority(
        bundle.policies,
        company_id=COMPANY,
        branch_id=UUID("40000000-0000-0000-0000-000000000001"),
        family_key="revenue_recognition",
        as_of=EFFECTIVE_START,
    )
    assert other.state is PolicyResolutionState.UNRESOLVED
    assert branch.state is PolicyResolutionState.CONFLICT


class _RecordingSession:
    def __init__(self) -> None:
        self.records: list[object] = []
        self.flushed = False

    def add(self, record: object) -> None:
        self.records.append(record)

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_repository_persists_only_explicit_bundle_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.business_economics.policy_repository.CompanyFinancePolicyVersion",
        lambda **values: ("policy", values),
    )
    monkeypatch.setattr(
        "app.business_economics.policy_repository.CompanyFinancePolicyGap",
        lambda **values: ("gap", values),
    )
    monkeypatch.setattr(
        "app.business_economics.policy_repository.FinancePolicySnapshotRecord",
        lambda **values: ("snapshot", values),
    )
    session = _RecordingSession()
    await persist_all_county_policy_v1(session, _bundle())  # type: ignore[arg-type]
    assert session.flushed
    tagged = [item for item in session.records if isinstance(item, tuple)]
    assert sum(item[0] == "policy" for item in tagged) == 12
    assert sum(item[0] == "gap" for item in tagged) > 0
    assert sum(item[0] == "snapshot" for item in tagged) == 1
