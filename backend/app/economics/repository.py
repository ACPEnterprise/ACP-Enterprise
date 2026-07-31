from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.economics.models import ProfitMeasurementRecord


class EconomicsRepository:
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
        return await session.scalar(
            select(ProfitMeasurementRecord)
            .where(
                ProfitMeasurementRecord.company_id == company_id,
                ProfitMeasurementRecord.subject_type == subject_type,
                ProfitMeasurementRecord.subject_id == subject_id,
            )
            .order_by(
                ProfitMeasurementRecord.measured_at.desc(),
                ProfitMeasurementRecord.id.desc(),
            )
            .limit(1)
        )
