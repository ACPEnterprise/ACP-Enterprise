from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.models import EngineeringCommand
from app.engineering_control.workstream_runtime import EngineeringWorkstreamRuntime
from app.engineering_execution.models import EngineeringExecution
from app.execution_nodes.models import EngineeringExecutionNode
from app.worker_control.contracts import WorkerCapability
from app.worker_control.models import EngineeringWorker
from app.worker_control.transport.persistence.models import WorkerTransportSession

from .contracts import (
    ControlledCommandType,
    ControlledExecutionOffer,
    ControlledExecutionResult,
    ControlledOfferState,
    ControlledOutcome,
)
from .models import ControlledExecutionOfferModel, ControlledExecutionResultModel


class ControlledExecutionRepository:
    @staticmethod
    async def active_node_id(
        session: AsyncSession, *, company_id: UUID, worker_id: UUID, now: datetime
    ) -> UUID | None:
        return await session.scalar(
            select(EngineeringExecutionNode.id).where(
                EngineeringExecutionNode.company_id == company_id,
                EngineeringExecutionNode.worker_id == worker_id,
                EngineeringExecutionNode.status == "active",
                EngineeringExecutionNode.expires_at > now,
            )
        )

    @staticmethod
    async def load_authoritative_source(
        session: AsyncSession, *, company_id: UUID, execution_id: UUID
    ) -> tuple[EngineeringCommand, EngineeringExecution] | None:
        execution = await session.scalar(
            select(EngineeringExecution)
            .where(
                EngineeringExecution.company_id == company_id,
                EngineeringExecution.id == execution_id,
            )
            .with_for_update()
        )
        if execution is None:
            return None
        command = await session.scalar(
            select(EngineeringCommand)
            .where(
                EngineeringCommand.company_id == company_id,
                EngineeringCommand.id == execution.command_id,
            )
            .with_for_update()
        )
        return None if command is None else (command, execution)

    @staticmethod
    async def create_offer(
        session: AsyncSession,
        *,
        company_id: UUID,
        command_id: UUID,
        execution_id: UUID,
        correlation_id: UUID,
        workspace_id: str,
        payload: dict[str, object],
        expires_at: datetime,
        lease_seconds: int,
        now: datetime,
        command_type: ControlledCommandType = ControlledCommandType.INSPECT_WORKSPACE,
    ) -> ControlledExecutionOffer:
        entity = ControlledExecutionOfferModel(
            company_id=company_id,
            command_id=command_id,
            execution_id=execution_id,
            correlation_id=correlation_id,
            workspace_id=workspace_id,
            command_type=command_type.value,
            payload=payload,
            capability_required="engineering.execute",
            state=ControlledOfferState.AVAILABLE.value,
            expires_at=expires_at,
            lease_seconds=lease_seconds,
            version=1,
            created_at=now,
            updated_at=now,
        )
        session.add(entity)
        await session.flush()
        return _offer(entity)

    @staticmethod
    async def list_acknowledged_code_executions(
        session: AsyncSession,
        *,
        company_id: UUID,
        worker_id: UUID,
        now: datetime,
        limit: int,
    ) -> tuple[tuple[EngineeringCommand, EngineeringExecution], ...]:
        node = await ControlledExecutionRepository.active_node_id(
            session, company_id=company_id, worker_id=worker_id, now=now
        )
        if node is None:
            return ()
        rows = (
            await session.execute(
                select(EngineeringCommand, EngineeringExecution)
                .join(
                    EngineeringExecution,
                    EngineeringExecution.command_id == EngineeringCommand.id,
                )
                .join(
                    EngineeringWorkstreamRuntime,
                    EngineeringWorkstreamRuntime.command_id == EngineeringCommand.id,
                )
                .outerjoin(
                    ControlledExecutionOfferModel,
                    ControlledExecutionOfferModel.execution_id
                    == EngineeringExecution.id,
                )
                .where(
                    EngineeringCommand.company_id == company_id,
                    EngineeringCommand.approval_state == "approved",
                    EngineeringCommand.requested_code_changes.is_(True),
                    EngineeringCommand.canceled_at.is_(None),
                    EngineeringCommand.expires_at > now,
                    EngineeringCommand.execution_boundary_digest != "0" * 64,
                    EngineeringExecution.state == "execution_not_connected",
                    EngineeringWorkstreamRuntime.runtime_state.in_(
                        ("acknowledged", "recovering", "queued")
                    ),
                    EngineeringWorkstreamRuntime.acknowledged_action.in_(
                        ("start", "resume")
                    ),
                    ControlledExecutionOfferModel.id.is_(None),
                )
                .order_by(
                    EngineeringWorkstreamRuntime.acknowledged_at.desc(),
                    EngineeringCommand.id,
                )
                .limit(limit)
                .with_for_update(
                    of=(EngineeringCommand, EngineeringExecution), skip_locked=True
                )
            )
        ).all()
        return tuple((command, execution) for command, execution in rows)

    @staticmethod
    async def get_offer_for_update(
        session: AsyncSession, *, company_id: UUID, offer_id: UUID
    ) -> ControlledExecutionOfferModel | None:
        return await session.scalar(
            select(ControlledExecutionOfferModel)
            .where(
                ControlledExecutionOfferModel.company_id == company_id,
                ControlledExecutionOfferModel.id == offer_id,
            )
            .with_for_update()
        )

    @staticmethod
    async def get_offer(
        session: AsyncSession, *, company_id: UUID, offer_id: UUID
    ) -> ControlledExecutionOffer | None:
        entity = await session.scalar(
            select(ControlledExecutionOfferModel).where(
                ControlledExecutionOfferModel.company_id == company_id,
                ControlledExecutionOfferModel.id == offer_id,
            )
        )
        return None if entity is None else _offer(entity)

    @staticmethod
    async def list_available(
        session: AsyncSession,
        *,
        company_id: UUID,
        worker_id: UUID,
        session_id: UUID,
        now: datetime,
        limit: int,
    ) -> tuple[ControlledExecutionOffer, ...]:
        entities = (
            await session.scalars(
                select(ControlledExecutionOfferModel)
                .where(
                    ControlledExecutionOfferModel.company_id == company_id,
                    or_(
                        ControlledExecutionOfferModel.state
                        == ControlledOfferState.AVAILABLE.value,
                        (
                            (
                                ControlledExecutionOfferModel.state
                                == ControlledOfferState.ACQUIRED.value
                            )
                            & (ControlledExecutionOfferModel.worker_id == worker_id)
                        ),
                    ),
                    ControlledExecutionOfferModel.expires_at > now,
                )
                .order_by(
                    ControlledExecutionOfferModel.created_at,
                    ControlledExecutionOfferModel.id,
                )
                .limit(limit)
            )
        ).all()
        return tuple(_offer(entity) for entity in entities)

    @staticmethod
    async def reattach_acquired_session(
        session: AsyncSession,
        *,
        company_id: UUID,
        offer_id: UUID,
        worker_id: UUID,
        session_id: UUID,
        now: datetime,
    ) -> ControlledExecutionOffer | None:
        entity = await session.scalar(
            select(ControlledExecutionOfferModel)
            .where(
                ControlledExecutionOfferModel.company_id == company_id,
                ControlledExecutionOfferModel.id == offer_id,
                ControlledExecutionOfferModel.state
                == ControlledOfferState.ACQUIRED.value,
                ControlledExecutionOfferModel.worker_id == worker_id,
            )
            .with_for_update()
        )
        if entity is None:
            return None
        entity.session_id = session_id
        entity.updated_at = now
        entity.version += 1
        await session.flush()
        return _offer(entity)

    @staticmethod
    async def bind_offer(
        session: AsyncSession,
        *,
        offer: ControlledExecutionOfferModel,
        lease_id: UUID,
        worker_id: UUID,
        session_id: UUID,
        now: datetime,
    ) -> ControlledExecutionOffer:
        offer.state = ControlledOfferState.ACQUIRED.value
        offer.lease_id = lease_id
        offer.worker_id = worker_id
        offer.session_id = session_id
        offer.acquired_at = now
        offer.updated_at = now
        offer.version += 1
        await session.flush()
        return _offer(offer)

    @staticmethod
    async def load_worker_and_session(
        session: AsyncSession,
        *,
        company_id: UUID,
        worker_id: UUID,
        session_id: UUID,
    ) -> tuple[EngineeringWorker, WorkerTransportSession] | None:
        worker = await session.scalar(
            select(EngineeringWorker)
            .where(
                EngineeringWorker.company_id == company_id,
                EngineeringWorker.id == worker_id,
            )
            .with_for_update()
        )
        transport = await session.scalar(
            select(WorkerTransportSession)
            .where(
                WorkerTransportSession.company_id == company_id,
                WorkerTransportSession.id == session_id,
                WorkerTransportSession.worker_id == worker_id,
            )
            .with_for_update()
        )
        return None if worker is None or transport is None else (worker, transport)

    @staticmethod
    async def create_result(
        session: AsyncSession,
        *,
        offer: ControlledExecutionOfferModel,
        outcome: ControlledOutcome,
        output: dict[str, object],
        error_classification: str | None,
        started_at: datetime,
        completed_at: datetime,
        repository_mutated: bool,
    ) -> ControlledExecutionResult:
        assert offer.lease_id and offer.worker_id and offer.session_id
        entity = ControlledExecutionResultModel(
            company_id=offer.company_id,
            offer_id=offer.id,
            command_id=offer.command_id,
            execution_id=offer.execution_id,
            lease_id=offer.lease_id,
            worker_id=offer.worker_id,
            session_id=offer.session_id,
            outcome=outcome.value,
            output=output,
            error_classification=error_classification,
            repository_mutated=repository_mutated,
            correlation_id=offer.correlation_id,
            started_at=started_at,
            completed_at=completed_at,
            created_at=completed_at,
        )
        offer.state = (
            ControlledOfferState.COMPLETED.value
            if outcome is ControlledOutcome.SUCCEEDED
            else ControlledOfferState.FAILED.value
        )
        offer.completed_at = completed_at
        offer.updated_at = completed_at
        offer.version += 1
        session.add(entity)
        await session.flush()
        return _result(entity)


