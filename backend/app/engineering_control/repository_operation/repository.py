from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.repository_authorization.records import (
    RepositoryAuthorizationRecord,
)
from app.engineering_control.repository_authorization.repository import (
    EngineeringRepositoryAuthorizationRepository,
)

from .contracts import (
    RepositoryOperationEventType,
    RepositoryOperationState,
    RepositoryOperationType,
)
from .models import (
    EngineeringRepositoryOperation,
    EngineeringRepositoryOperationEvent,
)
from .records import RepositoryOperationEventRecord, RepositoryOperationRecord


class EngineeringRepositoryOperationRepository:
    @staticmethod
    async def get_authorization_for_update(
        session: AsyncSession,
        *,
        company_id: UUID,
        authorization_id: UUID,
    ) -> RepositoryAuthorizationRecord | None:
        return await EngineeringRepositoryAuthorizationRepository.get_for_update(
            session,
            company_id=company_id,
            authorization_id=authorization_id,
        )

    @staticmethod
    async def get_for_update(
        session: AsyncSession,
        *,
        company_id: UUID,
        operation_id: UUID,
    ) -> RepositoryOperationRecord | None:
        entity = await session.scalar(
            select(EngineeringRepositoryOperation)
            .where(
                EngineeringRepositoryOperation.company_id == company_id,
                EngineeringRepositoryOperation.id == operation_id,
            )
            .with_for_update()
        )
        return None if entity is None else _record(entity)

    @staticmethod
    async def get_by_idempotency(
        session: AsyncSession,
        *,
        company_id: UUID,
        idempotency_key: str,
    ) -> RepositoryOperationRecord | None:
        entity = await session.scalar(
            select(EngineeringRepositoryOperation).where(
                EngineeringRepositoryOperation.company_id == company_id,
                EngineeringRepositoryOperation.idempotency_key == idempotency_key,
            )
        )
        return None if entity is None else _record(entity)

    @staticmethod
    async def get_by_authorization(
        session: AsyncSession,
        *,
        company_id: UUID,
        authorization_id: UUID,
    ) -> RepositoryOperationRecord | None:
        entity = await session.scalar(
            select(EngineeringRepositoryOperation).where(
                EngineeringRepositoryOperation.company_id == company_id,
                EngineeringRepositoryOperation.authorization_id == authorization_id,
            )
        )
        return None if entity is None else _record(entity)

    @staticmethod
    async def create_reserved(
        session: AsyncSession,
        *,
        authorization: RepositoryAuthorizationRecord,
        requested_by_user_id: UUID,
        commit_subject: str,
        boundary_digest: str,
        idempotency_key: str,
        now: datetime,
    ) -> RepositoryOperationRecord:
        entity = EngineeringRepositoryOperation(
            company_id=authorization.company_id,
            authorization_id=authorization.id,
            command_id=authorization.command_id,
            execution_id=authorization.execution_id,
            review_decision_id=authorization.review_decision_id,
            requested_by_user_id=requested_by_user_id,
            operation_type=RepositoryOperationType.CREATE_COMMIT.value,
            commit_subject=commit_subject,
            expected_branch=authorization.expected_branch,
            expected_base_commit=authorization.expected_base_commit,
            file_boundary=list(authorization.file_boundary),
            boundary_digest=boundary_digest,
            idempotency_key=idempotency_key,
            state=RepositoryOperationState.RESERVED.value,
            version=1,
            requested_at=now,
            reserved_at=now,
            updated_at=now,
        )
        session.add(entity)
        await session.flush()
        return _record(entity)

    @staticmethod
    async def transition(
        session: AsyncSession,
        *,
        company_id: UUID,
        operation_id: UUID,
        expected_version: int,
        from_states: tuple[RepositoryOperationState, ...],
        target: RepositoryOperationState,
        now: datetime,
        resulting_commit_sha: str | None = None,
        failure_classification: str | None = None,
        failure_detail: str | None = None,
    ) -> RepositoryOperationRecord | None:
        values: dict[str, object] = {
            "state": target.value,
            "version": expected_version + 1,
            "updated_at": now,
            "resulting_commit_sha": resulting_commit_sha,
            "failure_classification": failure_classification,
            "failure_detail": failure_detail,
        }
        if target is RepositoryOperationState.EXECUTING:
            values["execution_started_at"] = now
        elif target is RepositoryOperationState.SUCCEEDED:
            values["succeeded_at"] = now
            values["failed_at"] = None
            values["reconciliation_required_at"] = None
        elif target is RepositoryOperationState.FAILED:
            values["failed_at"] = now
        elif target is RepositoryOperationState.RECONCILIATION_REQUIRED:
            values["reconciliation_required_at"] = now
        entity = await session.scalar(
            update(EngineeringRepositoryOperation)
            .where(
                EngineeringRepositoryOperation.company_id == company_id,
                EngineeringRepositoryOperation.id == operation_id,
                EngineeringRepositoryOperation.version == expected_version,
                EngineeringRepositoryOperation.state.in_(
                    tuple(state.value for state in from_states)
                ),
            )
            .values(**values)
            .returning(EngineeringRepositoryOperation)
        )
        await session.flush()
        return None if entity is None else _record(entity)

    @staticmethod
    async def append_event(
        session: AsyncSession,
        *,
        operation: RepositoryOperationRecord,
        actor_user_id: UUID,
        event_type: RepositoryOperationEventType,
        now: datetime,
    ) -> RepositoryOperationEventRecord:
        entity = EngineeringRepositoryOperationEvent(
            company_id=operation.company_id,
            operation_id=operation.id,
            actor_user_id=actor_user_id,
            event_type=event_type.value,
            state=operation.state.value,
            version=operation.version,
            resulting_commit_sha=operation.resulting_commit_sha,
            failure_classification=operation.failure_classification,
            created_at=now,
        )
        session.add(entity)
        await session.flush()
        return _event(entity)

    @staticmethod
    async def list(
        session: AsyncSession,
        *,
        company_id: UUID,
        limit: int,
    ) -> tuple[RepositoryOperationRecord, ...]:
        entities = (
            await session.scalars(
                select(EngineeringRepositoryOperation)
                .where(EngineeringRepositoryOperation.company_id == company_id)
                .order_by(
                    EngineeringRepositoryOperation.requested_at.desc(),
                    EngineeringRepositoryOperation.id,
                )
                .limit(limit)
            )
        ).all()
        return tuple(_record(entity) for entity in entities)


