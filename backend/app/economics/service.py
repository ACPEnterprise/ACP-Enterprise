from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.economics.models import ProfitMeasurementRecord
from app.economics.repository import EconomicsRepository
from app.economics.schemas import (
    ConfidenceResponse,
    EvidenceReferenceResponse,
    ProfitMeasurementListResponse,
    ProfitMeasurementResponse,
)


class EconomicsMeasurementNotFoundError(LookupError):
    pass


class EconomicsQueryService:
    @staticmethod
    def _response(record: ProfitMeasurementRecord) -> ProfitMeasurementResponse:
        return ProfitMeasurementResponse(
            id=record.id,
            company_id=record.company_id,
            branch_id=record.branch_id,
            subject_type=record.subject_type,
            subject_id=record.subject_id,
            period_start=record.period_start,
            period_end=record.period_end,
            currency=record.currency,
            revenue_minor=record.revenue_minor,
            labor_minor=record.labor_minor,
            materials_minor=record.materials_minor,
            equipment_minor=record.equipment_minor,
            truck_minor=record.truck_minor,
            overhead_minor=record.overhead_minor,
            gross_profit_minor=record.gross_profit_minor,
            net_profit_minor=record.net_profit_minor,
            confidence=ConfidenceResponse(
                status=record.confidence_status,  # type: ignore[arg-type]
                percentage=record.confidence_percentage,
                explanation=record.confidence_explanation,
            ),
            evidence=[
                EvidenceReferenceResponse.model_validate(item)
                for item in record.evidence_snapshot
            ],
            input_fact_ids=[UUID(item) for item in record.input_fact_ids],
            input_allocation_ids=[UUID(item) for item in record.input_allocation_ids],
            engine_version=record.engine_version,
            version=record.version,
            measured_at=record.measured_at,
        )

    @classmethod
    async def list_measurements(
        cls, session: AsyncSession, company_id: UUID, limit: int, offset: int
    ) -> ProfitMeasurementListResponse:
        records = await EconomicsRepository.list_measurements(
            session, company_id, limit, offset
        )
        return ProfitMeasurementListResponse(
            items=[cls._response(record) for record in records],
            limit=limit,
            offset=offset,
        )

    @classmethod
    async def latest_for_subject(
        cls,
        session: AsyncSession,
        company_id: UUID,
        subject_type: str,
        subject_id: UUID,
    ) -> ProfitMeasurementResponse:
        record = await EconomicsRepository.latest_for_subject(
            session, company_id, subject_type, subject_id
        )
        if record is None:
            raise EconomicsMeasurementNotFoundError
        return cls._response(record)
