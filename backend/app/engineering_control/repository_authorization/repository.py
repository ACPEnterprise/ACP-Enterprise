from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.models import EngineeringCommand
from app.engineering_control.review.models import (
    EngineeringExecutionReview,
    EngineeringExecutionReviewDecision,
)
from app.engineering_execution.composition.models import (
    ExecutionComposition,
    NormalizedProviderResult,
    ProviderExecutionAttempt,
)
from app.engineering_execution.models import EngineeringExecution

from .contracts import (
    RepositoryAuthorizationEventType,
    RepositoryAuthorizationState,
    RepositoryOperationType,
)
from .models import (
    EngineeringRepositoryAuthorization,
    EngineeringRepositoryAuthorizationEvent,
)
from .records import (
    RepositoryAuthorizationEventRecord,
    RepositoryAuthorizationRecord,
)


@dataclass(frozen=True)
class RepositoryAuthorizationSource:
    review: EngineeringExecutionReview
    decision: EngineeringExecutionReviewDecision
    command: EngineeringCommand
    execution: EngineeringExecution
    composition: ExecutionComposition
    attempt: ProviderExecutionAttempt
    result: NormalizedProviderResult


class EngineeringRepositoryAuthorizationRepository:
    @staticmethod
    async def load_source_for_update(
        session: AsyncSession,
        *,
        company_id: UUID,
        review_id: UUID,
    ) -> RepositoryAuthorizationSource | None:
        review = await session.scalar(
            select(EngineeringExecutionReview)
            .where(
                EngineeringExecutionReview.company_id == company_id,
                EngineeringExecutionReview.id == review_id,
            )
            .with_for_update()
        )
        if review is None:
            return None
        decision = await session.scalar(
            select(EngineeringExecutionReviewDecision)
            .where(
                EngineeringExecutionReviewDecision.company_id == company_id,
                EngineeringExecutionReviewDecision.review_id == review_id,
            )
            .with_for_update()
        )
        command = await session.scalar(
            select(EngineeringCommand)
            .where(
                EngineeringCommand.company_id == company_id,
                EngineeringCommand.id == review.command_id,
            )
            .with_for_update()
        )
        result = await session.scalar(
            select(NormalizedProviderResult)
            .where(
                NormalizedProviderResult.company_id == company_id,
                NormalizedProviderResult.id == review.result_id,
            )
            .with_for_update()
        )
        execution = await session.scalar(
            select(EngineeringExecution)
            .where(
                EngineeringExecution.company_id == company_id,
                EngineeringExecution.id == review.execution_id,
            )
            .with_for_update()
        )
        composition = await session.scalar(
            select(ExecutionComposition)
            .where(
                ExecutionComposition.company_id == company_id,
                ExecutionComposition.id == review.composition_id,
            )
            .with_for_update()
        )
        attempt = await session.scalar(
            select(ProviderExecutionAttempt)
            .where(
                ProviderExecutionAttempt.company_id == company_id,
                ProviderExecutionAttempt.id == review.attempt_id,
            )
            .with_for_update()
        )
        if (
            decision is None
            or command is None
            or execution is None
            or composition is None
            or attempt is None
            or result is None
        ):
            return None
        return RepositoryAuthorizationSource(
            review,
            decision,
            command,
            execution,
            composition,
            attempt,
            result,
        )

    @staticmethod
    async def get_by_idempotency(
        session: AsyncSession,
        *,
        company_id: UUID,
        idempotency_key: str,
    ) -> RepositoryAuthorizationRecord | None:
        entity = await session.scalar(
            select(EngineeringRepositoryAuthorization).where(
                EngineeringRepositoryAuthorization.company_id == company_id,
                EngineeringRepositoryAuthorization.idempotency_key == idempotency_key,
            )
        )
        return None if entity is None else _authorization(entity)

    @staticmethod
    async def get_for_update(
        session: AsyncSession,
        *,
        company_id: UUID,
        authorization_id: UUID,
    ) -> RepositoryAuthorizationRecord | None:
        entity = await session.scalar(
            select(EngineeringRepositoryAuthorization)
            .where(
                EngineeringRepositoryAuthorization.company_id == company_id,
                EngineeringRepositoryAuthorization.id == authorization_id,
            )
            .with_for_update()
        )
        return None if entity is None else _authorization(entity)

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        source: RepositoryAuthorizationSource,
        authorized_by_user_id: UUID,
        capability_id: UUID,
        operation_type: RepositoryOperationType,
        file_boundary: tuple[str, ...],
        expected_branch: str,
        expected_base_commit: str,
        review_digest: str,
        authorization_digest: str,
        idempotency_key: str,
        authorized_at: datetime,
        expires_at: datetime,
    ) -> RepositoryAuthorizationRecord:
        entity = EngineeringRepositoryAuthorization(
            capability_id=capability_id,
            company_id=source.review.company_id,
            command_id=source.review.command_id,
            execution_id=source.review.execution_id,
            result_id=source.review.result_id,
            review_id=source.review.id,
            review_decision_id=source.decision.id,
            authorized_by_user_id=authorized_by_user_id,
            operation_type=operation_type.value,
            file_boundary=list(file_boundary),
            expected_branch=expected_branch,
            expected_base_commit=expected_base_commit,
            review_digest=review_digest,
            authorization_digest=authorization_digest,
            idempotency_key=idempotency_key,
            state=RepositoryAuthorizationState.AUTHORIZED.value,
            version=1,
            authorized_at=authorized_at,
            expires_at=expires_at,
            updated_at=authorized_at,
        )
        session.add(entity)
        await session.flush()
        return _authorization(entity)

    @staticmethod
    async def transition(
        session: AsyncSession,
        *,
        company_id: UUID,
        authorization_id: UUID,
        expected_version: int,
        target: RepositoryAuthorizationState,
        now: datetime,
    ) -> RepositoryAuthorizationRecord | None:
        values: dict[str, object] = {
            "state": target.value,
            "version": expected_version + 1,
            "updated_at": now,
        }
        if target is RepositoryAuthorizationState.REVOKED:
            values["revoked_at"] = now
        if target is RepositoryAuthorizationState.CONSUMED:
            values["consumed_at"] = now
        entity = await session.scalar(
            update(EngineeringRepositoryAuthorization)
            .where(
                EngineeringRepositoryAuthorization.company_id == company_id,
                EngineeringRepositoryAuthorization.id == authorization_id,
                EngineeringRepositoryAuthorization.version == expected_version,
                EngineeringRepositoryAuthorization.state
                == RepositoryAuthorizationState.AUTHORIZED.value,
            )
            .values(**values)
            .returning(EngineeringRepositoryAuthorization)
        )
        await session.flush()
        return None if entity is None else _authorization(entity)

    @staticmethod
    async def append_event(
        session: AsyncSession,
        *,
        authorization: RepositoryAuthorizationRecord,
        actor_user_id: UUID,
        event_type: RepositoryAuthorizationEventType,
        reason_code: str | None,
        now: datetime,
    ) -> RepositoryAuthorizationEventRecord:
        entity = EngineeringRepositoryAuthorizationEvent(
            company_id=authorization.company_id,
            authorization_id=authorization.id,
            actor_user_id=actor_user_id,
            event_type=event_type.value,
            state=authorization.state.value,
            version=authorization.version,
            reason_code=reason_code,
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
        state: RepositoryAuthorizationState | None,
        limit: int,
    ) -> tuple[RepositoryAuthorizationRecord, ...]:
        statement = select(EngineeringRepositoryAuthorization).where(
            EngineeringRepositoryAuthorization.company_id == company_id
        )
        if state is not None:
            statement = statement.where(
                EngineeringRepositoryAuthorization.state == state.value
            )
        entities = (
            await session.scalars(
                statement.order_by(
                    EngineeringRepositoryAuthorization.authorized_at.desc(),
                    EngineeringRepositoryAuthorization.id,
                ).limit(limit)
            )
        ).all()
        return tuple(_authorization(entity) for entity in entities)


