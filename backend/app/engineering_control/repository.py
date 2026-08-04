from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.models import (
    EngineeringCommand,
    EngineeringCommandEcidSequence,
    EngineeringCommandEvent,
)
from app.engineering_control.records import (
    AppendEngineeringCommandEvent,
    CreateEngineeringCommand,
    EngineeringApprovalState,
    EngineeringCommandEventRecord,
    EngineeringCommandMutationResult,
    EngineeringCommandQueryResult,
    EngineeringCommandRecord,
    EngineeringExecutionState,
    EngineeringMutationStatus,
)


class EngineeringCommandRepository:
    """Company-scoped SQL and locking; callers own policy and transactions."""

    @staticmethod
    async def allocate_ecid(session: AsyncSession, *, occurred_at: datetime) -> str:
        year = occurred_at.year
        statement = (
            insert(EngineeringCommandEcidSequence)
            .values(sequence_year=year, last_value=1, updated_at=occurred_at)
            .on_conflict_do_update(
                index_elements=[EngineeringCommandEcidSequence.sequence_year],
                set_={
                    "last_value": EngineeringCommandEcidSequence.last_value + 1,
                    "updated_at": func.now(),
                },
            )
            .returning(EngineeringCommandEcidSequence.last_value)
        )
        value = await session.scalar(statement)
        if value is None:
            raise RuntimeError("Engineering Control identifier allocation failed")
        return f"ECID-{year:04d}-{value:06d}"

    @classmethod
    async def create_command(
        cls, session: AsyncSession, *, command: CreateEngineeringCommand
    ) -> EngineeringCommandRecord:
        ecid = await cls.allocate_ecid(session, occurred_at=command.created_at)
        entity = EngineeringCommand(
            ecid=ecid,
            company_id=command.company_id,
            requested_by_user_id=command.requested_by_user_id,
            command_type=command.command_type,
            owner_instruction=command.owner_instruction,
            instruction_digest=command.instruction_digest,
            repository_key=command.repository_key,
            expected_branch=command.expected_branch,
            expected_head=command.expected_head,
            requested_code_changes=command.requested_code_changes,
            execution_boundary=command.execution_boundary,
            execution_boundary_digest=command.execution_boundary_digest,
            approval_state=EngineeringApprovalState.AWAITING_APPROVAL.value,
            execution_state=EngineeringExecutionState.EXECUTION_NOT_CONNECTED.value,
            idempotency_key=command.idempotency_key,
            request_digest=command.request_digest,
            correlation_id=command.correlation_id,
            expires_at=command.expires_at,
            version=1,
            created_at=command.created_at,
            updated_at=command.created_at,
        )
        session.add(entity)
        await session.flush()
        return _command_record(entity)

    @staticmethod
    async def get_command(
        session: AsyncSession, *, company_id: UUID, command_id: UUID
    ) -> EngineeringCommandRecord | None:
        entity = await session.scalar(
            select(EngineeringCommand).where(
                EngineeringCommand.company_id == company_id,
                EngineeringCommand.id == command_id,
            )
        )
        return None if entity is None else _command_record(entity)

    @staticmethod
    async def get_command_by_ecid(
        session: AsyncSession, *, company_id: UUID, ecid: str
    ) -> EngineeringCommandRecord | None:
        entity = await session.scalar(
            select(EngineeringCommand).where(
                EngineeringCommand.company_id == company_id,
                EngineeringCommand.ecid == ecid,
            )
        )
        return None if entity is None else _command_record(entity)

    @staticmethod
    async def get_command_by_idempotency_key(
        session: AsyncSession, *, company_id: UUID, idempotency_key: str
    ) -> EngineeringCommandRecord | None:
        entity = await session.scalar(
            select(EngineeringCommand).where(
                EngineeringCommand.company_id == company_id,
                EngineeringCommand.idempotency_key == idempotency_key,
            )
        )
        return None if entity is None else _command_record(entity)

    @staticmethod
    async def list_commands(
        session: AsyncSession,
        *,
        company_id: UUID,
        approval_state: EngineeringApprovalState | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> EngineeringCommandQueryResult:
        if offset < 0:
            raise ValueError("offset must be nonnegative")
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        predicates = [EngineeringCommand.company_id == company_id]
        if approval_state is not None:
            predicates.append(EngineeringCommand.approval_state == approval_state.value)
        total_count = await session.scalar(
            select(func.count(EngineeringCommand.id)).where(*predicates)
        )
        entities = (
            await session.scalars(
                select(EngineeringCommand)
                .where(*predicates)
                .order_by(
                    EngineeringCommand.created_at.desc(),
                    EngineeringCommand.id.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return EngineeringCommandQueryResult(
            items=tuple(_command_record(entity) for entity in entities),
            total_count=total_count or 0,
        )

    @staticmethod
    async def get_command_for_update(
        session: AsyncSession, *, company_id: UUID, command_id: UUID
    ) -> EngineeringCommandRecord | None:
        entity = await session.scalar(
            select(EngineeringCommand)
            .where(
                EngineeringCommand.company_id == company_id,
                EngineeringCommand.id == command_id,
            )
            .with_for_update()
        )
        return None if entity is None else _command_record(entity)

    @classmethod
    async def approve_command(
        cls,
        session: AsyncSession,
        *,
        company_id: UUID,
        command_id: UUID,
        expected_version: int,
        approved_by_user_id: UUID,
        approved_at: datetime,
    ) -> EngineeringCommandMutationResult:
        return await cls._mutate_command(
            session,
            company_id=company_id,
            command_id=command_id,
            expected_version=expected_version,
            eligible_states=(EngineeringApprovalState.AWAITING_APPROVAL,),
            values={
                "approval_state": EngineeringApprovalState.APPROVED.value,
                "approved_by_user_id": approved_by_user_id,
                "approved_at": approved_at,
                "updated_at": approved_at,
            },
            not_expired_at=approved_at,
        )

    @classmethod
    async def cancel_command(
        cls,
        session: AsyncSession,
        *,
        company_id: UUID,
        command_id: UUID,
        expected_version: int,
        canceled_by_user_id: UUID,
        canceled_at: datetime,
        cancellation_reason_code: str,
    ) -> EngineeringCommandMutationResult:
        return await cls._mutate_command(
            session,
            company_id=company_id,
            command_id=command_id,
            expected_version=expected_version,
            eligible_states=(
                EngineeringApprovalState.AWAITING_APPROVAL,
                EngineeringApprovalState.APPROVED,
            ),
            values={
                "approval_state": EngineeringApprovalState.CANCELED.value,
                "canceled_by_user_id": canceled_by_user_id,
                "canceled_at": canceled_at,
                "cancellation_reason_code": cancellation_reason_code,
                "updated_at": canceled_at,
            },
        )

    @classmethod
    async def expire_command(
        cls,
        session: AsyncSession,
        *,
        company_id: UUID,
        command_id: UUID,
        expected_version: int,
        expired_at: datetime,
    ) -> EngineeringCommandMutationResult:
        return await cls._mutate_command(
            session,
            company_id=company_id,
            command_id=command_id,
            expected_version=expected_version,
            eligible_states=(
                EngineeringApprovalState.AWAITING_APPROVAL,
                EngineeringApprovalState.APPROVED,
            ),
            values={
                "approval_state": EngineeringApprovalState.EXPIRED.value,
                "updated_at": expired_at,
            },
            expired_by=expired_at,
        )

    @staticmethod
    async def append_event(
        session: AsyncSession, *, event: AppendEngineeringCommandEvent
    ) -> EngineeringCommandEventRecord:
        command = await session.scalar(
            select(EngineeringCommand)
            .where(
                EngineeringCommand.company_id == event.company_id,
                EngineeringCommand.id == event.command_id,
                EngineeringCommand.ecid == event.ecid,
                EngineeringCommand.instruction_digest == event.instruction_digest,
            )
            .with_for_update()
        )
        if command is None:
            raise ValueError("Engineering Command event parent does not match")
        next_sequence = await session.scalar(
            select(
                func.coalesce(func.max(EngineeringCommandEvent.sequence_number), 0) + 1
            ).where(
                EngineeringCommandEvent.company_id == event.company_id,
                EngineeringCommandEvent.command_id == event.command_id,
            )
        )
        if next_sequence is None:
            raise RuntimeError("Engineering Command event sequence allocation failed")
        entity = EngineeringCommandEvent(
            company_id=event.company_id,
            command_id=event.command_id,
            ecid=event.ecid,
            instruction_digest=event.instruction_digest,
            sequence_number=next_sequence,
            event_type=event.event_type,
            prior_approval_state=_value(event.prior_approval_state),
            new_approval_state=_value(event.new_approval_state),
            prior_execution_state=_value(event.prior_execution_state),
            new_execution_state=_value(event.new_execution_state),
            actor_user_id=event.actor_user_id,
            reason_code=event.reason_code,
            event_metadata=dict(event.metadata),
            correlation_id=event.correlation_id,
            occurred_at=event.occurred_at,
            created_at=event.occurred_at,
        )
        session.add(entity)
        await session.flush()
        return _event_record(entity)

    @staticmethod
    async def list_events(
        session: AsyncSession, *, company_id: UUID, command_id: UUID
    ) -> tuple[EngineeringCommandEventRecord, ...]:
        entities = (
            await session.scalars(
                select(EngineeringCommandEvent)
                .where(
                    EngineeringCommandEvent.company_id == company_id,
                    EngineeringCommandEvent.command_id == command_id,
                )
                .order_by(
                    EngineeringCommandEvent.sequence_number,
                    EngineeringCommandEvent.id,
                )
            )
        ).all()
        return tuple(_event_record(entity) for entity in entities)

    @classmethod
    async def _mutate_command(
        cls,
        session: AsyncSession,
        *,
        company_id: UUID,
        command_id: UUID,
        expected_version: int,
        eligible_states: tuple[EngineeringApprovalState, ...],
        values: dict[str, object],
        not_expired_at: datetime | None = None,
        expired_by: datetime | None = None,
    ) -> EngineeringCommandMutationResult:
        statement = update(EngineeringCommand).where(
            EngineeringCommand.company_id == company_id,
            EngineeringCommand.id == command_id,
            EngineeringCommand.version == expected_version,
            EngineeringCommand.approval_state.in_(
                tuple(state.value for state in eligible_states)
            ),
            EngineeringCommand.execution_state
            == EngineeringExecutionState.EXECUTION_NOT_CONNECTED.value,
        )
        if not_expired_at is not None:
            statement = statement.where(EngineeringCommand.expires_at > not_expired_at)
        if expired_by is not None:
            statement = statement.where(EngineeringCommand.expires_at <= expired_by)
        entity = await session.scalar(
            statement.values(
                **values,
                version=EngineeringCommand.version + 1,
            ).returning(EngineeringCommand)
        )
        if entity is not None:
            return EngineeringCommandMutationResult(
                EngineeringMutationStatus.APPLIED,
                _command_record(entity),
            )
        current = await cls.get_command(
            session, company_id=company_id, command_id=command_id
        )
        if current is None:
            return EngineeringCommandMutationResult(EngineeringMutationStatus.NOT_FOUND)
        if current.version != expected_version:
            return EngineeringCommandMutationResult(
                EngineeringMutationStatus.STALE_VERSION,
                current,
            )
        return EngineeringCommandMutationResult(
            EngineeringMutationStatus.INELIGIBLE_STATE,
            current,
        )


def _command_record(entity: EngineeringCommand) -> EngineeringCommandRecord:
    return EngineeringCommandRecord(
        id=entity.id,
        ecid=entity.ecid,
        company_id=entity.company_id,
        requested_by_user_id=entity.requested_by_user_id,
        command_type=entity.command_type,
        owner_instruction=entity.owner_instruction,
        instruction_digest=entity.instruction_digest,
        repository_key=entity.repository_key,
        expected_branch=entity.expected_branch,
        expected_head=entity.expected_head,
        requested_code_changes=entity.requested_code_changes,
        approval_state=EngineeringApprovalState(entity.approval_state),
        execution_state=EngineeringExecutionState(entity.execution_state),
        idempotency_key=entity.idempotency_key,
        request_digest=entity.request_digest,
        correlation_id=entity.correlation_id,
        failure_code=entity.failure_code,
        cancellation_reason_code=entity.cancellation_reason_code,
        expires_at=entity.expires_at,
        version=entity.version,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        approved_at=entity.approved_at,
        approved_by_user_id=entity.approved_by_user_id,
        canceled_at=entity.canceled_at,
        canceled_by_user_id=entity.canceled_by_user_id,
        result_reference=entity.result_reference,
        execution_boundary=MappingProxyType(dict(entity.execution_boundary)),
        execution_boundary_digest=entity.execution_boundary_digest,
    )


def _event_record(entity: EngineeringCommandEvent) -> EngineeringCommandEventRecord:
    return EngineeringCommandEventRecord(
        id=entity.id,
        company_id=entity.company_id,
        command_id=entity.command_id,
        ecid=entity.ecid,
        instruction_digest=entity.instruction_digest,
        sequence_number=entity.sequence_number,
        event_type=entity.event_type,
        prior_approval_state=_approval(entity.prior_approval_state),
        new_approval_state=_approval(entity.new_approval_state),
        prior_execution_state=_execution(entity.prior_execution_state),
        new_execution_state=_execution(entity.new_execution_state),
        actor_user_id=entity.actor_user_id,
        reason_code=entity.reason_code,
        metadata=MappingProxyType(dict(entity.event_metadata)),
        correlation_id=entity.correlation_id,
        occurred_at=entity.occurred_at,
        created_at=entity.created_at,
    )


def _value(
    value: EngineeringApprovalState | EngineeringExecutionState | None,
) -> str | None:
    return None if value is None else value.value


def _approval(value: str | None) -> EngineeringApprovalState | None:
    return None if value is None else EngineeringApprovalState(value)


def _execution(value: str | None) -> EngineeringExecutionState | None:
    return None if value is None else EngineeringExecutionState(value)


engineering_command_repository = EngineeringCommandRepository()
