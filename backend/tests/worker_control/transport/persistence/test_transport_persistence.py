import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.worker_control.contracts import (
    AuthenticatedWorkerContext,
    WorkerCapability,
    WorkerHealth,
)
from app.worker_control.models import WorkerHeartbeat
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    HeartbeatMessage,
    TransportMessageKind,
    WorkerSession,
)
from app.worker_control.transport.errors import (
    TransportBindingError,
    TransportReplayError,
    TransportSequenceError,
)
from app.worker_control.transport.persistence.models import (
    WorkerTransportChallenge,
    WorkerTransportReceipt,
    WorkerTransportSession,
)
from app.worker_control.transport.persistence.repository import (
    PostgreSQLWorkerTransportSessionRepository,
)
from app.worker_control.transport.service import WorkerTransportService
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    seed_service_fixture,
    utc_now,
)
from tests.worker_control.test_worker_control import register_available_worker


class PersistenceAuthenticator:
    active_key_version = "key-v1"

    def __init__(self, context: AuthenticatedWorkerContext) -> None:
        self.context = context

    async def authenticate_challenge_response(
        self,
        *,
        worker_id: UUID,
        authentication_response: str,
        key_version: str,
        now,
    ) -> AuthenticatedWorkerContext:
        assert worker_id == self.context.worker_id
        assert authentication_response == "proof"
        assert key_version == self.active_key_version
        return replace(self.context, authenticated_at=now)

    async def verify_message(
        self,
        *,
        envelope: AuthenticatedMessageEnvelope,
        session: WorkerSession,
    ) -> bool:
        return (
            envelope.authentication_proof == "signed"
            and envelope.worker_id == session.context.worker_id
        )


class FailingReceiptRepository(PostgreSQLWorkerTransportSessionRepository):
    async def store_receipt(self, *args, **kwargs) -> None:
        await super().store_receipt(*args, **kwargs)
        raise RuntimeError("receipt persistence failed")


@pytest_asyncio.fixture
async def transport_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    try:
        yield fixture
    finally:
        await engine.dispose()


async def established_transport(
    fixture: ServiceFixture,
    *,
    repository: PostgreSQLWorkerTransportSessionRepository | None = None,
) -> tuple[WorkerTransportService, WorkerSession]:
    _, _, context, _ = await register_available_worker(fixture)
    service = WorkerTransportService(
        authenticator=PersistenceAuthenticator(context),
        sessions=repository or PostgreSQLWorkerTransportSessionRepository(),
    )
    now = utc_now()
    async with fixture.factory() as database:
        challenge = await service.initiate_session(
            database, worker_id=context.worker_id, now=now
        )
    async with fixture.factory() as database:
        from app.worker_control.transport.contracts import WorkerSessionRequest

        session = await service.establish_session(
            database,
            request=WorkerSessionRequest(
                challenge_id=challenge.challenge_id,
                worker_id=context.worker_id,
                challenge=challenge.challenge,
                authentication_response="proof",
                capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
            ),
            now=now,
        )
    return service, session


def heartbeat(
    session: WorkerSession,
    *,
    message_id: UUID | None = None,
    sequence: int = 1,
    health: WorkerHealth = WorkerHealth.HEALTHY,
) -> AuthenticatedMessageEnvelope:
    return AuthenticatedMessageEnvelope(
        message_id=message_id or uuid4(),
        session_id=session.session_id,
        worker_id=session.context.worker_id,
        sequence_number=sequence,
        sent_at=utc_now(),
        kind=TransportMessageKind.HEARTBEAT,
        payload=HeartbeatMessage(health=health),
        authentication_proof="signed",
        key_version=session.key_version,
    )


@pytest.mark.asyncio
async def test_challenge_session_and_identical_duplicate_are_durable(
    transport_database: ServiceFixture,
) -> None:
    service, worker_session = await established_transport(transport_database)
    envelope = heartbeat(worker_session)
    async with transport_database.factory() as database:
        receipt = await service.handle_message(database, envelope=envelope)
    async with transport_database.factory() as database:
        duplicate = await service.handle_message(database, envelope=envelope)
        persisted_session = await database.get(
            WorkerTransportSession, worker_session.session_id
        )
        challenges = await database.scalar(
            select(func.count(WorkerTransportChallenge.id)).where(
                WorkerTransportChallenge.worker_id == worker_session.context.worker_id
            )
        )
        receipts = await database.scalar(
            select(func.count(WorkerTransportReceipt.message_id)).where(
                WorkerTransportReceipt.session_id == worker_session.session_id
            )
        )
    assert duplicate == replace(receipt, duplicate=True)
    assert persisted_session is not None and persisted_session.next_sequence == 2
    assert challenges == receipts == 1


@pytest.mark.asyncio
async def test_altered_duplicate_and_cross_worker_binding_fail_closed(
    transport_database: ServiceFixture,
) -> None:
    service, worker_session = await established_transport(transport_database)
    envelope = heartbeat(worker_session)
    async with transport_database.factory() as database:
        await service.handle_message(database, envelope=envelope)
    async with transport_database.factory() as database:
        with pytest.raises(TransportReplayError):
            await service.handle_message(
                database,
                envelope=replace(
                    envelope, payload=HeartbeatMessage(WorkerHealth.DEGRADED)
                ),
            )
    async with transport_database.factory() as database:
        with pytest.raises(TransportBindingError):
            await service.handle_message(
                database, envelope=replace(envelope, worker_id=uuid4())
            )


@pytest.mark.asyncio
async def test_concurrent_same_sequence_has_one_winner(
    transport_database: ServiceFixture,
) -> None:
    service, worker_session = await established_transport(transport_database)

    async def send(envelope: AuthenticatedMessageEnvelope) -> object:
        async with transport_database.factory() as database:
            return await service.handle_message(database, envelope=envelope)

    outcomes = await asyncio.gather(
        send(heartbeat(worker_session)),
        send(heartbeat(worker_session)),
        return_exceptions=True,
    )
    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, TransportSequenceError) for outcome in outcomes) == 1


@pytest.mark.asyncio
async def test_receipt_failure_rolls_back_heartbeat_sequence_and_receipt(
    transport_database: ServiceFixture,
) -> None:
    service, worker_session = await established_transport(
        transport_database, repository=FailingReceiptRepository()
    )
    async with transport_database.factory() as database:
        before = await database.scalar(select(func.count(WorkerHeartbeat.id)))
        receipts_before = await database.scalar(
            select(func.count(WorkerTransportReceipt.message_id))
        )
    with pytest.raises(RuntimeError, match="receipt persistence failed"):
        async with transport_database.factory() as database:
            await service.handle_message(database, envelope=heartbeat(worker_session))
    async with transport_database.factory() as database:
        after = await database.scalar(select(func.count(WorkerHeartbeat.id)))
        persisted_session = await database.get(
            WorkerTransportSession, worker_session.session_id
        )
        receipts = await database.scalar(
            select(func.count(WorkerTransportReceipt.message_id))
        )
    assert after == before
    assert persisted_session is not None and persisted_session.next_sequence == 1
    assert receipts == receipts_before


@pytest.mark.asyncio
async def test_expired_session_cannot_accept_message(
    transport_database: ServiceFixture,
) -> None:
    service, worker_session = await established_transport(transport_database)
    envelope = heartbeat(worker_session)
    async with transport_database.factory() as database:
        with pytest.raises(Exception):
            await service.handle_message(
                database,
                envelope=envelope,
                now=worker_session.expires_at + timedelta(seconds=1),
            )
