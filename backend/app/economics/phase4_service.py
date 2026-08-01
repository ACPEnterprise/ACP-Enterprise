from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.economics.models import (
    AccountingExportRecord,
    AccountingPeriodRecord,
    AllocationRunRecord,
    CloseReadinessRecord,
    FinancialIntegrityPublicationRecord,
    GeneralLedgerReconciliationRecord,
    PeriodAuditPackageRecord,
    RecalculationScopeRecord,
    ReconciliationResultRecord,
)
from app.economics.schemas import (
    AllocationStatusResponse,
    AuditPackageResponse,
    CloseReadinessResponse,
    ConfidenceResponse,
    ExportStatusResponse,
    FinancialIntegrityResponse,
    ProjectionLineageResponse,
    ReconciliationStatusResponse,
)


class EconomicsPhase4NotFoundError(LookupError):
    pass


class EconomicsPhase4QueryService:
    @staticmethod
    async def close_readiness(
        session: AsyncSession, company_id: UUID, period_id: UUID
    ) -> CloseReadinessResponse:
        record = await session.scalar(
            select(CloseReadinessRecord)
            .where(
                CloseReadinessRecord.company_id == company_id,
                CloseReadinessRecord.period_id == period_id,
            )
            .order_by(CloseReadinessRecord.version.desc())
            .limit(1)
        )
        if record is None:
            raise EconomicsPhase4NotFoundError
        return CloseReadinessResponse.model_validate(record, from_attributes=True)

    @staticmethod
    async def reconciliation(
        session: AsyncSession, company_id: UUID, period_id: UUID
    ) -> ReconciliationStatusResponse:
        economics = tuple(
            (
                await session.scalars(
                    select(ReconciliationResultRecord)
                    .where(
                        ReconciliationResultRecord.company_id == company_id,
                        ReconciliationResultRecord.period_id == period_id,
                    )
                    .order_by(ReconciliationResultRecord.reconciled_at)
                )
            ).all()
        )
        gl = await session.scalar(
            select(GeneralLedgerReconciliationRecord)
            .where(
                GeneralLedgerReconciliationRecord.company_id == company_id,
                GeneralLedgerReconciliationRecord.period_id == period_id,
            )
            .order_by(GeneralLedgerReconciliationRecord.version.desc())
            .limit(1)
        )
        if not economics and gl is None:
            raise EconomicsPhase4NotFoundError
        by_kind = {item.kind: item.status for item in economics}
        return ReconciliationStatusResponse(
            period_id=period_id,
            economics=by_kind,
            general_ledger_status=gl.status if gl else "unknown",  # type: ignore[arg-type]
            period_variance_minor=gl.period_variance_minor if gl else None,
            unexplained_residual_minor=gl.unexplained_residual_minor if gl else None,
            reconciled_at=gl.reconciled_at if gl else None,
        )

    @staticmethod
    async def allocation_status(
        session: AsyncSession, company_id: UUID, period_id: UUID
    ) -> AllocationStatusResponse:
        runs = tuple(
            (
                await session.scalars(
                    select(AllocationRunRecord).where(
                        AllocationRunRecord.company_id == company_id,
                        AllocationRunRecord.period_id == period_id,
                    )
                )
            ).all()
        )
        return AllocationStatusResponse(
            period_id=period_id,
            run_count=len(runs),
            balanced_run_count=sum(item.residual_amount_minor == 0 for item in runs),
            residual_minor=sum(item.residual_amount_minor for item in runs),
        )

    @staticmethod
    async def audit_package(
        session: AsyncSession, company_id: UUID, period_id: UUID
    ) -> AuditPackageResponse:
        record = await session.scalar(
            select(PeriodAuditPackageRecord)
            .where(
                PeriodAuditPackageRecord.company_id == company_id,
                PeriodAuditPackageRecord.period_id == period_id,
            )
            .order_by(PeriodAuditPackageRecord.version.desc())
            .limit(1)
        )
        if record is None:
            raise EconomicsPhase4NotFoundError
        return AuditPackageResponse.model_validate(record, from_attributes=True)

    @staticmethod
    async def export_status(
        session: AsyncSession, company_id: UUID, period_id: UUID
    ) -> list[ExportStatusResponse]:
        records = tuple(
            (
                await session.scalars(
                    select(AccountingExportRecord)
                    .where(
                        AccountingExportRecord.company_id == company_id,
                        AccountingExportRecord.period_id == period_id,
                    )
                    .order_by(
                        AccountingExportRecord.created_at.desc(),
                        AccountingExportRecord.version.desc(),
                    )
                )
            ).all()
        )
        return [
            ExportStatusResponse.model_validate(item, from_attributes=True)
            for item in records
        ]

    @staticmethod
    async def projection_lineage(
        session: AsyncSession, company_id: UUID, projection_id: UUID
    ) -> ProjectionLineageResponse:
        record = await session.scalar(
            select(FinancialIntegrityPublicationRecord)
            .where(
                FinancialIntegrityPublicationRecord.company_id == company_id,
                FinancialIntegrityPublicationRecord.projection_id == projection_id,
            )
            .order_by(FinancialIntegrityPublicationRecord.version.desc())
            .limit(1)
        )
        if record is None:
            raise EconomicsPhase4NotFoundError
        return ProjectionLineageResponse(
            projection_id=record.projection_id,
            period_id=record.period_id,
            confidence=ConfidenceResponse(
                status=record.confidence_status,  # type: ignore[arg-type]
                percentage=record.confidence_percentage,
                explanation="Authoritative projection confidence.",
            ),
            completeness_percentage=record.completeness_percentage,
            freshness_status=record.freshness_status,
            evidence_lineage=[UUID(item) for item in record.evidence_lineage],
            integrity_status=record.integrity_status,  # type: ignore[arg-type]
            version=record.version,
            published_at=record.published_at,
        )

    @staticmethod
    async def financial_integrity(
        session: AsyncSession, company_id: UUID, period_id: UUID
    ) -> FinancialIntegrityResponse:
        period = await session.scalar(
            select(AccountingPeriodRecord).where(
                AccountingPeriodRecord.company_id == company_id,
                AccountingPeriodRecord.id == period_id,
            )
        )
        if period is None:
            raise EconomicsPhase4NotFoundError
        readiness = await session.scalar(
            select(CloseReadinessRecord)
            .where(
                CloseReadinessRecord.company_id == company_id,
                CloseReadinessRecord.period_id == period_id,
            )
            .order_by(CloseReadinessRecord.version.desc())
            .limit(1)
        )
        package = await session.scalar(
            select(PeriodAuditPackageRecord)
            .where(
                PeriodAuditPackageRecord.company_id == company_id,
                PeriodAuditPackageRecord.period_id == period_id,
            )
            .order_by(PeriodAuditPackageRecord.version.desc())
            .limit(1)
        )
        export_status = await session.scalar(
            select(AccountingExportRecord.status)
            .where(
                AccountingExportRecord.company_id == company_id,
                AccountingExportRecord.period_id == period_id,
            )
            .order_by(AccountingExportRecord.created_at.desc())
            .limit(1)
        )
        stale = int(
            await session.scalar(
                select(func.count())
                .select_from(RecalculationScopeRecord)
                .where(
                    RecalculationScopeRecord.company_id == company_id,
                    RecalculationScopeRecord.period_start >= period.period_start,
                    RecalculationScopeRecord.period_end <= period.period_end,
                    RecalculationScopeRecord.processed_at.is_(None),
                )
            )
            or 0
        )
        integrity = (
            "stale"
            if stale
            else "reconciled"
            if readiness and readiness.ready
            else "incomplete"
            if readiness
            else "unknown"
        )
        return FinancialIntegrityResponse(
            period_id=period_id,
            period_status=period.status,  # type: ignore[arg-type]
            ready_to_close=bool(readiness and readiness.ready and not stale),
            integrity_status=integrity,  # type: ignore[arg-type]
            blockers=(
                [*readiness.blockers, "stale_measurements"]
                if readiness and stale
                else list(readiness.blockers)
                if readiness
                else ["readiness_not_evaluated"]
            ),
            audit_package_digest=package.package_digest if package else None,
            latest_export_status=export_status,
            as_of=datetime.now(timezone.utc),
        )