def _authorization(
    entity: EngineeringRepositoryAuthorization,
) -> RepositoryAuthorizationRecord:
    return RepositoryAuthorizationRecord(
        id=entity.id,
        capability_id=entity.capability_id,
        company_id=entity.company_id,
        command_id=entity.command_id,
        execution_id=entity.execution_id,
        result_id=entity.result_id,
        review_id=entity.review_id,
        review_decision_id=entity.review_decision_id,
        authorized_by_user_id=entity.authorized_by_user_id,
        operation_type=RepositoryOperationType(entity.operation_type),
        file_boundary=tuple(entity.file_boundary),
        expected_branch=entity.expected_branch,
        expected_base_commit=entity.expected_base_commit,
        review_digest=entity.review_digest,
        authorization_digest=entity.authorization_digest,
        idempotency_key=entity.idempotency_key,
        state=RepositoryAuthorizationState(entity.state),
        version=entity.version,
        authorized_at=entity.authorized_at,
        expires_at=entity.expires_at,
        revoked_at=entity.revoked_at,
        consumed_at=entity.consumed_at,
        updated_at=entity.updated_at,
    )


def _event(
    entity: EngineeringRepositoryAuthorizationEvent,
) -> RepositoryAuthorizationEventRecord:
    return RepositoryAuthorizationEventRecord(
        id=entity.id,
        company_id=entity.company_id,
        authorization_id=entity.authorization_id,
        actor_user_id=entity.actor_user_id,
        event_type=RepositoryAuthorizationEventType(entity.event_type),
        state=RepositoryAuthorizationState(entity.state),
        version=entity.version,
        reason_code=entity.reason_code,
        created_at=entity.created_at,
    )
