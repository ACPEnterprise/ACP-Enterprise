from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import (
    CustomerSourceIdentity,
    ServiceLocationSourceIdentity,
)
from app.operational_migration.cutover_models import (
    MigrationArtifact,
    MigrationArtifactAttempt,
    MigrationAuditSummary,
    MigrationCutoverAssessment,
    MigrationHistoryEntry,
    MigrationPhaseCompletion,
    MigrationRecordOutcome,
)
from app.operational_migration.models import (
    AppointmentSourceIdentity,
    EstimateSourceIdentity,
    InvoiceSourceIdentity,
    JobSourceIdentity,
    OperationalMigrationRun,
)
from app.platform.employees.models import Employee


class CutoverMigrationRepository:
    @staticmethod
    async def get_parent_identity(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        source_system: str,
        parent_type: str,
        source_parent_id: str,
    ) -> UUID | None:
        if parent_type == "customer":
            record = await session.scalar(
                select(CustomerSourceIdentity).where(
                    CustomerSourceIdentity.company_id == company_id,
                    CustomerSourceIdentity.branch_id == branch_id,
                    CustomerSourceIdentity.source_system == source_system,
                    CustomerSourceIdentity.source_customer_id == source_parent_id,
                )
            )
            return None if record is None else record.customer_id
        if parent_type == "service_location":
            record = await session.scalar(
                select(ServiceLocationSourceIdentity)
                .join(
                    CustomerSourceIdentity,
                    CustomerSourceIdentity.id
                    == ServiceLocationSourceIdentity.customer_source_identity_id,
                )
                .where(
                    ServiceLocationSourceIdentity.company_id == company_id,
                    CustomerSourceIdentity.branch_id == branch_id,
                    ServiceLocationSourceIdentity.source_system == source_system,
                    ServiceLocationSourceIdentity.source_location_id
                    == source_parent_id,
                )
            )
            return None if record is None else record.service_location_id
        if parent_type == "job":
            return await session.scalar(
                select(JobSourceIdentity.job_id).where(
                    JobSourceIdentity.company_id == company_id,
                    JobSourceIdentity.branch_id == branch_id,
                    JobSourceIdentity.source_system == source_system,
                    JobSourceIdentity.source_job_id == source_parent_id,
                )
            )
        if parent_type == "appointment":
            return await session.scalar(
                select(AppointmentSourceIdentity.appointment_id).where(
                    AppointmentSourceIdentity.company_id == company_id,
                    AppointmentSourceIdentity.branch_id == branch_id,
                    AppointmentSourceIdentity.source_system == source_system,
                    AppointmentSourceIdentity.source_appointment_id == source_parent_id,
                )
            )
        if parent_type == "estimate":
            return await session.scalar(
                select(EstimateSourceIdentity.estimate_id).where(
                    EstimateSourceIdentity.company_id == company_id,
                    EstimateSourceIdentity.branch_id == branch_id,
                    EstimateSourceIdentity.source_system == source_system,
                    EstimateSourceIdentity.source_estimate_id == source_parent_id,
                )
            )
        if parent_type == "invoice":
            return await session.scalar(
                select(InvoiceSourceIdentity.invoice_id).where(
                    InvoiceSourceIdentity.company_id == company_id,
                    InvoiceSourceIdentity.branch_id == branch_id,
                    InvoiceSourceIdentity.source_system == source_system,
                    InvoiceSourceIdentity.source_invoice_id == source_parent_id,
                )
            )
        return None

    @staticmethod
    async def employee_is_authoritative(
        session: AsyncSession, *, company_id: UUID, employee_id: UUID
    ) -> bool:
        return bool(
            await session.scalar(
                select(Employee.id).where(
                    Employee.company_id == company_id,
                    Employee.id == employee_id,
                    Employee.archived_at.is_(None),
                )
            )
        )

    @staticmethod
    async def history_exists(
        session: AsyncSession,
        *,
        company_id: UUID,
        source_system: str,
        source_hash: str,
    ) -> bool:
        return bool(
            await session.scalar(
                select(MigrationHistoryEntry.id).where(
                    MigrationHistoryEntry.company_id == company_id,
                    MigrationHistoryEntry.source_system == source_system,
                    MigrationHistoryEntry.source_id_sha256 == source_hash,
                )
            )
        )

    @staticmethod
    async def history_by_source(
        session: AsyncSession,
        *,
        company_id: UUID,
        source_system: str,
        source_hash: str,
    ) -> MigrationHistoryEntry | None:
        return await session.scalar(
            select(MigrationHistoryEntry).where(
                MigrationHistoryEntry.company_id == company_id,
                MigrationHistoryEntry.source_system == source_system,
                MigrationHistoryEntry.source_id_sha256 == source_hash,
            )
        )

    @staticmethod
    async def artifact_by_source(
        session: AsyncSession,
        *,
        company_id: UUID,
        source_system: str,
        source_hash: str,
    ) -> MigrationArtifact | None:
        return await session.scalar(
            select(MigrationArtifact).where(
                MigrationArtifact.company_id == company_id,
                MigrationArtifact.source_system == source_system,
                MigrationArtifact.source_id_sha256 == source_hash,
            )
        )

    @staticmethod
    async def artifact_by_checksum(
        session: AsyncSession,
        *,
        company_id: UUID,
        source_checksum: str,
    ) -> MigrationArtifact | None:
        return await session.scalar(
            select(MigrationArtifact).where(
                MigrationArtifact.company_id == company_id,
                MigrationArtifact.source_checksum == source_checksum,
            )
        )

    @staticmethod
    async def outcome(
        session: AsyncSession,
        *,
        run_id: UUID,
        entity_type: str,
        source_hash: str,
    ) -> MigrationRecordOutcome | None:
        return await session.scalar(
            select(MigrationRecordOutcome).where(
                MigrationRecordOutcome.run_id == run_id,
                MigrationRecordOutcome.entity_type == entity_type,
                MigrationRecordOutcome.source_id_sha256 == source_hash,
            )
        )

    @staticmethod
    def add_history(session: AsyncSession, entry: MigrationHistoryEntry) -> None:
        session.add(entry)

    @staticmethod
    async def add_artifact(
        session: AsyncSession,
        artifact: MigrationArtifact,
        attempt: MigrationArtifactAttempt,
    ) -> None:
        session.add(artifact)
        await session.flush()
        session.add(attempt)

    @staticmethod
    def add_outcome(session: AsyncSession, outcome: MigrationRecordOutcome) -> None:
        session.add(outcome)

    @staticmethod
    async def outcomes_for_run(
        session: AsyncSession, run_id: UUID
    ) -> tuple[MigrationRecordOutcome, ...]:
        return tuple(
            (
                await session.scalars(
                    select(MigrationRecordOutcome).where(
                        MigrationRecordOutcome.run_id == run_id
                    )
                )
            ).all()
        )

    @staticmethod
    async def get_run_for_update(
        session: AsyncSession, run_id: UUID
    ) -> OperationalMigrationRun | None:
        return await session.get(OperationalMigrationRun, run_id, with_for_update=True)

    @staticmethod
    async def artifacts_for_scope(
        session: AsyncSession, *, company_id: UUID, branch_id: UUID
    ) -> tuple[MigrationArtifact, ...]:
        return tuple(
            (
                await session.scalars(
                    select(MigrationArtifact).where(
                        MigrationArtifact.company_id == company_id,
                        MigrationArtifact.branch_id == branch_id,
                    )
                )
            ).all()
        )

    @staticmethod
    async def phase_completions(
        session: AsyncSession, *, company_id: UUID, branch_id: UUID
    ) -> tuple[MigrationPhaseCompletion, ...]:
        return tuple(
            (
                await session.scalars(
                    select(MigrationPhaseCompletion).where(
                        MigrationPhaseCompletion.company_id == company_id,
                        MigrationPhaseCompletion.branch_id == branch_id,
                    )
                )
            ).all()
        )

    @staticmethod
    async def unresolved_attributions(
        session: AsyncSession, *, company_id: UUID, branch_id: UUID
    ) -> int:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(MigrationHistoryEntry)
                .where(
                    MigrationHistoryEntry.company_id == company_id,
                    MigrationHistoryEntry.branch_id == branch_id,
                    MigrationHistoryEntry.attribution_status == "unresolved",
                )
            )
            or 0
        )

    @staticmethod
    async def runs_for_scope(
        session: AsyncSession, *, company_id: UUID, branch_id: UUID
    ) -> tuple[OperationalMigrationRun, ...]:
        return tuple(
            (
                await session.scalars(
                    select(OperationalMigrationRun).where(
                        OperationalMigrationRun.company_id == company_id,
                        OperationalMigrationRun.branch_id == branch_id,
                    )
                )
            ).all()
        )

    @staticmethod
    async def upsert_phase_completion(
        session: AsyncSession, completion: MigrationPhaseCompletion
    ) -> None:
        existing = await session.scalar(
            select(MigrationPhaseCompletion).where(
                MigrationPhaseCompletion.company_id == completion.company_id,
                MigrationPhaseCompletion.branch_id == completion.branch_id,
                MigrationPhaseCompletion.phase_code == completion.phase_code,
            )
        )
        if existing is None:
            session.add(completion)
            return
        existing.required = completion.required
        existing.dry_run_completed = completion.dry_run_completed
        existing.import_completed = completion.import_completed
        existing.idempotent_rerun_validated = completion.idempotent_rerun_validated
        existing.supporting_run_id = completion.supporting_run_id
        existing.completed_at = completion.completed_at

    @staticmethod
    def add_assessment(
        session: AsyncSession, assessment: MigrationCutoverAssessment
    ) -> None:
        session.add(assessment)

    @staticmethod
    def add_summary(session: AsyncSession, summary: MigrationAuditSummary) -> None:
        session.add(summary)

    @staticmethod
    async def count_open_exceptions(
        session: AsyncSession, *, run_ids: Sequence[UUID]
    ) -> int:
        if not run_ids:
            return 0
        return int(
            await session.scalar(
                select(func.count())
                .select_from(MigrationRecordOutcome)
                .where(
                    MigrationRecordOutcome.run_id.in_(run_ids),
                    MigrationRecordOutcome.disposition.in_(("rejected", "unresolved")),
                )
            )
            or 0
        )
