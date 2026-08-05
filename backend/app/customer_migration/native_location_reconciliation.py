"""Durable replay-safe persistence for native location reconciliation."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import ServiceLocationReconciliationEvidence
from app.customer_migration.native_location_matching import (
    MATCHING_CONTRACT_VERSION,
    NativeLocationMatchResult,
)


@dataclass(frozen=True)
class ReconciliationWrite:
    company_id: UUID
    branch_id: UUID
    evaluated_by_user_id: UUID
    result: NativeLocationMatchResult


class NativeLocationReconciliationRepository:
    async def record(
        self, session: AsyncSession, *, evidence: ReconciliationWrite
    ) -> tuple[ServiceLocationReconciliationEvidence, bool]:
        existing = await session.scalar(
            select(ServiceLocationReconciliationEvidence).where(
                ServiceLocationReconciliationEvidence.company_id == evidence.company_id,
                ServiceLocationReconciliationEvidence.identity_evidence_id
                == evidence.result.identity_evidence_id,
                ServiceLocationReconciliationEvidence.evidence_digest
                == evidence.result.evidence_digest,
            )
        )
        if existing is not None:
            return existing, False
        record = ServiceLocationReconciliationEvidence(
            company_id=evidence.company_id,
            branch_id=evidence.branch_id,
            identity_evidence_id=evidence.result.identity_evidence_id,
            service_location_id=evidence.result.service_location_id,
            customer_id=evidence.result.customer_id,
            evaluated_by_user_id=evidence.evaluated_by_user_id,
            matching_contract_version=MATCHING_CONTRACT_VERSION,
            outcome=evidence.result.outcome.value,
            candidate_count=evidence.result.candidate_count,
            input_digest=evidence.result.input_digest,
            evidence_digest=evidence.result.evidence_digest,
        )
        session.add(record)
        await session.flush()
        return record, True


native_location_reconciliation_repository = NativeLocationReconciliationRepository()
