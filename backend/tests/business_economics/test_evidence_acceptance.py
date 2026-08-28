from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from app.business_economics.company_policy_configurations.all_county_evidence_v1 import (
    ALL_COUNTY_EVIDENCE_CONTRACTS,
    ALL_COUNTY_GAP_ASSESSMENT,
)
from app.business_economics.company_policy_configurations.all_county_v1 import (
    build_all_county_policy_v1,
)
from app.business_economics.evidence_acceptance import (
    EconomicEvidenceAssertion,
    GapAssessmentClass,
    GapLifecycleState,
    build_gap_closure_snapshot,
    evaluate_gap_closure,
    seal_acceptance_grant,
    supersede_gap_closure,
)
from app.business_economics.evidence_acceptance_repository import (
    persist_acceptance_contracts,
    persist_acceptance_grant,
    persist_gap_closure,
)
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
    MeasurementGateState,
    PrerequisiteState,
    evaluate_contribution_measurement_gate,
)
from app.business_economics.measurement_package import (
    MEASUREMENT_PACKAGE_VERSION,
    seal_measurement_readiness_package,
)
from app.business_economics.policy_measurement_bridge import (
    policy_and_evidence_snapshot_to_prerequisites,
)
from app.business_economics.source_conformance import EvidenceConfidence

