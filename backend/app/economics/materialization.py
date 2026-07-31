from datetime import datetime, timezone
from time import monotonic_ns
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.economics.domain import (
    BusinessFact,
    Confidence,
    EconomicCategory,
    EvidenceKind,
    EvidenceReference,
    MeasurementStatus,
)
from app.economics.ledger import EconomicsLedgerService
from app.economics.measurement import MeasurementEngine
from app.economics.models import (
    BusinessFactRecord,
    EvidenceReferenceRecord,
    FactEvidenceRecord,
    ProfitMeasurementRecord,
    RecalculationScopeRecord,
)


class EconomicsMaterializationService:
    @staticmethod
    async def _active_facts(
        session: AsyncSession,
        company_id: UUID,
        subject_type: str,
        subject_id: UUID,
        period_start: object,
        period_end: object,
    ) -> tuple[BusinessFactRecord, ...]:
        corrected = BusinessFactRecord.__table__.alias("correcting_fact")
        result = await session.scalars(
            select(BusinessFactRecord)
            .where(
                BusinessFactRecord.company_id == company_id,
                BusinessFactRecord.subject_type == subject_type,
                BusinessFactRecord.subject_id == subject_id,
                BusinessFactRecord.period_start == period_start,
                BusinessFactRecord.period_end == period_end,
                BusinessFactRecord.accounting_basis == "accrual",
                ~exists(
                    select(1).where(
                        corrected.c.company_id == company_id,
                        corrected.c.corrects_fact_id == BusinessFactRecord.id,
                        corrected.c.correction_kind.in_(
                            ("supersession", "effective_date")
                        ),
                    )
                ),
            )
            .order_by(BusinessFactRecord.id)
        )
        return tuple(result.all())

    @staticmethod
    async def _domain_fact(
        session: AsyncSession, record: BusinessFactRecord
    ) -> BusinessFact:
        evidence_records = tuple(
            (
                await session.scalars(
                    select(EvidenceReferenceRecord)
                    .join(
                        FactEvidenceRecord,
                        FactEvidenceRecord.evidence_id == EvidenceReferenceRecord.id,
                    )
                    .where(
                        FactEvidenceRecord.company_id == record.company_id,
                        FactEvidenceRecord.fact_id == record.id,
                    )
                    .order_by(EvidenceReferenceRecord.id)
                )
            ).all()
        )
        evidence = tuple(
            EvidenceReference(
                kind=EvidenceKind(item.kind),
                reference_id=item.reference_id,
                source_system=item.source_system,
                source_version=item.source_version,
                source_record_type=item.source_record_type,
                content_digest=item.content_digest,
                observed_at=item.observed_at,
                explanation=item.explanation,
            )
            for item in evidence_records
        )
        return BusinessFact(
            id=record.id,
            company_id=record.company_id,
            branch_id=record.branch_id,
            subject_type=record.subject_type,
            subject_id=record.subject_id,
            category=EconomicCategory(record.category),
            fact_key=record.fact_key,
            amount_minor=record.amount_minor,
            currency=record.currency,
            confidence=Confidence(
                MeasurementStatus(record.confidence_status),
                record.confidence_percentage,
                record.confidence_explanation,
            ),
            evidence=evidence,
            occurred_at=record.occurred_at,
            period_start=record.period_start,
            period_end=record.period_end,
            measurement_method=record.measurement_method,
            version=record.version,
        )

    @classmethod
    async def materialize_job(
        cls,
        session: AsyncSession,
        company_id: UUID,
        branch_id: UUID | None,
        job_id: UUID,
        period_start: object,
        period_end: object,
    ) -> ProfitMeasurementRecord | None:
        records = await cls._active_facts(
            session, company_id, "job", job_id, period_start, period_end
        )
        if not records:
            return None
        facts = tuple([await cls._domain_fact(session, record) for record in records])
        measurement = MeasurementEngine.measure("job", job_id, facts)
        return await EconomicsLedgerService.record_profit_measurement(
            session, company_id, branch_id, measurement
        )


class EconomicsRecalculationService:
    @classmethod
    async def process_pending(cls, session: AsyncSession, *, limit: int = 100) -> int:
        from app.economics.integrity import ProjectionPublicationService
        from app.economics.models import OperationalMetricRecord

        pending = tuple(
            (
                await session.scalars(
                    select(RecalculationScopeRecord)
                    .where(RecalculationScopeRecord.processed_at.is_(None))
                    .order_by(
                        RecalculationScopeRecord.requested_at,
                        RecalculationScopeRecord.id,
                    )
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        processed_at = datetime.now(timezone.utc)
        processed = 0
        for scope in pending:
            started = monotonic_ns()
            if scope.scope_type == "job":
                await EconomicsMaterializationService.materialize_job(
                    session,
                    scope.company_id,
                    scope.branch_id,
                    scope.scope_id,
                    scope.period_start,
                    scope.period_end,
                )
            await ProjectionPublicationService.publish(
                session,
                scope.company_id,
                scope.scope_type,
                scope.scope_id,
                scope.period_start,
                scope.period_end,
                scope.branch_id,
            )
            session.add(
                OperationalMetricRecord(
                    company_id=scope.company_id,
                    name="materialization_duration_ms",
                    value=max(0, (monotonic_ns() - started) // 1_000_000),
                    labels={
                        "scope_type": scope.scope_type,
                        "scope_id": str(scope.scope_id),
                    },
                )
            )
            scope.processed_at = processed_at
            processed += 1
        await session.flush()
        return processed


economics_recalculation_service = EconomicsRecalculationService()
