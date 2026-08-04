"""Append-only persistence for reconciled native location evidence."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import ServiceLocationIdentityEvidence
from app.customer_migration.native_location_identity import LocationIdentityResult


@dataclass(frozen=True)
class EvidenceWrite:
    company_id: UUID
    branch_id: UUID
    recorded_by_user_id: UUID
    customer_source_identity_id: UUID | None
    source_system: str
    source_artifact_sha256: str
    source_record_sha256: str
    address_evidence_sha256: str | None
    result: LocationIdentityResult
    prior_evidence_id: UUID | None = None


class NativeLocationEvidenceRepository:
    async def record(
        self, session: AsyncSession, *, evidence: EvidenceWrite
    ) -> tuple[ServiceLocationIdentityEvidence, bool]:
        """Return an exact replay or append a new attributed evidence version."""
        existing = await session.scalar(
            select(ServiceLocationIdentityEvidence).where(
                ServiceLocationIdentityEvidence.company_id == evidence.company_id,
                ServiceLocationIdentityEvidence.source_system == evidence.source_system,
                ServiceLocationIdentityEvidence.observation_sha256
                == evidence.result.observation_sha256,
                ServiceLocationIdentityEvidence.evidence_digest
                == evidence.result.evidence_digest,
            )
        )
        if existing is not None:
            return existing, False

        version = 1
        if evidence.prior_evidence_id is not None:
            prior = await session.scalar(
                select(ServiceLocationIdentityEvidence).where(
                    ServiceLocationIdentityEvidence.id == evidence.prior_evidence_id,
                    ServiceLocationIdentityEvidence.company_id == evidence.company_id,
                )
            )
            if prior is None:
                raise ValueError(
                    "prior location identity evidence is outside Company scope"
                )
            if prior.observation_sha256 != evidence.result.observation_sha256:
                raise ValueError(
                    "identity correction must retain the observation identity"
                )
            version = prior.evidence_version + 1

        record = ServiceLocationIdentityEvidence(
            company_id=evidence.company_id,
            branch_id=evidence.branch_id,
            customer_source_identity_id=evidence.customer_source_identity_id,
            prior_evidence_id=evidence.prior_evidence_id,
            recorded_by_user_id=evidence.recorded_by_user_id,
            source_system=evidence.source_system,
            source_entity_type="service_location",
            observation_sha256=evidence.result.observation_sha256,
            source_location_id_sha256=evidence.result.source_location_id_sha256,
            source_customer_id_sha256=evidence.result.source_customer_id_sha256,
            source_artifact_sha256=evidence.source_artifact_sha256,
            source_record_sha256=evidence.source_record_sha256,
            address_evidence_sha256=evidence.address_evidence_sha256,
            classification=evidence.result.classification.value,
            readiness=evidence.result.readiness,
            evidence_digest=evidence.result.evidence_digest,
            evidence_version=version,
        )
        session.add(record)
        await session.flush()
        return record, True


native_location_evidence_repository = NativeLocationEvidenceRepository()
