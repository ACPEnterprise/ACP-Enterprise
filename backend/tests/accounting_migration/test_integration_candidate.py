from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.accounting.errors import AccountingConflict
from app.accounting_migration import (
    AccountingIntegrationCandidateService,
    CandidateEvidence,
    CandidateMappingReferences,
    CandidatePolicyReferences,
    CandidateState,
    InMemoryCandidateRegistry,
    OpeningComponent,
    OpeningReconciliation,
    OpeningReconciliationLine,
    ReconciliationState,
)

COMPANY_ID = UUID("00000000-0000-4000-8000-000000000101")
BRANCH_ID = UUID("00000000-0000-4000-8000-000000000102")
PERIOD_ID = UUID("00000000-0000-4000-8000-000000000103")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000104")
PREPARER_ID = UUID("00000000-0000-4000-8000-000000000105")
APPROVER_ID = UUID("00000000-0000-4000-8000-000000000106")
CREATED_AT = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)


def _line(*, debit: Decimal = Decimal(0), credit: Decimal = Decimal(0)) -> OpeningReconciliationLine:
    return OpeningReconciliationLine(
        source_identity="synthetic-account",
        source_authority_classification="SYNTHETIC ACCEPTED EVIDENCE",
        source_evidence_digest="1" * 64,
        reconciliation_identity="2" * 64,
        imported_value_digest="3" * 64,
        target_account_id=ACCOUNT_ID,
        target_branch_id=BRANCH_ID,
        component=OpeningComponent.OTHER_BALANCE_SHEET,
        expected_debit=debit,
        expected_credit=credit,
        actual_prepared_debit=debit,
        actual_prepared_credit=credit,
        difference=Decimal(0),
        state=ReconciliationState.RECONCILED,
        limitations=(),
        source_artifact_id="synthetic-trial-balance",
        source_row=1,
    )


def _reconciliation() -> OpeningReconciliation:
    return OpeningReconciliation(
        package_id="00000000-0000-4000-8000-000000000099",
        canonical_package_digest="4" * 64,
        imported_value_digest="5" * 64,
        reconciliation_identity="6" * 64,
        reconciliation_digest="7" * 64,
        definition_version="acc-mig-1/v1",
        transformation_version="synthetic/v1",
        company_id=COMPANY_ID,
        branch_ids=(BRANCH_ID,),
        period_id=PERIOD_ID,
        cutover_date=date(2030, 1, 1),
        currency="USD",
        state=ReconciliationState.APPROVED_ELIGIBLE,
        eligible_for_posting=True,
        lines=(_line(debit=Decimal("100.00")), _line(credit=Decimal("100.00"))),
        limitations=(),
        prepared_by_user_id=PREPARER_ID,
        approved_by_user_id=APPROVER_ID,
        approval_evidence_digest="8" * 64,
        policy_digest="9" * 64,
    )


def _evidence(reconciliation: OpeningReconciliation) -> CandidateEvidence:
    return CandidateEvidence(
        source_authority_classification="PROVIDER_NEUTRAL_RECONCILED_SOURCE",
        source_package_identity=reconciliation.package_id,
        source_evidence_digest=reconciliation.canonical_package_digest,
        custody_references=("custody:synthetic-package:1",),
        reconciliation_package_digest=reconciliation.reconciliation_digest,
        unresolved_exception_references=(),
    )


def _policies() -> CandidatePolicyReferences:
    return CandidatePolicyReferences(
        opening_state_acceptance="finance:opening:1",
        reconciliation_precedence="finance:precedence:1",
        retained_earnings_treatment="finance:retained:1",
        opening_equity_treatment="finance:equity:1",
        unresolved_ar_treatment="finance:ar:1",
        unresolved_ap_treatment="finance:ap:1",
        cash_bank_difference_treatment="finance:cash:1",
        materiality="finance:materiality:1",
        cutover_date="2030-01-01",
        accounting_period=str(PERIOD_ID),
        currency="USD",
    )


def _mappings() -> CandidateMappingReferences:
    return CandidateMappingReferences(
        chart="mapping:chart:1",
        accounts="mapping:accounts:1",
        accounts_receivable_control="mapping:ar:1",
        accounts_payable_control="mapping:ap:1",
        cash_bank="mapping:cash:1",
    )


def _candidate(*, candidate_id: UUID | None = None, version: int = 1, supersedes: UUID | None = None):
    reconciliation = _reconciliation()
    return AccountingIntegrationCandidateService.create(
        candidate_id=candidate_id or uuid4(),
        version=version,
        supersedes_candidate_id=supersedes,
        reconciliation=reconciliation,
        evidence=_evidence(reconciliation),
        policies=_policies(),
        mappings=_mappings(),
        created_at=CREATED_AT,
        as_of=CREATED_AT,
    )


def test_serialization_and_digest_are_deterministic_and_materially_bound() -> None:
    identity = uuid4()
    first = _candidate(candidate_id=identity)
    second = _candidate(candidate_id=identity)
    assert first == second
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.canonical_package_digest == second.canonical_package_digest

    changed = replace(first, mappings=replace(first.mappings, accounts="mapping:accounts:2"))
    rebuilt = AccountingIntegrationCandidateService.create(
        candidate_id=changed.candidate_id,
        version=1,
        supersedes_candidate_id=None,
        reconciliation=_reconciliation(),
        evidence=changed.evidence,
        policies=changed.policies,
        mappings=changed.mappings,
        created_at=changed.created_at,
        as_of=changed.as_of,
    )
    assert rebuilt.canonical_package_digest != first.canonical_package_digest


