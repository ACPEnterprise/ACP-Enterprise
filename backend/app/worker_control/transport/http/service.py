from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.worker_control.contracts import AuthenticatedWorkerContext, ExecutionOffer
from app.worker_control.transport.contracts import WorkerSession
from app.worker_control.transport.repository import WorkerTransportSessionRepository


class WorkerOfferSource(Protocol):
    async def poll(
        self,
        database: AsyncSession,
        *,
        session: WorkerSession,
        limit: int,
    ) -> tuple[ExecutionOffer, ...]: ...


class AuthenticatedSessionValidator(Protocol):
    async def validate_authenticated_session_in_transaction(
        self,
        database: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        session_id: UUID,
        now: datetime | None = None,
    ) -> WorkerSession: ...


class DisconnectedWorkerOfferSource:
    """DF.7B honest default: no queue, dispatch, or execution provider exists."""

    async def poll(
        self,
        database: AsyncSession,
        *,
        session: WorkerSession,
        limit: int,
    ) -> tuple[ExecutionOffer, ...]:
        del database, session, limit
        return ()


class WorkerPollingService:
    def __init__(
        self,
        *,
        sessions: WorkerTransportSessionRepository,
        session_validator: AuthenticatedSessionValidator,
        offers: WorkerOfferSource | None = None,
    ) -> None:
        self.sessions = sessions
        self.session_validator = session_validator
        self.offers = offers or DisconnectedWorkerOfferSource()

    async def poll(
        self,
        database: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        session_id,
        limit: int,
    ) -> tuple[ExecutionOffer, ...]:
        async with database.begin():
            session = await self.session_validator.validate_authenticated_session_in_transaction(
                database, context=context, session_id=session_id
            )
            return await self.offers.poll(database, session=session, limit=limit)
