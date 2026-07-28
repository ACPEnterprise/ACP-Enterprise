from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.models import EngineeringCommand
from app.engineering_execution.composition.models import (
    ExecutionComposition,
    NormalizedProviderResult,
    ProviderExecutionAttempt,
)
from app.engineering_execution.controlled.models import (
    ControlledExecutionOfferModel,
    ControlledExecutionResultModel,
)
from app.engineering_execution.models import EngineeringExecution

from .contracts import EngineeringReviewDecision, EngineeringReviewState
from .models import EngineeringExecutionReview, EngineeringExecutionReviewDecision
from .records import (
    EngineeringReviewDecisionRecord,
    EngineeringReviewRecord,
)


@dataclass(frozen=True)
class EngineeringReviewSource:
    command: EngineeringCommand
    execution: EngineeringExecution
    composition: ExecutionComposition | None = None
    attempt: ProviderExecutionAttempt | None = None
    result: NormalizedProviderResult | None = None
    controlled_offer: ControlledExecutionOfferModel | None = None
    controlled_result: ControlledExecutionResultModel | None = None


class EngineeringReviewRepository:
    @staticmethod
    async def load_completed_source_for_update(
        session: AsyncSession,
        *,
        company_id: UUID,
        command_id: UUID,
    ) -> EngineeringReviewSource | None:
        command = await session.scalar(
            select(EngineeringCommand)
            .where(
                EngineeringCommand.company_id == company_id,
                EngineeringCommand.id == command_id,
            )
            .with_for_update()
        )
        if command is None:
            return None
        execution = await session.scalar(
            select(EngineeringExecution)
            .where(
                EngineeringExecution.company_id == company_id,
                EngineeringExecution.command_id == command_id,
            )
            .order_by(EngineeringExecution.requested_at.desc())
            .limit(1)
            .with_for_update()
        )
        if execution is None:
            return None
        composition = await session.scalar(
            select(ExecutionComposition)
            .where(
                ExecutionComposition.company_id == company_id,
                ExecutionComposition.execution_id == execution.id,
            )
            .order_by(ExecutionComposition.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        if composition is None:
            offer = await session.scalar(
                select(ControlledExecutionOfferModel)
                .where(
                    ControlledExecutionOfferModel.company_id == company_id,
                    ControlledExecutionOfferModel.execution_id == execution.id,
                )
                .order_by(ControlledExecutionOfferModel.created_at.desc())
                .limit(1)
                .with_for_update()
            )
            if offer is None:
                return None
            controlled_result = await session.scalar(
                select(ControlledExecutionResultModel)
                .where(
                    ControlledExecutionResultModel.company_id == company_id,
                    ControlledExecutionResultModel.offer_id == offer.id,
                )
                .with_for_update()
            )
            if controlled_result is None:
                return None
            return EngineeringReviewSource(
                command=command,
                execution=execution,
                controlled_offer=offer,
                controlled_result=controlled_result,
            )
        attempt = await session.scalar(
            select(ProviderExecutionAttempt)
            .where(
                ProviderExecutionAttempt.company_id == company_id,
                ProviderExecutionAttempt.composition_id == composition.id,
            )
            .order_by(ProviderExecutionAttempt.attempt_ordinal.desc())
            .limit(1)
            .with_for_update()
        )
        if attempt is None:
            return None
        result = await session.scalar(
            select(NormalizedProviderResult)
            .where(
                NormalizedProviderResult.company_id == company_id,
                NormalizedProviderResult.attempt_id == attempt.id,
                NormalizedProviderResult.composition_id == composition.id,
            )
            .with_for_update()
        )
        if result is None:
            return None
        return EngineeringReviewSource(
            command=command,
            execution=execution,
            composition=composition,
            attempt=attempt,
            result=result,
        )

    @staticmethod
    async def get_by_result(
        session: AsyncSession,
        *,
        company_id: UUID,
        result_id: UUID,
    ) -> EngineeringReviewRecord | None:
        entity = await session.scalar(
            select(EngineeringExecutionReview).where(
                EngineeringExecutionReview.company_id == company_id,
                EngineeringExecutionReview.result_id == result_id,
            )
        )
        return None if entity is None else _review(entity)

    @staticmethod
    async def get_by_controlled_result(
        session: AsyncSession,
        *,
        company_id: UUID,
        result_id: UUID,
    ) -> EngineeringReviewRecord | None:
        entity = await session.scalar(
            select(EngineeringExecutionReview).where(
                EngineeringExecutionReview.company_id == company_id,
                EngineeringExecutionReview.controlled_result_id == result_id,
            )
        )
        return None if entity is None else _review(entity)

    @staticmethod
    async def get_for_update(
        session: AsyncSession,
        *,
        company_id: UUID,
        review_id: UUID,
    ) -> EngineeringReviewRecord | None:
        entity = await session.scalar(
            select(EngineeringExecutionReview)
            .where(
                EngineeringExecutionReview.company_id == company_id,
                EngineeringExecutionReview.id == review_id,
            )
            .with_for_update()
        )
        return None if entity is None else _review(entity)

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        source: EngineeringReviewSource,
        review_digest: str,
        now: datetime,
    ) -> EngineeringReviewRecord:
        entity = EngineeringExecutionReview(
            company_id=source.command.company_id,
            command_id=source.command.id,
            execution_id=source.execution.id,
            composition_id=source.composition.id if source.composition else None,
            attempt_id=source.attempt.id if source.attempt else None,
            result_id=source.result.id if source.result else None,
            controlled_result_id=(
                source.controlled_result.id if source.controlled_result else None
            ),
            provider_identifier=(
                source.composition.provider_identifier
                if source.composition
                else "authenticated-worker"
            ),
            instruction_digest=source.command.instruction_digest,
            request_digest=source.command.request_digest,
            composition_digest=(
                source.composition.composition_digest
                if source.composition
                else source.command.request_digest[:64]
            ),
            review_digest=review_digest,
            state=EngineeringReviewState.PENDING.value,
            version=1,
            created_at=now,
            updated_at=now,
        )
        session.add(entity)
        await session.flush()
        return _review(entity)

    @staticmethod
    async def transition(
        session: AsyncSession,
        *,
        company_id: UUID,
        review_id: UUID,
        expected_version: int,
        state: EngineeringReviewState,
        now: datetime,
    ) -> EngineeringReviewRecord | None:
        entity = await session.scalar(
            update(EngineeringExecutionReview)
            .where(
                EngineeringExecutionReview.company_id == company_id,
                EngineeringExecutionReview.id == review_id,
                EngineeringExecutionReview.version == expected_version,
                EngineeringExecutionReview.state
                == EngineeringReviewState.PENDING.value,
            )
            .values(
                state=state.value,
                version=expected_version + 1,
                decided_at=now,
                updated_at=now,
            )
            .returning(EngineeringExecutionReview)
        )
        await session.flush()
        return None if entity is None else _review(entity)

    @staticmethod
    async def create_decision(
        session: AsyncSession,
        *,
        review: EngineeringReviewRecord,
        reviewer_user_id: UUID,
        decision: EngineeringReviewDecision,
        reason_code: str | None,
        now: datetime,
    ) -> EngineeringReviewDecisionRecord:
        entity = EngineeringExecutionReviewDecision(
            company_id=review.company_id,
            review_id=review.id,
            reviewer_user_id=reviewer_user_id,
            decision=decision.value,
            review_digest=review.review_digest,
            reason_code=reason_code,
            decided_at=now,
        )
        session.add(entity)
        await session.flush()
        return _decision(entity)

    @staticmethod
    async def get_decision(
        session: AsyncSession,
        *,
        company_id: UUID,
        review_id: UUID,
    ) -> EngineeringReviewDecisionRecord | None:
        entity = await session.scalar(
            select(EngineeringExecutionReviewDecision).where(
                EngineeringExecutionReviewDecision.company_id == company_id,
                EngineeringExecutionReviewDecision.review_id == review_id,
            )
        )
        return None if entity is None else _decision(entity)

    @staticmethod
    async def list_reviews(
        session: AsyncSession,
        *,
        company_id: UUID,
        state: EngineeringReviewState | None,
        limit: int,
    ) -> tuple[EngineeringReviewRecord, ...]:
        statement = select(EngineeringExecutionReview).where(
            EngineeringExecutionReview.company_id == company_id
        )
        if state is not None:
            statement = statement.where(EngineeringExecutionReview.state == state.value)
        entities = (
            await session.scalars(
                statement.order_by(
                    EngineeringExecutionReview.created_at.desc(),
                    EngineeringExecutionReview.id,
                ).limit(limit)
            )
        ).all()
        return tuple(_review(entity) for entity in entities)

    @staticmethod
    async def list_reviews_page(
        session: AsyncSession,
        *,
        company_id: UUID,
        state: EngineeringReviewState,
        page: int,
        page_size: int,
    ) -> tuple[tuple[EngineeringReviewRecord, ...], int]:
        predicate = (
            EngineeringExecutionReview.company_id == company_id,
            EngineeringExecutionReview.state == state.value,
        )
        total = int(
            await session.scalar(
                select(func.count(EngineeringExecutionReview.id)).where(*predicate)
            )
            or 0
        )
        entities = (
            await session.scalars(
                select(EngineeringExecutionReview)
                .where(*predicate)
                .order_by(
                    EngineeringExecutionReview.created_at.desc(),
                    EngineeringExecutionReview.id,
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return tuple(_review(entity) for entity in entities), total

    @staticmethod
    async def load_package_source(
        session: AsyncSession,
        *,
        company_id: UUID,
        review: EngineeringReviewRecord,
    ) -> EngineeringReviewSource | None:
        source = await EngineeringReviewRepository.load_completed_source_for_update(
            session,
            company_id=company_id,
            command_id=review.command_id,
        )
        if (
            source is None
            or source.execution.id != review.execution_id
            or (
                source.result is not None
                and (
                    source.composition is None
                    or source.attempt is None
                    or source.composition.id != review.composition_id
                    or source.attempt.id != review.attempt_id
                    or source.result.id != review.result_id
                )
            )
            or (
                source.controlled_result is not None
                and source.controlled_result.id != review.controlled_result_id
            )
        ):
            return None
        return source

    @staticmethod
    async def load_package_source_read_only(
        session: AsyncSession,
        *,
        company_id: UUID,
        review: EngineeringReviewRecord,
    ) -> EngineeringReviewSource | None:
        command = await session.scalar(
            select(EngineeringCommand).where(
                EngineeringCommand.company_id == company_id,
                EngineeringCommand.id == review.command_id,
            )
        )
        execution = await session.scalar(
            select(EngineeringExecution).where(
                EngineeringExecution.company_id == company_id,
                EngineeringExecution.id == review.execution_id,
                EngineeringExecution.command_id == review.command_id,
            )
        )
        if review.controlled_result_id is not None:
            offer = await session.scalar(
                select(ControlledExecutionOfferModel).where(
                    ControlledExecutionOfferModel.company_id == company_id,
                    ControlledExecutionOfferModel.execution_id == review.execution_id,
                )
            )
            controlled_result = await session.scalar(
                select(ControlledExecutionResultModel).where(
                    ControlledExecutionResultModel.company_id == company_id,
                    ControlledExecutionResultModel.id == review.controlled_result_id,
                    ControlledExecutionResultModel.execution_id == review.execution_id,
                )
            )
            if (
                command is None
                or execution is None
                or offer is None
                or controlled_result is None
            ):
                return None
            return EngineeringReviewSource(
                command=command,
                execution=execution,
                controlled_offer=offer,
                controlled_result=controlled_result,
            )
        composition = await session.scalar(
            select(ExecutionComposition).where(
                ExecutionComposition.company_id == company_id,
                ExecutionComposition.id == review.composition_id,
                ExecutionComposition.execution_id == review.execution_id,
            )
        )
        attempt = await session.scalar(
            select(ProviderExecutionAttempt).where(
                ProviderExecutionAttempt.company_id == company_id,
                ProviderExecutionAttempt.id == review.attempt_id,
                ProviderExecutionAttempt.composition_id == review.composition_id,
            )
        )
        result = await session.scalar(
            select(NormalizedProviderResult).where(
                NormalizedProviderResult.company_id == company_id,
                NormalizedProviderResult.id == review.result_id,
                NormalizedProviderResult.attempt_id == review.attempt_id,
                NormalizedProviderResult.composition_id == review.composition_id,
            )
        )
        if (
            command is None
            or execution is None
            or composition is None
            or attempt is None
            or result is None
        ):
            return None
        return EngineeringReviewSource(
            command=command,
            execution=execution,
            composition=composition,
            attempt=attempt,
            result=result,
        )


def _review(entity: EngineeringExecutionReview) -> EngineeringReviewRecord:
    return EngineeringReviewRecord(
        id=entity.id,
        company_id=entity.company_id,
        command_id=entity.command_id,
        execution_id=entity.execution_id,
        composition_id=entity.composition_id,
        attempt_id=entity.attempt_id,
        result_id=entity.result_id,
        controlled_result_id=entity.controlled_result_id,
        provider_identifier=entity.provider_identifier,
        instruction_digest=entity.instruction_digest,
        request_digest=entity.request_digest,
        composition_digest=entity.composition_digest,
        review_digest=entity.review_digest,
        state=EngineeringReviewState(entity.state),
        version=entity.version,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        decided_at=entity.decided_at,
    )


def _decision(
    entity: EngineeringExecutionReviewDecision,
) -> EngineeringReviewDecisionRecord:
    return EngineeringReviewDecisionRecord(
        id=entity.id,
        company_id=entity.company_id,
        review_id=entity.review_id,
        reviewer_user_id=entity.reviewer_user_id,
        decision=EngineeringReviewDecision(entity.decision),
        review_digest=entity.review_digest,
        reason_code=entity.reason_code,
        decided_at=entity.decided_at,
    )
