from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import (
    CustomerSourceIdentity,
    ServiceLocationSourceIdentity,
)
from app.jobs.models import Job
from app.operational_migration.models import (
    AppointmentSourceIdentity,
    JobSourceIdentity,
    OperationalMigrationException,
    OperationalMigrationProgress,
    OperationalMigrationRun,
)


class OperationalMigrationRepository:
    """Own provider-neutral migration-control persistence and lookups."""

    @staticmethod
    async def create_run(
        session: AsyncSession, run: OperationalMigrationRun
    ) -> OperationalMigrationRun:
        session.add(run)
        await session.flush()
        return run

    @staticmethod
    async def get_run_for_update(
        session: AsyncSession, run_id: UUID
    ) -> OperationalMigrationRun | None:
        return await session.get(OperationalMigrationRun, run_id, with_for_update=True)

    @staticmethod
    async def get_customer_identity(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        source_system: str,
        source_customer_id: str,
    ) -> CustomerSourceIdentity | None:
        return await session.scalar(
            select(CustomerSourceIdentity).where(
                CustomerSourceIdentity.company_id == company_id,
                CustomerSourceIdentity.branch_id == branch_id,
                CustomerSourceIdentity.source_system == source_system,
                CustomerSourceIdentity.source_customer_id == source_customer_id,
            )
        )

    @staticmethod
    async def get_location_identity(
        session: AsyncSession,
        *,
        company_id: UUID,
        customer_source_identity_id: UUID,
        source_system: str,
        source_location_id: str,
    ) -> ServiceLocationSourceIdentity | None:
        return await session.scalar(
            select(ServiceLocationSourceIdentity).where(
                ServiceLocationSourceIdentity.company_id == company_id,
                ServiceLocationSourceIdentity.customer_source_identity_id
                == customer_source_identity_id,
                ServiceLocationSourceIdentity.source_system == source_system,
                ServiceLocationSourceIdentity.source_location_id == source_location_id,
            )
        )

    @staticmethod
    async def get_job_identity(
        session: AsyncSession,
        *,
        company_id: UUID,
        source_system: str,
        source_job_id: str,
    ) -> JobSourceIdentity | None:
        return await session.scalar(
            select(JobSourceIdentity).where(
                JobSourceIdentity.company_id == company_id,
                JobSourceIdentity.source_system == source_system,
                JobSourceIdentity.source_job_id == source_job_id,
            )
        )

    @staticmethod
    async def count_source_job_number(
        session: AsyncSession,
        *,
        company_id: UUID,
        source_system: str,
        source_job_number: str,
    ) -> int:
        value = await session.scalar(
            select(func.count())
            .select_from(JobSourceIdentity)
            .where(
                JobSourceIdentity.company_id == company_id,
                JobSourceIdentity.source_system == source_system,
                JobSourceIdentity.source_job_number == source_job_number,
            )
        )
        return int(value or 0)

    @staticmethod
    async def get_appointment_identity(
        session: AsyncSession,
        *,
        company_id: UUID,
        source_system: str,
        source_appointment_id: str,
    ) -> AppointmentSourceIdentity | None:
        return await session.scalar(
            select(AppointmentSourceIdentity).where(
                AppointmentSourceIdentity.company_id == company_id,
                AppointmentSourceIdentity.source_system == source_system,
                AppointmentSourceIdentity.source_appointment_id
                == source_appointment_id,
            )
        )

    @staticmethod
    async def get_job(session: AsyncSession, job_id: UUID) -> Job | None:
        return await session.get(Job, job_id)

    @staticmethod
    def add_job_identity(session: AsyncSession, identity: JobSourceIdentity) -> None:
        session.add(identity)

    @staticmethod
    def add_appointment_identity(
        session: AsyncSession, identity: AppointmentSourceIdentity
    ) -> None:
        session.add(identity)

    @staticmethod
    def add_progress(
        session: AsyncSession, progress: OperationalMigrationProgress
    ) -> None:
        session.add(progress)

    @staticmethod
    def add_exception(
        session: AsyncSession, exception: OperationalMigrationException
    ) -> None:
        session.add(exception)


operational_migration_repository = OperationalMigrationRepository()