def _record(entity: EngineeringRepositoryOperation) -> RepositoryOperationRecord:
    return RepositoryOperationRecord(
        id=entity.id,
        company_id=entity.company_id,
        authorization_id=entity.authorization_id,
        command_id=entity.command_id,
        execution_id=entity.execution_id,
        review_decision_id=entity.review_decision_id,
        requested_by_user_id=entity.requested_by_user_id,
        operation_type=RepositoryOperationType(entity.operation_type),
        commit_subject=entity.commit_subject,
        expected_branch=entity.expected_branch,
        expected_base_commit=entity.expected_base_commit,
        file_boundary=tuple(entity.file_boundary),
        boundary_digest=entity.boundary_digest,
        idempotency_key=entity.idempotency_key,
        state=RepositoryOperationState(entity.state),
        resulting_commit_sha=entity.resulting_commit_sha,
        failure_classification=entity.failure_classification,
        failure_detail=entity.failure_detail,
        version=entity.version,
        requested_at=entity.requested_at,
        reserved_at=entity.reserved_at,
        execution_started_at=entity.execution_started_at,
        succeeded_at=entity.succeeded_at,
        failed_at=entity.failed_at,
        reconciliation_required_at=entity.reconciliation_required_at,
        updated_at=entity.updated_at,
    )


def _event(
    entity: EngineeringRepositoryOperationEvent,
) -> RepositoryOperationEventRecord:
    return RepositoryOperationEventRecord(
        id=entity.id,
        company_id=entity.company_id,
        operation_id=entity.operation_id,
        actor_user_id=entity.actor_user_id,
        event_type=RepositoryOperationEventType(entity.event_type),
        state=RepositoryOperationState(entity.state),
        version=entity.version,
        resulting_commit_sha=entity.resulting_commit_sha,
        failure_classification=entity.failure_classification,
        created_at=entity.created_at,
    )