def test_incomplete_and_reconciliation_gates_never_imply_acceptance() -> None:
    reconciliation = _reconciliation()
    incomplete = AccountingIntegrationCandidateService.create(
        candidate_id=uuid4(), version=1, supersedes_candidate_id=None,
        reconciliation=reconciliation, evidence=_evidence(reconciliation),
        policies=replace(_policies(), materiality=""), mappings=_mappings(),
        created_at=CREATED_AT, as_of=CREATED_AT,
    )
    assert incomplete.state is CandidateState.INCOMPLETE
    assert not AccountingIntegrationCandidateService.readiness(incomplete).eligible

    required = AccountingIntegrationCandidateService.create(
        candidate_id=uuid4(), version=1, supersedes_candidate_id=None,
        reconciliation=replace(
            reconciliation,
            state=ReconciliationState.PARTIALLY_RECONCILED,
            eligible_for_posting=False,
        ),
        evidence=_evidence(reconciliation), policies=_policies(), mappings=_mappings(),
        created_at=CREATED_AT, as_of=CREATED_AT,
    )
    assert required.state is CandidateState.RECONCILIATION_REQUIRED


def test_finance_owner_lifecycle_and_sod_are_explicit() -> None:
    candidate = _candidate()
    assert candidate.state is CandidateState.FINANCE_REVIEW_REQUIRED
    with pytest.raises(AccountingConflict, match="separation"):
        AccountingIntegrationCandidateService.finance_approve(
            candidate, actor_user_id=candidate.prepared_by_user_id
        )
    finance_actor = uuid4()
    reviewed = AccountingIntegrationCandidateService.finance_approve(
        candidate, actor_user_id=finance_actor
    )
    assert reviewed.state is CandidateState.OWNER_REVIEW_REQUIRED
    accepted = AccountingIntegrationCandidateService.owner_accept(
        reviewed, actor_user_id=uuid4()
    )
    readiness = AccountingIntegrationCandidateService.readiness(accepted)
    assert accepted.state is CandidateState.ACCEPTED_FOR_REHEARSAL
    assert readiness.eligible
    assert not readiness.authorization_granted
    with pytest.raises(FrozenInstanceError):
        accepted.state = CandidateState.REJECTED  # type: ignore[misc]


def test_rejection_is_terminal_and_digest_bound() -> None:
    candidate = _candidate()
    rejected = AccountingIntegrationCandidateService.reject(
        candidate, actor_user_id=uuid4()
    )
    assert rejected.state is CandidateState.REJECTED
    assert rejected.canonical_package_digest != candidate.canonical_package_digest
    with pytest.raises(AccountingConflict, match="Terminal"):
        AccountingIntegrationCandidateService.reject(
            rejected, actor_user_id=uuid4()
        )


def test_registry_is_idempotent_contradiction_safe_and_preserves_lineage() -> None:
    registry = InMemoryCandidateRegistry()
    prior = _candidate()
    assert registry.record(prior) is registry.record(prior)
    with pytest.raises(AccountingConflict, match="contradictory"):
        registry.record(replace(prior, canonical_package_digest="f" * 64))

    successor = _candidate(
        candidate_id=uuid4(), version=2, supersedes=prior.candidate_id
    )
    superseded, recorded = registry.supersede(prior.candidate_id, successor)
    assert superseded.state is CandidateState.SUPERSEDED
    assert recorded.supersedes_candidate_id == prior.candidate_id
    assert registry.items[prior.candidate_id].canonical_package_digest == superseded.canonical_package_digest


def test_custody_scope_and_acc_mig_compatibility_are_preserved() -> None:
    reconciliation = _reconciliation()
    candidate = AccountingIntegrationCandidateService.create(
        candidate_id=uuid4(), version=1, supersedes_candidate_id=None,
        reconciliation=reconciliation, evidence=_evidence(reconciliation),
        policies=_policies(), mappings=_mappings(), created_at=CREATED_AT, as_of=CREATED_AT,
    )
    assert candidate.evidence.custody_references == ("custody:synthetic-package:1",)
    AccountingIntegrationCandidateService.validate_acc_mig_compatibility(
        candidate, reconciliation
    )
    with pytest.raises(AccountingConflict, match="ACC.MIG.1"):
        AccountingIntegrationCandidateService.validate_acc_mig_compatibility(
            candidate, replace(reconciliation, company_id=uuid4())
        )


def test_contradictory_source_evidence_fails_closed_without_journal_side_effect() -> None:
    reconciliation = _reconciliation()
    with pytest.raises(AccountingConflict, match="evidence"):
        AccountingIntegrationCandidateService.create(
            candidate_id=uuid4(), version=1, supersedes_candidate_id=None,
            reconciliation=reconciliation,
            evidence=replace(_evidence(reconciliation), reconciliation_package_digest="0" * 64),
            policies=_policies(), mappings=_mappings(), created_at=CREATED_AT, as_of=CREATED_AT,
        )
