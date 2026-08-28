from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from uuid import UUID

from app.accounting.errors import AccountingConflict, AccountingValidation
from app.accounting_migration.native import OpeningReconciliation, ReconciliationState


class CandidateState(str, Enum):
    DRAFT = "DRAFT"
    INCOMPLETE = "INCOMPLETE"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    FINANCE_REVIEW_REQUIRED = "FINANCE_REVIEW_REQUIRED"
    OWNER_REVIEW_REQUIRED = "OWNER_REVIEW_REQUIRED"
    ACCEPTED_FOR_REHEARSAL = "ACCEPTED_FOR_REHEARSAL"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True, slots=True)
class CandidatePolicyReferences:
    opening_state_acceptance: str
    reconciliation_precedence: str
    retained_earnings_treatment: str
    opening_equity_treatment: str
    unresolved_ar_treatment: str
    unresolved_ap_treatment: str
    cash_bank_difference_treatment: str
    materiality: str
    cutover_date: str
    accounting_period: str
    currency: str


@dataclass(frozen=True, slots=True)
class CandidateMappingReferences:
    chart: str
    accounts: str
    accounts_receivable_control: str
    accounts_payable_control: str
    cash_bank: str


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    source_authority_classification: str
    source_package_identity: str
    source_evidence_digest: str
    custody_references: tuple[str, ...]
    reconciliation_package_digest: str
    unresolved_exception_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AccountingIntegrationCandidate:
    candidate_id: UUID
    version: int
    supersedes_candidate_id: UUID | None
    company_id: UUID
    branch_ids: tuple[UUID, ...]
    schema_version: str
    definition_version: str
    evidence: CandidateEvidence
    policies: CandidatePolicyReferences
    mappings: CandidateMappingReferences
    cutover_date: date
    period_id: UUID
    currency: str
    expected_debit_total: Decimal
    expected_credit_total: Decimal
    prepared_by_user_id: UUID
    reconciliation_approved_by_user_id: UUID
    created_at: datetime
    as_of: datetime
    state: CandidateState
    finance_approved_by_user_id: UUID | None
    owner_accepted_by_user_id: UUID | None
    canonical_package_digest: str

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(_candidate_payload(self, include_digest=False))


@dataclass(frozen=True, slots=True)
class RehearsalReadiness:
    eligible: bool
    state: CandidateState
    limitations: tuple[str, ...]
    candidate_digest: str
    authorization_granted: bool = False


