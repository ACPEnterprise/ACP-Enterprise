from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.economics.adapters import AdapterContext, AdapterResult, EconomicsSourceAdapter
from app.economics.domain import MeasurementStatus
from app.economics.ledger import EconomicsLedgerError, EconomicsLedgerService
from app.economics.models import BusinessFactRecord


class EconomicsIngestionService:
    """Routes adapter output exclusively through the authoritative ledger."""

    @staticmethod
    async def ingest(
        session: AsyncSession,
        *,
        company_id: UUID,
        adapter: EconomicsSourceAdapter,
        source: object,
        context: AdapterContext,
    ) -> tuple[BusinessFactRecord, ...]:
        source_company_id = getattr(source, "company_id", company_id)
        if source_company_id != company_id:
            raise EconomicsLedgerError("source Company does not match ingestion scope")
        result: AdapterResult = adapter.adapt(source, context)
        if any(
            command.confidence.status is not MeasurementStatus.MEASURED
            for command in result.commands
        ):
            raise EconomicsLedgerError(
                "authoritative ingestion accepts measured facts only"
            )
        return tuple(
            [
                await EconomicsLedgerService.record_fact(session, company_id, command)
                for command in result.commands
            ]
        )


economics_ingestion_service = EconomicsIngestionService()
