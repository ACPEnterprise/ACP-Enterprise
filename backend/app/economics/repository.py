from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.economics.models import (
    BusinessFactRecord,
    FactEvidenceRecord,
    ProfitMeasurementRecord,
    RecalculationScopeRecord,
)


class EconomicsRepository:
    @staticmethod
    def _not_superseded() -> ColumnElement[bool]:
        return ~exists(
            select(1).where(
                RecalculationScopeRecord.company_id
                == ProfitMeasurementRecord.company_id,
                RecalculationScopeRecord.scope_type
                == ProfitMeasurementRecord.subject_type,
                RecalculationScopeRecord.scope_id == ProfitMeasurementRecord.subject_id,
                RecalculationScopeRecord.period_start
                == ProfitMeasurementRecord.period_start,
                RecalculationScopeRecord.period_end
                == ProfitMeasurementRecord.period_end,
                RecalculationScopeRecord.requested_at
                > ProfitMeasurementRecord.measured_at,
            )
        )

    @staticmethod
    async def list_measurements(
        session: AsyncSession, company_id: UUID, limit: int, offset: int
    ) -> list[ProfitMeasurementRecord]:
        result = await session.execute(
            select(ProfitMeasurementRecord)
            .where(ProfitMeasurementRecord.company_id == company_id)
            .order_by(
                ProfitMeasurementRecord.measured_at.desc(),
                ProfitMeasurementRecord.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    @staticmethod
    async def latest_for_subject(
        session: AsyncSession, company_id: UUID, subject_type: str, subject_id: UUID
    ) -> ProfitMeasurementRecord | None:
        records = await session.scalars(
            select(ProfitMeasurementRecord)
            .where(
                ProfitMeasurementRecord.company_id == company_id,
                ProfitMeasurementRecord.subject_type == subject_type,
                ProfitMeasurementRecord.subject_id == subject_id,
                EconomicsRepository._not_superseded(),
            )
            .order_by(
                ProfitMeasurementRecord.measured_at.desc(),
                ProfitMeasurementRecord.id.desc(),
            )
            .limit(1)
        )
        return records.first()

    @staticmethod
    async def history_for_subject(
        session: AsyncSession,
        company_id: UUID,
        subject_type: str,
        subject_id: UUID,
        limit: int,
        offset: int,
    ) -> list[ProfitMeasurementRecord]:
        result = await session.scalars(
            select(ProfitMeasurementRecord)
            .where(
                ProfitMeasurementRecord.company_id == company_id,
                ProfitMeasurementRecord.subject_type == subject_type,
                ProfitMeasurementRecord.subject_id == subject_id,
            )
            .order_by(
                ProfitMeasurementRecord.measured_at.desc(),
                ProfitMeasurementRecord.version.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(result.all())

    @staticmethod
    async def latest_job_measurements(
        session: AsyncSession, company_id: UUID, branch_id: UUID | None = None
    ) -> list[ProfitMeasurementRecord]:
        ranked = select(
            ProfitMeasurementRecord.id.label("id"),
            func.row_number()
            .over(
                partition_by=ProfitMeasurementRecord.subject_id,
                order_by=(
                    ProfitMeasurementRecord.measured_at.desc(),
                    ProfitMeasurementRecord.version.desc(),
                ),
            )
            .label("rank"),
        ).where(
            ProfitMeasurementRecord.company_id == company_id,
            ProfitMeasurementRecord.subject_type == "job",
            EconomicsRepository._not_superseded(),
        )
        if branch_id is not None:
            ranked = ranked.where(ProfitMeasurementRecord.branch_id == branch_id)
        ranked_subquery = ranked.subquery()
        result = await session.scalars(
            select(ProfitMeasurementRecord)
            .join(ranked_subquery, ranked_subquery.c.id == ProfitMeasurementRecord.id)
            .where(ranked_subquery.c.rank == 1)
        )
        return list(result.all())

    @staticmethod
    async def evidence_counts(
        session: AsyncSession, company_id: UUID
    ) -> tuple[int, int]:
        known = int(
            await session.scalar(
                select(func.count())
                .select_from(BusinessFactRecord)
                .where(
                    BusinessFactRecord.company_id == company_id,
                    BusinessFactRecord.amount_minor.is_not(None),
                )
            )
            or 0
        )
        linked = int(
            await session.scalar(
                select(func.count(func.distinct(FactEvidenceRecord.fact_id))).where(
                    FactEvidenceRecord.company_id == company_id
                )
            )
            or 0
        )
        return known, linked

    @staticmethod
    async def list_facts(
        session: AsyncSession,
        company_id: UUID,
        subject_type: str | None,
        subject_id: UUID | None,
        limit: int,
        offset: int,
    ) -> list[BusinessFactRecord]:
        statement = select(BusinessFactRecord).where(
            BusinessFactRecord.company_id == company_id
        )
        if subject_type is not None:
            statement = statement.where(BusinessFactRecord.subject_type == subject_type)
        if subject_id is not None:
            statement = statement.where(BusinessFactRecord.subject_id == subject_id)
        records = await session.scalars(
            statement.order_by(
                BusinessFactRecord.recorded_at.desc(),
                BusinessFactRecord.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(records.all())

    @staticmethod
    async def stale_measurements(
        session: AsyncSession, company_id: UUID, limit: int
    ) -> list[tuple[ProfitMeasurementRecord, datetime]]:
        newer_measurement = ProfitMeasurementRecord.__table__.alias("newer_measurement")
        stale_scope_at = (
            select(func.min(RecalculationScopeRecord.requested_at))
            .where(
                RecalculationScopeRecord.company_id
                == ProfitMeasurementRecord.company_id,
                RecalculationScopeRecord.scope_type
                == ProfitMeasurementRecord.subject_type,
                RecalculationScopeRecord.scope_id == ProfitMeasurementRecord.subject_id,
                RecalculationScopeRecord.period_start
                == ProfitMeasurementRecord.period_start,
                RecalculationScopeRecord.period_end
                == ProfitMeasurementRecord.period_end,
                RecalculationScopeRecord.requested_at
                > ProfitMeasurementRecord.measured_at,
            )
            .correlate(ProfitMeasurementRecord)
            .scalar_subquery()
        )
        result = await session.execute(
            select(ProfitMeasurementRecord, stale_scope_at.label("stale_since"))
            .where(
                ProfitMeasurementRecord.company_id == company_id,
                ~exists(
                    select(1).where(
                        newer_measurement.c.company_id
                        == ProfitMeasurementRecord.company_id,
                        newer_measurement.c.subject_type
                        == ProfitMeasurementRecord.subject_type,
                        newer_measurement.c.subject_id
                        == ProfitMeasurementRecord.subject_id,
                        newer_measurement.c.period_start
                        == ProfitMeasurementRecord.period_start,
                        newer_measurement.c.period_end
                        == ProfitMeasurementRecord.period_end,
                        newer_measurement.c.version > ProfitMeasurementRecord.version,
                    )
                ),
                ~EconomicsRepository._not_superseded(),
            )
            .order_by(stale_scope_at, ProfitMeasurementRecord.id)
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result.all()]