def _normalize(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _candidate_payload(
    candidate: AccountingIntegrationCandidate, *, include_digest: bool
) -> dict[str, object]:
    payload = asdict(candidate)
    if not include_digest:
        payload.pop("canonical_package_digest")
    return payload


def _missing_references(
    policies: CandidatePolicyReferences,
    mappings: CandidateMappingReferences,
    evidence: CandidateEvidence,
) -> tuple[str, ...]:
    missing: list[str] = []
    for prefix, values in (
        ("policy", asdict(policies)),
        ("mapping", asdict(mappings)),
    ):
        missing.extend(
            f"{prefix}:{name}" for name, value in values.items() if not value.strip()
        )
    if not evidence.source_authority_classification.strip():
        missing.append("evidence:source_authority_classification")
    if not evidence.source_package_identity.strip():
        missing.append("evidence:source_package_identity")
    if not evidence.custody_references or any(
        not value.strip() for value in evidence.custody_references
    ):
        missing.append("evidence:custody_references")
    return tuple(sorted(missing))


class AccountingIntegrationCandidateService:
    """Create immutable, content-addressed candidates without executing Accounting."""

    SCHEMA_VERSION = "acc-ic-1/v1"

    @classmethod
    def create(
        cls,
        *,
        candidate_id: UUID,
        version: int,
        supersedes_candidate_id: UUID | None,
        reconciliation: OpeningReconciliation,
        evidence: CandidateEvidence,
        policies: CandidatePolicyReferences,
        mappings: CandidateMappingReferences,
        created_at: datetime,
        as_of: datetime,
    ) -> AccountingIntegrationCandidate:
        if version < 1 or (version == 1) == (supersedes_candidate_id is not None):
            raise AccountingValidation("Candidate version and lineage conflict")
        if created_at.tzinfo is None or as_of.tzinfo is None or as_of < created_at:
            raise AccountingValidation("Candidate timestamps are invalid")
        if evidence.reconciliation_package_digest != reconciliation.reconciliation_digest:
            raise AccountingConflict("Candidate reconciliation evidence is contradictory")
        if evidence.source_package_identity != reconciliation.package_id:
            raise AccountingConflict("Candidate source package identity is contradictory")
        if evidence.source_evidence_digest != reconciliation.canonical_package_digest:
            raise AccountingConflict("Candidate source evidence digest is contradictory")
        if policies.cutover_date != reconciliation.cutover_date.isoformat():
            raise AccountingConflict("Candidate cutover policy is contradictory")
        if policies.accounting_period != str(reconciliation.period_id):
            raise AccountingConflict("Candidate period policy is contradictory")
        if policies.currency != reconciliation.currency:
            raise AccountingConflict("Candidate currency policy is contradictory")

        debits = sum(
            (
                (line.actual_prepared_debit or Decimal(0))
                for line in reconciliation.lines
            ),
            start=Decimal(0),
        )
        credits = sum(
            (
                (line.actual_prepared_credit or Decimal(0))
                for line in reconciliation.lines
            ),
            start=Decimal(0),
        )
        if debits != credits or debits <= 0:
            raise AccountingConflict("Candidate opening totals are not balanced")
        missing = _missing_references(policies, mappings, evidence)
        if missing:
            state = CandidateState.INCOMPLETE
        elif reconciliation.state is not ReconciliationState.APPROVED_ELIGIBLE:
            state = CandidateState.RECONCILIATION_REQUIRED
        else:
            state = CandidateState.FINANCE_REVIEW_REQUIRED
        candidate = AccountingIntegrationCandidate(
            candidate_id=candidate_id,
            version=version,
            supersedes_candidate_id=supersedes_candidate_id,
            company_id=reconciliation.company_id,
            branch_ids=tuple(sorted(reconciliation.branch_ids, key=str)),
            schema_version=cls.SCHEMA_VERSION,
            definition_version=reconciliation.definition_version,
            evidence=evidence,
            policies=policies,
            mappings=mappings,
            cutover_date=reconciliation.cutover_date,
            period_id=reconciliation.period_id,
            currency=reconciliation.currency,
            expected_debit_total=debits,
            expected_credit_total=credits,
            prepared_by_user_id=reconciliation.prepared_by_user_id,
            reconciliation_approved_by_user_id=reconciliation.approved_by_user_id,
            created_at=created_at,
            as_of=as_of,
            state=state,
            finance_approved_by_user_id=None,
            owner_accepted_by_user_id=None,
            canonical_package_digest="",
        )
        return replace(candidate, canonical_package_digest=_digest(_candidate_payload(candidate, include_digest=False)))

    @staticmethod
    def finance_approve(
        candidate: AccountingIntegrationCandidate, *, actor_user_id: UUID
    ) -> AccountingIntegrationCandidate:
        if candidate.state is not CandidateState.FINANCE_REVIEW_REQUIRED:
            raise AccountingConflict("Candidate is not awaiting Finance review")
        if actor_user_id in {
            candidate.prepared_by_user_id,
            candidate.reconciliation_approved_by_user_id,
        }:
            raise AccountingConflict("Candidate Finance review violates separation of duties")
        return _redigest(
            replace(
                candidate,
                state=CandidateState.OWNER_REVIEW_REQUIRED,
                finance_approved_by_user_id=actor_user_id,
                canonical_package_digest="",
            )
        )

    @staticmethod
    def owner_accept(
        candidate: AccountingIntegrationCandidate, *, actor_user_id: UUID
    ) -> AccountingIntegrationCandidate:
        if candidate.state is not CandidateState.OWNER_REVIEW_REQUIRED:
            raise AccountingConflict("Candidate is not awaiting owner review")
        if actor_user_id in {
            candidate.prepared_by_user_id,
            candidate.reconciliation_approved_by_user_id,
            candidate.finance_approved_by_user_id,
        }:
            raise AccountingConflict("Candidate owner review violates separation of duties")
        return _redigest(
            replace(
                candidate,
                state=CandidateState.ACCEPTED_FOR_REHEARSAL,
                owner_accepted_by_user_id=actor_user_id,
                canonical_package_digest="",
            )
        )

    @staticmethod
    def reject(
        candidate: AccountingIntegrationCandidate, *, actor_user_id: UUID
    ) -> AccountingIntegrationCandidate:
        if candidate.state in {
            CandidateState.ACCEPTED_FOR_REHEARSAL,
            CandidateState.REJECTED,
            CandidateState.SUPERSEDED,
        }:
            raise AccountingConflict("Terminal candidate cannot be rejected in place")
        if actor_user_id == candidate.prepared_by_user_id:
            raise AccountingConflict("Candidate rejection requires independent review")
        return _redigest(
            replace(
                candidate,
                state=CandidateState.REJECTED,
                canonical_package_digest="",
            )
        )

    @staticmethod
    def readiness(candidate: AccountingIntegrationCandidate) -> RehearsalReadiness:
        limitations = _missing_references(
            candidate.policies, candidate.mappings, candidate.evidence
        )
        if candidate.state is not CandidateState.ACCEPTED_FOR_REHEARSAL:
            limitations = tuple(sorted((*limitations, f"state:{candidate.state.value}")))
        return RehearsalReadiness(
            eligible=not limitations,
            state=candidate.state,
            limitations=limitations,
            candidate_digest=candidate.canonical_package_digest,
        )

    @staticmethod
    def validate_acc_mig_compatibility(
        candidate: AccountingIntegrationCandidate,
        reconciliation: OpeningReconciliation,
    ) -> None:
        if (
            candidate.company_id != reconciliation.company_id
            or candidate.branch_ids != reconciliation.branch_ids
            or candidate.period_id != reconciliation.period_id
            or candidate.cutover_date != reconciliation.cutover_date
            or candidate.currency != reconciliation.currency
            or candidate.evidence.reconciliation_package_digest
            != reconciliation.reconciliation_digest
        ):
            raise AccountingConflict("Candidate is incompatible with ACC.MIG.1")


def _redigest(
    changed: AccountingIntegrationCandidate,
) -> AccountingIntegrationCandidate:
    return replace(
        changed,
        canonical_package_digest=_digest(_candidate_payload(changed, include_digest=False)),
    )


class InMemoryCandidateRegistry:
    """Test/reference registry; serialized candidates are the durable handoff unit."""

    def __init__(self) -> None:
        self._items: dict[UUID, AccountingIntegrationCandidate] = {}

    @property
    def items(self) -> Mapping[UUID, AccountingIntegrationCandidate]:
        return MappingProxyType(self._items)

    def record(
        self, candidate: AccountingIntegrationCandidate
    ) -> AccountingIntegrationCandidate:
        existing = self._items.get(candidate.candidate_id)
        if existing is not None:
            if existing.canonical_package_digest != candidate.canonical_package_digest:
                raise AccountingConflict("Candidate identity has contradictory evidence")
            return existing
        self._items[candidate.candidate_id] = candidate
        return candidate

    def supersede(
        self,
        prior_id: UUID,
        successor: AccountingIntegrationCandidate,
    ) -> tuple[AccountingIntegrationCandidate, AccountingIntegrationCandidate]:
        prior = self._items.get(prior_id)
        if prior is None or successor.supersedes_candidate_id != prior_id:
            raise AccountingConflict("Candidate supersession lineage is invalid")
        if successor.company_id != prior.company_id or successor.version != prior.version + 1:
            raise AccountingConflict("Candidate supersession scope or version is invalid")
        superseded = _redigest(
            replace(
                prior,
                state=CandidateState.SUPERSEDED,
                canonical_package_digest="",
            )
        )
        self._items[prior_id] = superseded
        return superseded, self.record(successor)
