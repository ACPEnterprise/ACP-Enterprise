"""Append-only persistence for evidence acceptance and gap-closure records."""

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from .evidence_acceptance import (
    EvidenceAcceptanceContract,
    EvidenceAcceptanceGrant,
    GapClosure,
)
from .models import (
    EvidenceAcceptanceContractRecord,
    EvidenceAcceptanceGrantRecord,
    PolicyGapClosureRecord,
)


async def persist_acceptance_contracts(
    session: AsyncSession, contracts: Iterable[EvidenceAcceptanceContract]
) -> None:
    """Append immutable contract definitions; database uniqueness rejects rewrites."""
    for contract in contracts:
        session.add(
            EvidenceAcceptanceContractRecord(
                contract_id=contract.contract_id,
                contract_version=contract.version,
                family_key=contract.family_key,
                gap_key=contract.gap_key,
                definition={
                    "required_facts": list(contract.required_facts),
                    "permitted_authorities": list(contract.permitted_authorities),
                    "prohibited_evidence_roles": list(
                        contract.prohibited_evidence_roles
                    ),
                    "provisional_allowed": contract.provisional_allowed,
                },
                contract_digest=contract.contract_digest,
            )
        )
    await session.flush()


async def persist_acceptance_grant(
    session: AsyncSession, grant: EvidenceAcceptanceGrant
) -> None:
    """Persist an explicit approval without persisting source values."""
    grant.verify()
    session.add(
        EvidenceAcceptanceGrantRecord(
            grant_id=grant.grant_id,
            company_id=grant.company_id,
            branch_id=grant.branch_id,
            subject_id=grant.subject_id,
            contract_id=grant.contract_id,
            contract_version=grant.contract_version,
            evidence_id=grant.evidence_id,
            evidence_digest=grant.evidence_digest,
            authority=grant.authority,
            effective_start=grant.effective_start,
            effective_end=grant.effective_end,
            approved_by_user_id=grant.approved_by_user_id,
            approved_at=grant.approved_at,
            grant_digest=grant.grant_digest,
        )
    )
    await session.flush()


async def persist_gap_closure(session: AsyncSession, closure: GapClosure) -> None:
    """Persist one immutable observation; supersession appends another observation."""
    closure.verify()
    session.add(
        PolicyGapClosureRecord(
            company_id=closure.company_id,
            branch_id=closure.branch_id,
            gap_id=closure.gap_id,
            subject_id=closure.subject_id,
            reconciliation_key=closure.reconciliation_key,
            contract_id=closure.contract_id,
            contract_version=closure.contract_version,
            state=closure.state.value,
            evidence_ids=list(closure.evidence_ids),
            evidence_digests=list(closure.evidence_digests),
            authorities=list(closure.authorities),
            effective_date=closure.effective_date,
            as_of=closure.as_of,
            provisional=closure.provisional,
            limitations=list(closure.limitations),
            supersedes_closure_id=closure.supersedes_closure_id,
            closure_digest=closure.closure_digest,
        )
    )
    await session.flush()
