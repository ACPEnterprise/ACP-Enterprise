from types import MappingProxyType
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_execution.contracts import (
    EngineeringExecutionState,
    EngineeringExecutionStatus,
    EngineeringFailureClassification,
)
from app.engineering_execution.models import EngineeringExecution
from app.engineering_execution.records import (
    CreateEngineeringExecution,
    EngineeringExecutionRecord,
)


class EngineeringExecutionRepository:
    @staticmethod
    async def create(
        session: AsyncSession, *, execution: CreateEngineeringExecution
    ) -> EngineeringExecutionRecord:
        entity = EngineeringExecution(
            company_id=execution.company_id,
            command_id=execution.command_id,
            ecid=execution.ecid,
            instruction_digest=execution.instruction_digest,
            requested_by_user_id=execution.requested_by_user_id,
            provider_identifier=execution.provider_identifier,
            state=EngineeringExecutionState.EXECUTION_NOT_CONNECTED.value,
            status=EngineeringExecutionStatus.DISCONNECTED.value,
            correlation_id=execution.correlation_id,
            evidence_summary=execution.evidence_summary,
            validation_summary=execution.validation_summary,
            output_references=[],
            failure_classification=(
                EngineeringFailureClassification.PROVIDER_NOT_CONNECTED.value
            ),
            version=1,
            requested_at=execution.requested_at,
            created_at=execution.requested_at,
            updated_at=execution.requested_at,
        )
        session.add(entity)
        await session.flush()
        return _record(entity)

    @staticmethod
    async def get(
        session: AsyncSession, *, company_id: UUID, execution_id: UUID
    ) -> EngineeringExecutionRecord | None:
        entity = await session.scalar(
            select(EngineeringExecution).where(
                EngineeringExecution.company_id == company_id,
                EngineeringExecution.id == execution_id,
            )
        )
        return None if entity is None else _record(entity)

    @staticmethod
    async def get_by_command(
        session: AsyncSession, *, company_id: UUID, command_id: UUID
    ) -> EngineeringExecutionRecord | None:
        entity = await session.scalar(
            select(EngineeringExecution).where(
                EngineeringExecution.company_id == company_id,
                EngineeringExecution.command_id == command_id,
            )
        )
        return None if entity is None else _record(entity)

    @staticmethod
    async def list_for_company(
        session: AsyncSession, *, company_id: UUID, limit: int = 50
    ) -> tuple[EngineeringExecutionRecord, ...]:
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        entities = (
            await session.scalars(
                select(EngineeringExecution)
                .where(EngineeringExecution.company_id == company_id)
                .order_by(
                    EngineeringExecution.created_at.desc(),
                    EngineeringExecution.id.desc(),
                )
                .limit(limit)
            )
        ).all()
        return tuple(_record(entity) for entity in entities)


def _record(entity: EngineeringExecution) -> EngineeringExecutionRecord:
    if entity.failure_classification is None:
        raise ValueError("Disconnected execution requires a failure classification")
    return EngineeringExecutionRecord(
        id=entity.id,
        company_id=entity.company_id,
        command_id=entity.command_id,
        ecid=entity.ecid,
        instruction_digest=entity.instruction_digest,
        requested_by_user_id=entity.requested_by_user_id,
        provider_identifier=entity.provider_identifier,
        state=EngineeringExecutionState(entity.state),
        status=EngineeringExecutionStatus(entity.status),
        correlation_id=entity.correlation_id,
        evidence_summary=MappingProxyType(dict(entity.evidence_summary)),
        validation_summary=MappingProxyType(dict(entity.validation_summary)),
        output_references=tuple(entity.output_references),
        failure_classification=EngineeringFailureClassification(
            entity.failure_classification
        ),
        version=entity.version,
        requested_at=entity.requested_at,
        started_at=entity.started_at,
        finished_at=entity.finished_at,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )
