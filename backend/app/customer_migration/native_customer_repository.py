"""Replay-safe persistence for native Customer consolidation evidence."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import CustomerIdentityConsolidationEvidence
from app.customer_migration.native_customer_consolidation import (
    CONSOLIDATION_CONTRACT_VERSION,
    NativeCustomerConsolidationResult,
)


@dataclass(frozen=True)
class CustomerConsolidationWrite:
    company_id: UUID
    branch_id: UUID
    evaluated_by_user_id: UUID
    source_system: str
    result: NativeCustomerConsolidationResult


class NativeCustomerConsolidationRepository:
    async def record(
        self, session: AsyncSession, *, evidence: CustomerConsolidationWrite
    ) -> tuple[CustomerIdentityConsolidationEvidence, bool]:
        existing = await session.scalar(
            select(CustomerIdentityConsolidationEvidence).where(
                CustomerIdentityConsolidationEvidence.company_id == evidence.company_id,
                CustomerIdentityConsolidationEvidence.branch_id == evidence.branch_id,
                CustomerIdentityConsolidationEvidence.source_system
                == evidence.source_system,
                CustomerIdentityConsolidationEvidence.source_identity_key
                == evidence.result.source_identity_key,
                CustomerIdentityConsolidationEvidence.evidence_digest
                == evidence.result.evidence_digest,
            )
        )
        if existing is not None:
            return existing, False
        record = CustomerIdentityConsolidationEvidence(
            company_id=evidence.company_id,
            branch_id=evidence.branch_id,
            customer_source_identity_id=evidence.result.customer_source_identity_id,
            customer_id=evidence.result.customer_id,
            evaluated_by_user_id=evidence.evaluated_by_user_id,
            source_system=evidence.source_system,
            source_entity_type="customer",
            source_identity_key=evidence.result.source_identity_key,
            source_customer_id_sha256=evidence.result.source_customer_id_sha256,
            consolidation_contract_version=CONSOLIDATION_CONTRACT_VERSION,
            outcome=evidence.result.outcome.value,
            observation_count=evidence.result.observation_count,
            input_digest=evidence.result.input_digest,
            evidence_digest=evidence.result.evidence_digest,
        )
        session.add(record)
        await session.flush()
        return record, True


native_customer_consolidation_repository = NativeCustomerConsolidationRepository()
