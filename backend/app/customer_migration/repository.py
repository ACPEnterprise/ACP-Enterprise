from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import (
    CustomerMigrationCandidate,
    CustomerMigrationChildException,
    CustomerMigrationEvidence,
    CustomerMigrationSourceArtifact,
    CustomerMigrationSourceRow,
    CustomerMigrationStagingRun,
)


class CustomerMigrationStagingRepository:
    async def find_artifact(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        source_system: str,
        source_sha256: str,
    ) -> CustomerMigrationSourceArtifact | None:
        return await session.scalar(
            select(CustomerMigrationSourceArtifact).where(
                CustomerMigrationSourceArtifact.company_id == company_id,
                CustomerMigrationSourceArtifact.branch_id == branch_id,
                CustomerMigrationSourceArtifact.source_system == source_system,
                CustomerMigrationSourceArtifact.source_sha256 == source_sha256,
            )
        )

    @staticmethod
    def add_artifact(
        session: AsyncSession, artifact: CustomerMigrationSourceArtifact
    ) -> None:
        session.add(artifact)

    @staticmethod
    def add_source_row(
        session: AsyncSession, source_row: CustomerMigrationSourceRow
    ) -> None:
        session.add(source_row)

    @staticmethod
    def add_candidate(
        session: AsyncSession, candidate: CustomerMigrationCandidate
    ) -> None:
        session.add(candidate)

    @staticmethod
    def add_evidence(
        session: AsyncSession, evidence: CustomerMigrationEvidence
    ) -> None:
        session.add(evidence)

    @staticmethod
    def add_child_exception(
        session: AsyncSession, exception: CustomerMigrationChildException
    ) -> None:
        session.add(exception)

    @staticmethod
    def add_staging_run(
        session: AsyncSession, staging_run: CustomerMigrationStagingRun
    ) -> None:
        session.add(staging_run)