def _offer(entity: ControlledExecutionOfferModel) -> ControlledExecutionOffer:
    return ControlledExecutionOffer(
        id=entity.id,
        company_id=entity.company_id,
        command_id=entity.command_id,
        execution_id=entity.execution_id,
        correlation_id=entity.correlation_id,
        workspace_id=entity.workspace_id,
        command_type=ControlledCommandType(entity.command_type),
        payload=MappingProxyType(dict(entity.payload)),
        capability_required=WorkerCapability(entity.capability_required),
        state=ControlledOfferState(entity.state),
        expires_at=entity.expires_at,
        lease_seconds=entity.lease_seconds,
        lease_id=entity.lease_id,
        worker_id=entity.worker_id,
        session_id=entity.session_id,
        version=entity.version,
        created_at=entity.created_at,
        acquired_at=entity.acquired_at,
        completed_at=entity.completed_at,
    )


def _result(entity: ControlledExecutionResultModel) -> ControlledExecutionResult:
    return ControlledExecutionResult(
        id=entity.id,
        company_id=entity.company_id,
        offer_id=entity.offer_id,
        command_id=entity.command_id,
        execution_id=entity.execution_id,
        lease_id=entity.lease_id,
        worker_id=entity.worker_id,
        session_id=entity.session_id,
        outcome=ControlledOutcome(entity.outcome),
        output=MappingProxyType(dict(entity.output)),
        error_classification=entity.error_classification,
        repository_mutated=entity.repository_mutated,
        correlation_id=entity.correlation_id,
        started_at=entity.started_at,
        completed_at=entity.completed_at,
        created_at=entity.created_at,
    )