COMPANY = UUID("50000000-0000-0000-0000-000000000001")
OWNER = UUID("50000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)
SUBJECT = "job:synthetic-accepted"
RECONCILIATION = "job:synthetic-accepted"


def _bundle():
    return build_all_county_policy_v1(
        company_id=COMPANY, approver_user_id=OWNER, approved_at=NOW
    )


def _gap(key: str):
    return next(item for item in _bundle().parameter_gaps if item.gap_key == key)


def _assertion(
    gap_key: str,
    *,
    evidence_id: str | None = None,
    authority: str | None = None,
    evidence_type: str = "accepted_domain_fact",
    value_digest: str = "b" * 64,
    provisional: bool = False,
) -> EconomicEvidenceAssertion:
    contract = ALL_COUNTY_EVIDENCE_CONTRACTS[gap_key]
    return EconomicEvidenceAssertion(
        evidence_id=evidence_id or f"evidence:{gap_key}",
        company_id=COMPANY,
        branch_id=None,
        subject_id=SUBJECT,
        reconciliation_key=RECONCILIATION,
        evidence_type=evidence_type,
        source_authority=authority or contract.permitted_authorities[0],
        effective_date=date(2026, 8, 27),
        as_of=NOW,
        facts={key: f"synthetic:{key}" for key in contract.required_facts},
        evidence_digest="a" * 64,
        value_digest=value_digest,
        provisional=provisional,
    )


def _grant(assertion: EconomicEvidenceAssertion, gap_key: str):
    contract = ALL_COUNTY_EVIDENCE_CONTRACTS[gap_key]
    return seal_acceptance_grant(
        grant_id=f"grant:{assertion.evidence_id}",
        company_id=COMPANY,
        branch_id=None,
        subject_id=SUBJECT,
        contract_id=contract.contract_id,
        contract_version=contract.version,
        evidence_id=assertion.evidence_id,
        evidence_digest=assertion.evidence_digest,
        authority=assertion.source_authority,
        effective_start=date(2026, 8, 27),
        effective_end=None,
        approved_by_user_id=OWNER,
        approved_at=NOW,
    )


def _closure(gap_key: str, assertions=(), grants=()):
    return evaluate_gap_closure(
        gap=_gap(gap_key),
        contract=ALL_COUNTY_EVIDENCE_CONTRACTS[gap_key],
        assertions=assertions,
        grants=grants,
        subject_id=SUBJECT,
        reconciliation_key=RECONCILIATION,
        effective_date=date(2026, 8, 27),
        as_of=NOW,
    )


def test_policy_or_unaccepted_evidence_alone_leaves_gap_open() -> None:
    assertion = _assertion("accepted_earned_job_value")
    assert _closure("accepted_earned_job_value").state is GapLifecycleState.OPEN
    assert (
        _closure("accepted_earned_job_value", (assertion,), ()).state
        is GapLifecycleState.OPEN
    )


def test_exact_granted_evidence_closes_only_intended_gap() -> None:
    assertion = _assertion("accepted_earned_job_value")
    closure = _closure(
        "accepted_earned_job_value",
        (assertion,),
        (_grant(assertion, "accepted_earned_job_value"),),
    )
    assert closure.state is GapLifecycleState.SATISFIED
    assert closure.gap_id == _gap("accepted_earned_job_value").gap_id
    assert (
        _closure(
            "revenue_corrections",
            (assertion,),
            (_grant(assertion, "accepted_earned_job_value"),),
        ).state
        is GapLifecycleState.OPEN
    )


def test_wrong_company_period_and_convenient_source_roles_fail_closed() -> None:
    scheduled = _assertion(
        "approved_actual_job_time",
        evidence_type="appointment_scheduled_duration",
    )
    qbo = _assertion(
        "accepted_earned_job_value",
        authority="quickbooks_online_source_reported",
        evidence_type="qbo_source_reported",
    )
    purchase = _assertion(
        "job_linked_inventory_issues",
        authority="acp_inventory_material_issue",
        evidence_type="purchase",
    )
    for gap_key, assertion in (
        ("approved_actual_job_time", scheduled),
        ("accepted_earned_job_value", qbo),
        ("job_linked_inventory_issues", purchase),
    ):
        assert (
            _closure(gap_key, (assertion,), (_grant(assertion, gap_key),)).state
            is GapLifecycleState.OPEN
        )
    accepted = _assertion("accepted_earned_job_value")
    wrong_company = replace(
        accepted, company_id=UUID("50000000-0000-0000-0000-000000000099")
    )
    too_late = replace(accepted, effective_date=date(2026, 8, 28))
    assert (
        _closure(
            "accepted_earned_job_value",
            (wrong_company,),
            (_grant(accepted, "accepted_earned_job_value"),),
        ).state
        is GapLifecycleState.OPEN
    )
    assert (
        _closure(
            "accepted_earned_job_value",
            (too_late,),
            (_grant(accepted, "accepted_earned_job_value"),),
        ).state
        is GapLifecycleState.OPEN
    )


def test_conflict_changed_evidence_and_supersession_are_tamper_evident() -> None:
    one = _assertion(
        "accepted_earned_job_value", evidence_id="evidence:one", value_digest="b" * 64
    )
    two = _assertion(
        "accepted_earned_job_value", evidence_id="evidence:two", value_digest="c" * 64
    )
    conflict = _closure(
        "accepted_earned_job_value",
        (one, two),
        (
            _grant(one, "accepted_earned_job_value"),
            _grant(two, "accepted_earned_job_value"),
        ),
    )
    assert conflict.state is GapLifecycleState.CONFLICTING
    satisfied = _closure(
        "accepted_earned_job_value", (one,), (_grant(one, "accepted_earned_job_value"),)
    )
    assert conflict.closure_digest != satisfied.closure_digest
    superseded = supersede_gap_closure(satisfied, as_of=NOW.replace(hour=16))
    assert superseded.state is GapLifecycleState.SUPERSEDED
    assert superseded.supersedes_closure_id == satisfied.closure_id
    satisfied.verify()


def test_provisional_accounting_remains_explicitly_labeled() -> None:
    assertion = _assertion("accounting_integrity", provisional=True)
    closure = _closure(
        "accounting_integrity",
        (assertion,),
        (_grant(assertion, "accounting_integrity"),),
    )
    assert closure.state is GapLifecycleState.SATISFIED
    assert closure.provisional
    assert closure.limitations == ("UNREVIEWED / PROVISIONAL",)

    accounting_keys = tuple(
        key
        for key, contract in ALL_COUNTY_EVIDENCE_CONTRACTS.items()
        if contract.family_key == "accounting_reconciliation_admission"
    )
    closures = []
    for key in accounting_keys:
        item = _assertion(key, provisional=True)
        closures.append(_closure(key, (item,), (_grant(item, key),)))
    snapshot = build_gap_closure_snapshot(
        company_id=COMPANY,
        branch_id=None,
        subject_id=SUBJECT,
        reconciliation_key=RECONCILIATION,
        as_of=NOW,
        closures=closures,
    )
    prerequisite = next(
        item
        for item in policy_and_evidence_snapshot_to_prerequisites(
            _bundle().snapshot, snapshot
        )
        if item.dependency_id == "accounting_reconciliation_admission"
    )
    assert prerequisite.state is PrerequisiteState.RESOLVED
    assert prerequisite.authority.endswith("UNREVIEWED_PROVISIONAL")


def test_conflicting_required_evidence_blocks_policy_prerequisite() -> None:
    one = _assertion("accepted_earned_job_value", evidence_id="conflict:one")
    two = _assertion(
        "accepted_earned_job_value", evidence_id="conflict:two", value_digest="c" * 64
    )
    correction = _assertion("revenue_corrections")
    closures = (
        _closure(
            "accepted_earned_job_value",
            (one, two),
            (
                _grant(one, "accepted_earned_job_value"),
                _grant(two, "accepted_earned_job_value"),
            ),
        ),
        _closure(
            "revenue_corrections",
            (correction,),
            (_grant(correction, "revenue_corrections"),),
        ),
    )
    snapshot = build_gap_closure_snapshot(
        company_id=COMPANY,
        branch_id=None,
        subject_id=SUBJECT,
        reconciliation_key=RECONCILIATION,
        as_of=NOW,
        closures=closures,
    )
    prerequisite = next(
        item
        for item in policy_and_evidence_snapshot_to_prerequisites(
            _bundle().snapshot, snapshot
        )
        if item.dependency_id == "revenue_recognition"
    )
    assert prerequisite.state is PrerequisiteState.UNRESOLVED


class _RecordingSession:
    def __init__(self) -> None:
        self.records: list[object] = []
        self.flush_count = 0

    def add(self, value: object) -> None:
        self.records.append(value)

    async def flush(self) -> None:
        self.flush_count += 1


@pytest.mark.asyncio
async def test_repository_appends_contract_grant_and_closure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.business_economics.evidence_acceptance_repository.EvidenceAcceptanceContractRecord",
        lambda **values: ("contract", values),
    )
    monkeypatch.setattr(
        "app.business_economics.evidence_acceptance_repository.EvidenceAcceptanceGrantRecord",
        lambda **values: ("grant", values),
    )
    monkeypatch.setattr(
        "app.business_economics.evidence_acceptance_repository.PolicyGapClosureRecord",
        lambda **values: ("closure", values),
    )
    assertion = _assertion("accepted_earned_job_value")
    grant = _grant(assertion, "accepted_earned_job_value")
    closure = _closure("accepted_earned_job_value", (assertion,), (grant,))
    session = _RecordingSession()
    await persist_acceptance_contracts(  # type: ignore[arg-type]
        session, (ALL_COUNTY_EVIDENCE_CONTRACTS["accepted_earned_job_value"],)
    )
    await persist_acceptance_grant(session, grant)  # type: ignore[arg-type]
    await persist_gap_closure(session, closure)  # type: ignore[arg-type]
    assert [item[0] for item in session.records] == ["contract", "grant", "closure"]  # type: ignore[index]
    assert session.flush_count == 3


