from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.economics.models import BusinessFactRecord, ProfitMeasurementRecord
from app.economics.repository import EconomicsRepository
from app.economics.schemas import (
    BusinessFactListResponse,
    BusinessFactResponse,
    ConfidenceResponse,
    EvidenceCompletenessResponse,
    EvidenceReferenceResponse,
    ProfitabilityProjectionResponse,
    ProfitMeasurementListResponse,
    ProfitMeasurementResponse,
    StaleMeasurementResponse,
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
            input_digest=record.input_digest,
            engine_version=record.engine_version,
            version=record.version,
            measured_at=record.measured_at,
        )

    @staticmethod
    def _fact_response(record: BusinessFactRecord) -> BusinessFactResponse:
        return BusinessFactResponse(
            id=record.id,
            company_id=record.company_id,
            branch_id=record.branch_id,
            subject_type=record.subject_type,
            subject_id=record.subject_id,
            category=record.category,  # type: ignore[arg-type]
            fact_key=record.fact_key,
            amount_minor=record.amount_minor,
            currency=record.currency,
            confidence=ConfidenceResponse(
                status=record.confidence_status,  # type: ignore[arg-type]
                percentage=record.confidence_percentage,
                explanation=record.confidence_explanation,
            ),
            evidence=[
                EvidenceReferenceResponse.model_validate(item)
                for item in record.evidence_snapshot
            ],
            period_start=record.period_start,
            period_end=record.period_end,
            measurement_method=record.measurement_method,
            accounting_basis=record.accounting_basis,  # type: ignore[arg-type]
            correction_kind=record.correction_kind,  # type: ignore[arg-type]
            corrects_fact_id=record.corrects_fact_id,
            input_digest=record.input_digest,
            effective_at=record.effective_at,
            version=record.version,
            recorded_at=record.recorded_at,
        )

    @classmethod
    async def list_facts(
        cls,
        session: AsyncSession,
        company_id: UUID,
        subject_type: str | None,
        subject_id: UUID | None,
        limit: int,
        offset: int,
    ) -> BusinessFactListResponse:
        records = await EconomicsRepository.list_facts(
            session, company_id, subject_type, subject_id, limit, offset
        )
        return BusinessFactListResponse(
            items=[cls._fact_response(record) for record in records],
            limit=limit,
            offset=offset,
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

    @classmethod
    async def history_for_subject(
        cls,
        session: AsyncSession,
        company_id: UUID,
        subject_type: str,
        subject_id: UUID,
        limit: int,
        offset: int,
    ) -> ProfitMeasurementListResponse:
        records = await EconomicsRepository.history_for_subject(
            session, company_id, subject_type, subject_id, limit, offset
        )
        return ProfitMeasurementListResponse(
            items=[cls._response(record) for record in records],
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _projection(
        scope_type: str, scope_id: UUID, records: list[ProfitMeasurementRecord]
    ) -> ProfitabilityProjectionResponse:
        currencies = {record.currency for record in records}
        fields = (
            "revenue_minor",
            "labor_minor",
            "materials_minor",
            "equipment_minor",
            "truck_minor",
            "overhead_minor",
            "gross_profit_minor",
            "net_profit_minor",
        )
        known = (
            bool(records)
            and len(currencies) == 1
            and all(
                getattr(record, field) is not None
                for record in records
                for field in fields
            )
        )
        values = {
            field: (
                sum(int(getattr(record, field)) for record in records)
                if known
                else None
            )
            for field in fields
        }
        confidence = (
            ConfidenceResponse(
                status=(
                    "estimated"
                    if any(
                        record.confidence_status == "estimated" for record in records
                    )
                    else "measured"
                ),
                percentage=min(record.confidence_percentage for record in records),
                explanation=f"Rollup of {len(records)} latest job measurement(s).",
            )
            if known
            else ConfidenceResponse(
                status="unknown",
                percentage=0,
                explanation="No complete single-currency job measurement set exists.",
            )
        )
        return ProfitabilityProjectionResponse(
            scope_type=scope_type,  # type: ignore[arg-type]
            scope_id=scope_id,
            currency=currencies.pop() if len(currencies) == 1 else None,
            measurement_count=len(records),
            confidence=confidence,
            as_of=max((record.measured_at for record in records), default=None),
            **values,  # type: ignore[arg-type]
        )

    @classmethod
    async def branch_profitability(
        cls, session: AsyncSession, company_id: UUID, branch_id: UUID
    ) -> ProfitabilityProjectionResponse:
        records = await EconomicsRepository.latest_job_measurements(
            session, company_id, branch_id
        )
        return cls._projection("branch", branch_id, records)

    @classmethod
    async def company_profitability(
        cls, session: AsyncSession, company_id: UUID
    ) -> ProfitabilityProjectionResponse:
        records = await EconomicsRepository.latest_job_measurements(session, company_id)
        return cls._projection("company", company_id, records)

    @staticmethod
    async def evidence_completeness(
        session: AsyncSession, company_id: UUID
    ) -> EvidenceCompletenessResponse:
        known, linked = await EconomicsRepository.evidence_counts(session, company_id)
        missing = max(0, known - linked)
        return EvidenceCompletenessResponse(
            company_id=company_id,
            known_fact_count=known,
            linked_fact_count=linked,
            missing_evidence_count=missing,
            completeness_percentage=100 if known == 0 else linked * 100 // known,
        )

    @staticmethod
    async def stale_measurements(
        session: AsyncSession, company_id: UUID, limit: int
    ) -> list[StaleMeasurementResponse]:
        records = await EconomicsRepository.stale_measurements(
            session, company_id, limit
        )
        return [
            StaleMeasurementResponse(
                measurement_id=record.id,
                subject_type=record.subject_type,
                subject_id=record.subject_id,
                measured_at=record.measured_at,
                stale_since=stale_since,
            )
            for record, stale_since in records
        ]
