"""Persistence for immutable Customer Migration cutover-readiness evidence."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.cutover_readiness import (
    CUTOVER_READINESS_VERSION,
    CutoverReadiness,
)
from app.customer_migration.models import CustomerMigrationCutoverReadinessEvidence


@dataclass(frozen=True)
class CutoverReadinessWrite:
    company_id: UUID
    branch_id: UUID
    evaluated_by_user_id: UUID
    readiness: CutoverReadiness


class CutoverReadinessEvidenceRepository:
    async def record(
        self, session: AsyncSession, *, evidence: CutoverReadinessWrite
    ) -> tuple[CustomerMigrationCutoverReadinessEvidence, bool]:
        existing = await session.scalar(
            select(CustomerMigrationCutoverReadinessEvidence).where(
                CustomerMigrationCutoverReadinessEvidence.company_id
                == evidence.company_id,
                CustomerMigrationCutoverReadinessEvidence.branch_id
                == evidence.branch_id,
                CustomerMigrationCutoverReadinessEvidence.evidence_digest
                == evidence.readiness.evidence_digest,
            )
        )
        if existing is not None:
            return existing, False
        record = CustomerMigrationCutoverReadinessEvidence(
            id=evidence.readiness.readiness_id,
            company_id=evidence.company_id,
            branch_id=evidence.branch_id,
            evaluated_by_user_id=evidence.evaluated_by_user_id,
            readiness_key=evidence.readiness.readiness_key,
            contract_version=CUTOVER_READINESS_VERSION,
            status=evidence.readiness.status,
            ready=evidence.readiness.ready,
            completed_prerequisites=list(evidence.readiness.completed_prerequisites),
            missing_prerequisites=list(evidence.readiness.missing_prerequisites),
            blocking_conditions=list(evidence.readiness.blocking_conditions),
            owner_disposition_counts={
                item.category: item.count
                for item in evidence.readiness.unresolved_owner_dispositions
            },
            reconciliation_counts={
                item.category: item.count
                for item in evidence.readiness.unresolved_reconciliation_items
            },
            confidence_basis_points=evidence.readiness.confidence_basis_points,
            completeness_basis_points=evidence.readiness.completeness_basis_points,
            evidence_digest=evidence.readiness.evidence_digest,
        )
        session.add(record)
        await session.flush()
        return record, True


cutover_readiness_evidence_repository = CutoverReadinessEvidenceRepository()