def test_all_25_gaps_are_classified_without_fabricated_satisfaction() -> None:
    assert len(ALL_COUNTY_EVIDENCE_CONTRACTS) == 25
    assert set(ALL_COUNTY_GAP_ASSESSMENT) == set(ALL_COUNTY_EVIDENCE_CONTRACTS)
    assert set(ALL_COUNTY_GAP_ASSESSMENT.values()) == set(GapAssessmentClass)


def test_synthetic_accepted_evidence_reaches_admission_without_calculation() -> None:
    bundle = _bundle()
    revenue_gap_keys = ("accepted_earned_job_value", "revenue_corrections")
    closures = []
    for key in revenue_gap_keys:
        assertion = _assertion(key)
        closures.append(_closure(key, (assertion,), (_grant(assertion, key),)))
    snapshot = build_gap_closure_snapshot(
        company_id=COMPANY,
        branch_id=None,
        subject_id=SUBJECT,
        reconciliation_key=RECONCILIATION,
        as_of=NOW,
        closures=closures,
    )
    prerequisites = policy_and_evidence_snapshot_to_prerequisites(
        bundle.snapshot, snapshot
    )
    revenue_policy = next(
        item for item in prerequisites if item.dependency_id == "revenue_recognition"
    )
    assert revenue_policy.state is PrerequisiteState.RESOLVED
    evidence = MeasurementEvidenceInput(
        input_id="accepted-earned-value",
        company_id=COMPANY,
        branch_id=None,
        subject_id=SUBJECT,
        reconciliation_key=RECONCILIATION,
        component=MeasurementComponent.REVENUE_EARNED_VALUE,
        source_authority="acp_finance_accepted_earned_value",
        evidence_state=FindingState.READY,
        confidence=EvidenceConfidence.AVAILABLE,
        source_value=Decimal("100.00"),
        currency="USD",
        unit=None,
        effective_date=date(2026, 8, 27),
        as_of=NOW,
        accepted_for_measurement=True,
        limitations=(),
        evidence_digest="a" * 64,
        value_digest="b" * 64,
        package_digest="c" * 64,
    )
    gate = evaluate_contribution_measurement_gate(
        subject_id=SUBJECT,
        subject_kind=SubjectKind.JOB,
        reconciliation_key=RECONCILIATION,
        required_components=(MeasurementComponent.REVENUE_EARNED_VALUE,),
        evidence=(evidence,),
        findings=(),
        policy_dependencies=(revenue_policy,),
    )
    assert gate.state is MeasurementGateState.MEASURABLE
    package = seal_measurement_readiness_package(
        company_id=COMPANY, branch_id=None, gate=gate, findings=()
    )
    admission = evaluate_calculation_admission(
        package,
        CalculationAdmissionRequest(
            company_id=COMPANY,
            branch_id=None,
            subject_id=SUBJECT,
            subject_kind=SubjectKind.JOB,
            reconciliation_key=RECONCILIATION,
            supported_package_versions=(MEASUREMENT_PACKAGE_VERSION,),
            supported_measurement_versions=(MEASUREMENT_DEFINITION_VERSION,),
            permitted_accepted_authorities=("acp_finance_accepted_earned_value",),
            required_policy_dependency_ids=("revenue_recognition",),
        ),
    )
    assert admission.state is AdmissionState.ADMITTED
