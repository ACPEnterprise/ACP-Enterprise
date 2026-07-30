from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import (
    CustomerMigrationCandidate,
    CustomerMigrationProgress,
    CustomerMigrationRun,
    CustomerMigrationSourceArtifact,
    CustomerMigrationSourceRow,
    CustomerSourceIdentity,
)
from app.customers.models import Customer, CustomerContact, ServiceLocation
from app.platform.permissions.authorization import AuthorizationContext


class CustomerAdapterImportRepository:
    @staticmethod
    async def find_staged_artifact(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        source_system: str,
        source_sha256: str,
    ) -> CustomerMigrationSourceArtifact | None:
        assert context.active_branch is not None
        return await session.scalar(
            select(CustomerMigrationSourceArtifact).where(
                CustomerMigrationSourceArtifact.company_id == context.company.id,
                CustomerMigrationSourceArtifact.branch_id == context.active_branch.id,
                CustomerMigrationSourceArtifact.source_system == source_system,
                CustomerMigrationSourceArtifact.source_sha256 == source_sha256,
            )
        )

    @staticmethod
    async def find_staged_row(
        session: AsyncSession,
        *,
        artifact_id: UUID,
        source_identity_sha256: str,
        source_row_sha256: str,
    ) -> CustomerMigrationSourceRow | None:
        return await session.scalar(
            select(CustomerMigrationSourceRow).where(
                CustomerMigrationSourceRow.artifact_id == artifact_id,
                CustomerMigrationSourceRow.source_id_sha256 == source_identity_sha256,
                CustomerMigrationSourceRow.source_row_sha256 == source_row_sha256,
                CustomerMigrationSourceRow.disposition == "accepted",
            )
        )

    @staticmethod
    async def list_staged_candidates(
        session: AsyncSession, *, source_row_id: UUID
    ) -> tuple[CustomerMigrationCandidate, ...]:
        return tuple(
            (
                await session.scalars(
                    select(CustomerMigrationCandidate).where(
                        CustomerMigrationCandidate.source_row_id == source_row_id
                    )
                )
            ).all()
        )

    @staticmethod
    async def find_source_identity(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        source_system: str,
        source_identity: str,
    ) -> CustomerSourceIdentity | None:
        return await session.scalar(
            select(CustomerSourceIdentity).where(
                CustomerSourceIdentity.company_id == context.company.id,
                CustomerSourceIdentity.source_system == source_system,
                CustomerSourceIdentity.source_customer_id == source_identity,
            )
        )

    @staticmethod
    async def count_supplied_identity_matches(
        session: AsyncSession,
        *,
        company_id: UUID,
        normalized_name: str,
        normalized_emails: tuple[str, ...],
        normalized_phones: tuple[str, ...],
        normalized_address: str | None,
    ) -> int:
        identity_filters = [Customer.normalized_name == normalized_name]
        contact_signals = [
            CustomerContact.normalized_email.in_(normalized_emails),
            CustomerContact.normalized_mobile_phone.in_(normalized_phones),
            CustomerContact.normalized_office_phone.in_(normalized_phones),
        ]
        if normalized_emails or normalized_phones:
            identity_filters.append(
                Customer.id.in_(
                    select(CustomerContact.customer_id).where(or_(*contact_signals))
                )
            )
        if normalized_address is not None:
            identity_filters.append(
                Customer.id.in_(
                    select(ServiceLocation.customer_id).where(
                        ServiceLocation.normalized_address == normalized_address
                    )
                )
            )
        count = await session.scalar(
            select(func.count())
            .select_from(Customer)
            .where(
                Customer.company_id == company_id,
                Customer.archived_at.is_(None),
                or_(*identity_filters),
            )
        )
        return int(count or 0)

    @staticmethod
    async def lock_run_progress(
        session: AsyncSession, *, run_id: UUID
    ) -> tuple[CustomerMigrationRun, CustomerMigrationProgress]:
        run = await session.get(CustomerMigrationRun, run_id, with_for_update=True)
        progress = await session.scalar(
            select(CustomerMigrationProgress)
            .where(
                CustomerMigrationProgress.run_id == run_id,
                CustomerMigrationProgress.entity_type == "customer",
            )
            .with_for_update()
        )
        if run is None or progress is None:
            raise RuntimeError("Customer adapter import progress disappeared")
        return run, progress
