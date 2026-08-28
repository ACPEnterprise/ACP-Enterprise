"""Versioned evidence acceptance and deterministic policy-gap closure."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from .policy_authority import PolicyIntegrityError, PolicyParameterGap, canonical_digest

ACCEPTANCE_DEFINITION_VERSION = "eco.evidence-acceptance.v1"
GAP_CLOSURE_VERSION = "eco.gap-closure.v1"


class GapLifecycleState(StrEnum):
    OPEN = "open"
    SATISFIED = "satisfied"
    CONFLICTING = "conflicting"
    SUPERSEDED = "superseded"


class GapAssessmentClass(StrEnum):
    SATISFIABLE_NOW = "satisfiable_now"
    UPSTREAM_CONTRACT_REQUIRED = "upstream_contract_required"
    FINANCE_PARAMETER_REQUIRED = "finance_parameter_required"
    EXTERNAL_RECONCILIATION_REQUIRED = "external_reconciliation_required"


@dataclass(frozen=True)
class EvidenceAcceptanceContract:
    contract_id: str
    version: str
    gap_key: str
    family_key: str
    required_facts: tuple[str, ...]
    permitted_authorities: tuple[str, ...]
    prohibited_evidence_roles: tuple[str, ...]
    provisional_allowed: bool = False

    @property
    def contract_digest(self) -> str:
        return canonical_digest(
            {
                "contract_id": self.contract_id,
                "version": self.version,
                "gap_key": self.gap_key,
                "family_key": self.family_key,
                "required_facts": self.required_facts,
                "permitted_authorities": self.permitted_authorities,
                "prohibited_evidence_roles": self.prohibited_evidence_roles,
                "provisional_allowed": self.provisional_allowed,
            }
        )


@dataclass(frozen=True)
class EconomicEvidenceAssertion:
    evidence_id: str
    company_id: UUID
    branch_id: UUID | None
    subject_id: str
    reconciliation_key: str
    evidence_type: str
    source_authority: str
    effective_date: date
    as_of: datetime
    facts: Mapping[str, object]
    evidence_digest: str
    value_digest: str
    provisional: bool = False


@dataclass(frozen=True)
class EvidenceAcceptanceGrant:
    grant_id: str
    company_id: UUID
    branch_id: UUID | None
    subject_id: str
    contract_id: str
    contract_version: str
    evidence_id: str
    evidence_digest: str
    authority: str
    effective_start: date
    effective_end: date | None
    approved_by_user_id: UUID
    approved_at: datetime
    grant_digest: str

    def verify(self) -> None:
        expected = canonical_digest(self.canonical_content())
        if expected != self.grant_digest:
            raise PolicyIntegrityError("evidence acceptance grant digest mismatch")

    def canonical_content(self) -> dict[str, object]:
        return {
            "grant_id": self.grant_id,
            "company_id": str(self.company_id),
            "branch_id": str(self.branch_id) if self.branch_id else None,
            "subject_id": self.subject_id,
            "contract_id": self.contract_id,
            "contract_version": self.contract_version,
            "evidence_id": self.evidence_id,
            "evidence_digest": self.evidence_digest,
            "authority": self.authority,
            "effective_start": self.effective_start.isoformat(),
            "effective_end": self.effective_end.isoformat()
            if self.effective_end
            else None,
            "approved_by_user_id": str(self.approved_by_user_id),
            "approved_at": self.approved_at.isoformat(),
        }


def seal_acceptance_grant(
    *,
    grant_id: str,
    company_id: UUID,
    branch_id: UUID | None,
    subject_id: str,
    contract_id: str,
    contract_version: str,
    evidence_id: str,
    evidence_digest: str,
    authority: str,
    effective_start: date,
    effective_end: date | None,
    approved_by_user_id: UUID,
    approved_at: datetime,
) -> EvidenceAcceptanceGrant:
    draft = EvidenceAcceptanceGrant(
        grant_id=grant_id,
        company_id=company_id,
        branch_id=branch_id,
        subject_id=subject_id,
        contract_id=contract_id,
        contract_version=contract_version,
        evidence_id=evidence_id,
        evidence_digest=evidence_digest,
        authority=authority,
        effective_start=effective_start,
        effective_end=effective_end,
        approved_by_user_id=approved_by_user_id,
        approved_at=approved_at,
        grant_digest="",
    )
    return replace(draft, grant_digest=canonical_digest(draft.canonical_content()))


@dataclass(frozen=True)
class GapClosure:
    closure_id: str
    gap_id: UUID
    company_id: UUID
    branch_id: UUID | None
    subject_id: str
    reconciliation_key: str
    contract_id: str
    contract_version: str
    state: GapLifecycleState
    evidence_ids: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    authorities: tuple[str, ...]
    effective_date: date
    as_of: datetime
    provisional: bool
    limitations: tuple[str, ...]
    supersedes_closure_id: str | None
    closure_digest: str

    def verify(self) -> None:
        if self.closure_id != f"eco-gap-closure:{self.closure_digest}":
            raise PolicyIntegrityError("gap closure identity mismatch")
        if self.closure_digest != canonical_digest(self.canonical_content()):
            raise PolicyIntegrityError("gap closure digest mismatch")

    def canonical_content(self) -> dict[str, object]:
        return {
            "version": GAP_CLOSURE_VERSION,
            "gap_id": str(self.gap_id),
            "company_id": str(self.company_id),
            "branch_id": str(self.branch_id) if self.branch_id else None,
            "subject_id": self.subject_id,
            "reconciliation_key": self.reconciliation_key,
            "contract_id": self.contract_id,
            "contract_version": self.contract_version,
            "state": self.state.value,
            "evidence_ids": self.evidence_ids,
            "evidence_digests": self.evidence_digests,
            "authorities": self.authorities,
            "effective_date": self.effective_date.isoformat(),
            "as_of": self.as_of.isoformat(),
            "provisional": self.provisional,
            "limitations": self.limitations,
            "supersedes_closure_id": self.supersedes_closure_id,
        }


@dataclass(frozen=True)
class GapClosureSnapshot:
    company_id: UUID
    branch_id: UUID | None
    subject_id: str
    reconciliation_key: str
    as_of: datetime
    closures: tuple[GapClosure, ...]
    snapshot_digest: str

    def verify(self) -> None:
        for closure in self.closures:
            closure.verify()
            if (
                closure.company_id != self.company_id
                or closure.branch_id != self.branch_id
                or closure.subject_id != self.subject_id
                or closure.reconciliation_key != self.reconciliation_key
            ):
                raise PolicyIntegrityError("gap closure snapshot scope mismatch")
        expected = canonical_digest(
            {
                "company_id": str(self.company_id),
                "branch_id": str(self.branch_id) if self.branch_id else None,
                "subject_id": self.subject_id,
                "reconciliation_key": self.reconciliation_key,
                "as_of": self.as_of.isoformat(),
                "closure_digests": tuple(
                    sorted(item.closure_digest for item in self.closures)
                ),
            }
        )
        if expected != self.snapshot_digest:
            raise PolicyIntegrityError("gap closure snapshot digest mismatch")


def evaluate_gap_closure(
    *,
    gap: PolicyParameterGap,
    contract: EvidenceAcceptanceContract,
    assertions: Sequence[EconomicEvidenceAssertion],
    grants: Sequence[EvidenceAcceptanceGrant],
    subject_id: str,
    reconciliation_key: str,
    effective_date: date,
    as_of: datetime,
    supersedes_closure_id: str | None = None,
) -> GapClosure:
    gap.validate()
    if contract.gap_key != gap.gap_key or contract.family_key != gap.family_key:
        raise PolicyIntegrityError("acceptance contract does not govern gap")
    accepted: list[EconomicEvidenceAssertion] = []
    limitations: set[str] = set()
    grants_by_evidence = {grant.evidence_id: grant for grant in grants}
    for assertion in assertions:
        grant = grants_by_evidence.get(assertion.evidence_id)
        if not _assertion_qualifies(
            gap, contract, assertion, grant, subject_id, effective_date, as_of
        ):
            continue
        if assertion.reconciliation_key != reconciliation_key:
            continue
        accepted.append(assertion)
        if assertion.provisional:
            limitations.add("UNREVIEWED / PROVISIONAL")
    state = GapLifecycleState.OPEN
    if accepted:
        state = (
            GapLifecycleState.CONFLICTING
            if len({item.value_digest for item in accepted}) > 1
            else GapLifecycleState.SATISFIED
        )
    evidence_ids = tuple(sorted(item.evidence_id for item in accepted))
    evidence_digests = tuple(sorted(item.evidence_digest for item in accepted))
    authorities = tuple(sorted({item.source_authority for item in accepted}))
    provisional = any(item.provisional for item in accepted)
    ordered_limitations = tuple(sorted(limitations))
    canonical = {
        "version": GAP_CLOSURE_VERSION,
        "gap_id": str(gap.gap_id),
        "company_id": str(gap.company_id),
        "branch_id": None,
        "subject_id": subject_id,
        "reconciliation_key": reconciliation_key,
        "contract_id": contract.contract_id,
        "contract_version": contract.version,
        "state": state.value,
        "evidence_ids": evidence_ids,
        "evidence_digests": evidence_digests,
        "authorities": authorities,
        "effective_date": effective_date.isoformat(),
        "as_of": as_of.isoformat(),
        "provisional": provisional,
        "limitations": ordered_limitations,
        "supersedes_closure_id": supersedes_closure_id,
    }
    digest = canonical_digest(canonical)
    result = GapClosure(
        closure_id=f"eco-gap-closure:{digest}",
        gap_id=gap.gap_id,
        company_id=gap.company_id,
        branch_id=None,
        subject_id=subject_id,
        reconciliation_key=reconciliation_key,
        contract_id=contract.contract_id,
        contract_version=contract.version,
        state=state,
        evidence_ids=evidence_ids,
        evidence_digests=evidence_digests,
        authorities=authorities,
        effective_date=effective_date,
        as_of=as_of,
        provisional=provisional,
        limitations=ordered_limitations,
        supersedes_closure_id=supersedes_closure_id,
        closure_digest=digest,
    )
    result.verify()
    return result


def _assertion_qualifies(
    gap: PolicyParameterGap,
    contract: EvidenceAcceptanceContract,
    assertion: EconomicEvidenceAssertion,
    grant: EvidenceAcceptanceGrant | None,
    subject_id: str,
    effective_date: date,
    as_of: datetime,
) -> bool:
    if grant is None:
        return False
    grant.verify()
    return (
        assertion.company_id == gap.company_id == grant.company_id
        and assertion.branch_id == gap.branch_id == grant.branch_id
        and assertion.subject_id == subject_id == grant.subject_id
        and assertion.evidence_id == grant.evidence_id
        and assertion.evidence_digest == grant.evidence_digest
        and assertion.source_authority == grant.authority
        and assertion.source_authority in contract.permitted_authorities
        and assertion.evidence_type not in contract.prohibited_evidence_roles
        and contract.contract_id == grant.contract_id
        and contract.version == grant.contract_version
        and grant.effective_start <= effective_date
        and (grant.effective_end is None or effective_date < grant.effective_end)
        and assertion.effective_date <= effective_date
        and assertion.as_of <= as_of
        and grant.approved_at <= as_of
        and set(contract.required_facts) <= set(assertion.facts)
        and (not assertion.provisional or contract.provisional_allowed)
    )


def build_gap_closure_snapshot(
    *,
    company_id: UUID,
    branch_id: UUID | None,
    subject_id: str,
    reconciliation_key: str,
    as_of: datetime,
    closures: Sequence[GapClosure],
) -> GapClosureSnapshot:
    ordered = tuple(sorted(closures, key=lambda item: str(item.gap_id)))
    canonical = {
        "company_id": str(company_id),
        "branch_id": str(branch_id) if branch_id else None,
        "subject_id": subject_id,
        "reconciliation_key": reconciliation_key,
        "as_of": as_of.isoformat(),
        "closure_digests": tuple(sorted(item.closure_digest for item in ordered)),
    }
    snapshot = GapClosureSnapshot(
        company_id,
        branch_id,
        subject_id,
        reconciliation_key,
        as_of,
        ordered,
        canonical_digest(canonical),
    )
    snapshot.verify()
    return snapshot


def supersede_gap_closure(prior: GapClosure, *, as_of: datetime) -> GapClosure:
    """Append a supersession observation without mutating the prior closure."""
    prior.verify()
    canonical = {
        **prior.canonical_content(),
        "state": GapLifecycleState.SUPERSEDED.value,
        "as_of": as_of.isoformat(),
        "supersedes_closure_id": prior.closure_id,
    }
    digest = canonical_digest(canonical)
    result = GapClosure(
        closure_id=f"eco-gap-closure:{digest}",
        gap_id=prior.gap_id,
        company_id=prior.company_id,
        branch_id=prior.branch_id,
        subject_id=prior.subject_id,
        reconciliation_key=prior.reconciliation_key,
        contract_id=prior.contract_id,
        contract_version=prior.contract_version,
        state=GapLifecycleState.SUPERSEDED,
        evidence_ids=prior.evidence_ids,
        evidence_digests=prior.evidence_digests,
        authorities=prior.authorities,
        effective_date=prior.effective_date,
        as_of=as_of,
        provisional=prior.provisional,
        limitations=prior.limitations,
        supersedes_closure_id=prior.closure_id,
        closure_digest=digest,
    )
    result.verify()
    return result
