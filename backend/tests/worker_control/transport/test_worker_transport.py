from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.worker_control.contracts import (
    AuthenticatedWorkerContext,
    WorkerCapability,
    WorkerExecutionResult,
    WorkerFailureClassification,
    WorkerHealth,
    WorkerLifecycleState,
    WorkerResultStatus,
)
from app.worker_control.records import (
    WorkerHeartbeatRecord,
    WorkerIdentity,
    WorkerResultRecord,
)
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    AuthenticatedWorkerSessionIdentity,
    HeartbeatMessage,
    ResultMessage,
    TransportMessageKind,
    WorkerSession,
    WorkerSessionRequest,
)
from app.worker_control.transport.errors import (
    TransportAuthenticationError,
    TransportBindingError,
    TransportCapabilityError,
    TransportChallengeError,
    TransportReplayError,
    TransportSequenceError,
    TransportSessionError,
    TransportTimestampError,
)
from app.worker_control.transport.repository import (
    InMemoryWorkerTransportSessionRepository,
)
from app.worker_control.transport.service import (
    CHALLENGE_TTL,
    SESSION_TTL,
    WorkerTransportService,
)

NOW = datetime(2026, 7, 24, 12, tzinfo=timezone.utc)


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeDatabase:
    def begin(self) -> FakeTransaction:
        return FakeTransaction()


DATABASE = cast(AsyncSession, FakeDatabase())


class FakeAuthenticator:
    key_version = "key-2026-07"

    def __init__(self, context: AuthenticatedWorkerContext) -> None:
        self.context = context
        self.message_valid = True

    async def active_key_version(
        self, database: AsyncSession, *, worker_id: UUID, now: datetime
    ) -> str:
        del database, now
        if worker_id != self.context.worker_id:
            raise TransportAuthenticationError("authentication failed")
        return self.key_version

    async def authenticate_challenge_response(
        self,
        database: AsyncSession,
        *,
        worker_id: UUID,
        challenge: str,
        authentication_response: str,
        key_version: str,
        now: datetime,
    ) -> AuthenticatedWorkerSessionIdentity:
        if (
            worker_id != self.context.worker_id
            or authentication_response != "valid-proof"
            or key_version != self.key_version
            or not challenge
        ):
            raise TransportAuthenticationError("authentication failed")
        del database
        return AuthenticatedWorkerSessionIdentity(
            context=replace(self.context, authenticated_at=now),
            worker_identity_id=self.context.worker_id,
            credential_id=self.context.worker_id,
            credential_version=1,
        )

    async def validate_session(
        self,
        database: AsyncSession,
        *,
        session: WorkerSession,
        now: datetime,
    ) -> None:
        del database, session, now

    async def verify_message(
        self,
        database,
        *,
        envelope: AuthenticatedMessageEnvelope,
        session: WorkerSession,
    ) -> bool:
        del database
        return self.message_valid and envelope.authentication_proof == "signed"


class FakeWorkerControl:
    def __init__(self, worker: WorkerIdentity) -> None:
        self.worker = worker
        self.heartbeat_calls = 0
        self.result_calls = 0

    async def validate_worker(
        self,
        database: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
    ) -> WorkerIdentity:
        del database
        if (
            worker_context.company_id != self.worker.company_id
            or worker_context.worker_id != self.worker.id
            or worker_context.provider_identifier != self.worker.provider_identifier
        ):
            raise TransportAuthenticationError("worker binding failed")
        return self.worker

    validate_worker_in_transaction = validate_worker

    async def record_heartbeat(
        self,
        database: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        health: WorkerHealth,
        now: datetime,
    ) -> tuple[WorkerIdentity, WorkerHeartbeatRecord]:
        del database, worker_context
        self.heartbeat_calls += 1
        return self.worker, WorkerHeartbeatRecord(
            id=uuid4(),
            company_id=self.worker.company_id,
            worker_id=self.worker.id,
            last_seen=now,
            health=health,
            worker_version=self.worker.version,
            created_at=now,
        )

    record_heartbeat_in_transaction = record_heartbeat

    async def accept_result(
        self,
        database: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        lease_id: UUID,
        expected_version: int,
        result: WorkerExecutionResult,
        correlation_id: UUID,
        now: datetime,
    ) -> WorkerResultRecord:
        del database, expected_version
        assert worker_context.company_id == self.worker.company_id
        self.result_calls += 1
        return WorkerResultRecord(
            id=uuid4(),
            company_id=self.worker.company_id,
            lease_id=lease_id,
            worker_id=self.worker.id,
            execution_id=result.execution_id,
            status=result.status,
            validation_summary=result.validation_summary,
            evidence_summary=result.evidence_summary,
            output_references=result.output_references,
            failure_classification=result.failure_classification,
            correlation_id=correlation_id,
            created_at=now,
        )

    accept_result_in_transaction = accept_result


def worker_identity() -> WorkerIdentity:
    worker_id = uuid4()
    return WorkerIdentity(
        id=worker_id,
        company_id=uuid4(),
        provider_identifier="provider-neutral",
        name="worker",
        worker_version="1.0",
        capabilities=(
            WorkerCapability.ENGINEERING_EXECUTE,
            WorkerCapability.VALIDATION_RUN,
        ),
        registered_at=NOW,
        last_heartbeat_at=NOW,
        lifecycle_state=WorkerLifecycleState.AVAILABLE,
        version=2,
        created_at=NOW,
        updated_at=NOW,
    )


def make_service() -> tuple[
    WorkerTransportService, FakeAuthenticator, FakeWorkerControl
]:
    worker = worker_identity()
    context = AuthenticatedWorkerContext(
        company_id=worker.company_id,
        worker_id=worker.id,
        provider_identifier=worker.provider_identifier,
        authentication_subject=f"worker:{worker.id}",
        authenticated_at=NOW,
    )
    authenticator = FakeAuthenticator(context)
    control = FakeWorkerControl(worker)
    service = WorkerTransportService(
        authenticator=authenticator,
        worker_control=cast(object, control),  # type: ignore[arg-type]
        sessions=InMemoryWorkerTransportSessionRepository(),
    )
    return service, authenticator, control


async def established(
    service: WorkerTransportService,
    control: FakeWorkerControl,
    *,
    capabilities: tuple[WorkerCapability, ...] = (
        WorkerCapability.ENGINEERING_EXECUTE,
    ),
    now: datetime = NOW,
) -> WorkerSession:
    challenge = await service.initiate_session(
        DATABASE, worker_id=control.worker.id, now=now
    )
    return await service.establish_session(
        DATABASE,
        request=WorkerSessionRequest(
            challenge_id=challenge.challenge_id,
            worker_id=challenge.worker_id,
            challenge=challenge.challenge,
            authentication_response="valid-proof",
            capabilities=capabilities,
        ),
        now=now,
    )


def heartbeat_envelope(
    session: WorkerSession,
    *,
    sequence: int = 1,
    sent_at: datetime = NOW,
) -> AuthenticatedMessageEnvelope:
    return AuthenticatedMessageEnvelope(
        message_id=uuid4(),
        session_id=session.session_id,
        worker_id=session.context.worker_id,
        sequence_number=sequence,
        sent_at=sent_at,
        kind=TransportMessageKind.HEARTBEAT,
        payload=HeartbeatMessage(health=WorkerHealth.HEALTHY),
        authentication_proof="signed",
        key_version=session.key_version,
    )


@pytest.mark.asyncio
async def test_challenge_session_contracts_are_immutable_and_secret_safe() -> None:
    service, _, control = make_service()
    challenge = await service.initiate_session(
        DATABASE, worker_id=control.worker.id, now=NOW
    )
    stored = await service.sessions.consume_challenge(
        DATABASE, challenge_id=challenge.challenge_id, now=NOW
    )
    assert stored is not None
    assert challenge.challenge not in stored.challenge_digest
    assert challenge.expires_at == NOW + CHALLENGE_TTL
    with pytest.raises(FrozenInstanceError):
        challenge.worker_id = uuid4()  # type: ignore[misc]


@pytest.mark.asyncio
async def test_session_binds_verified_identity_company_and_capabilities() -> None:
    service, _, control = make_service()
    session = await established(service, control)
    assert session.context.company_id == control.worker.company_id
    assert session.context.worker_id == control.worker.id
    assert session.capabilities == (WorkerCapability.ENGINEERING_EXECUTE,)
    assert session.expires_at == NOW + SESSION_TTL
    assert session.next_sequence == 1

    other_service, other_authenticator, other_control = make_service()
    challenge = await other_service.initiate_session(
        DATABASE, worker_id=other_control.worker.id, now=NOW
    )
    other_authenticator.context = replace(
        other_authenticator.context, company_id=uuid4()
    )
    with pytest.raises(TransportAuthenticationError):
        await other_service.establish_session(
            DATABASE,
            request=WorkerSessionRequest(
                challenge_id=challenge.challenge_id,
                worker_id=challenge.worker_id,
                challenge=challenge.challenge,
                authentication_response="valid-proof",
                capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
            ),
            now=NOW,
        )


@pytest.mark.asyncio
async def test_challenge_replay_expiration_and_capability_expansion_fail_closed() -> (
    None
):
    service, _, control = make_service()
    challenge = await service.initiate_session(
        DATABASE, worker_id=control.worker.id, now=NOW
    )
    request = WorkerSessionRequest(
        challenge_id=challenge.challenge_id,
        worker_id=control.worker.id,
        challenge=challenge.challenge,
        authentication_response="valid-proof",
        capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
    )
    await service.establish_session(DATABASE, request=request, now=NOW)
    with pytest.raises(TransportReplayError):
        await service.establish_session(DATABASE, request=request, now=NOW)

    expired = await service.initiate_session(
        DATABASE, worker_id=control.worker.id, now=NOW
    )
    with pytest.raises(TransportChallengeError):
        await service.establish_session(
            DATABASE,
            request=replace(
                request,
                challenge_id=expired.challenge_id,
                challenge=expired.challenge,
            ),
            now=NOW + CHALLENGE_TTL,
        )

    capability = await service.initiate_session(
        DATABASE, worker_id=control.worker.id, now=NOW
    )
    with pytest.raises(TransportCapabilityError):
        await service.establish_session(
            DATABASE,
            request=replace(
                request,
                challenge_id=capability.challenge_id,
                challenge=capability.challenge,
                capabilities=(WorkerCapability.REVIEW_PACKAGE,),
            ),
            now=NOW,
        )


@pytest.mark.asyncio
async def test_heartbeat_is_authenticated_ordered_and_idempotent() -> None:
    service, _, control = make_service()
    session = await established(service, control)
    envelope = heartbeat_envelope(session)
    first = await service.handle_message(DATABASE, envelope=envelope, now=NOW)
    replay = await service.handle_message(DATABASE, envelope=envelope, now=NOW)
    assert first.duplicate is False
    assert replay.duplicate is True
    assert replay.outcome_reference == first.outcome_reference
    assert control.heartbeat_calls == 1

    with pytest.raises(TransportSequenceError):
        await service.handle_message(
            DATABASE,
            envelope=heartbeat_envelope(session, sequence=3),
            now=NOW,
        )


@pytest.mark.asyncio
async def test_message_identity_timestamp_session_and_key_fail_closed() -> None:
    service, authenticator, control = make_service()
    session = await established(service, control)
    base = heartbeat_envelope(session)
    cases = (
        (
            replace(base, worker_id=uuid4()),
            NOW,
            TransportBindingError,
        ),
        (
            replace(base, sent_at=NOW - timedelta(minutes=3)),
            NOW,
            TransportTimestampError,
        ),
        (
            replace(base, key_version="retired-key"),
            NOW,
            TransportAuthenticationError,
        ),
    )
    for envelope, now, error in cases:
        with pytest.raises(error):
            await service.handle_message(DATABASE, envelope=envelope, now=now)

    authenticator.message_valid = False
    with pytest.raises(TransportAuthenticationError):
        await service.handle_message(DATABASE, envelope=base, now=NOW)
    authenticator.message_valid = True
    with pytest.raises(TransportSessionError):
        await service.handle_message(
            DATABASE,
            envelope=base,
            now=NOW + SESSION_TTL,
        )


@pytest.mark.asyncio
async def test_message_id_reuse_with_changed_content_is_rejected() -> None:
    service, _, control = make_service()
    session = await established(service, control)
    first = heartbeat_envelope(session)
    await service.handle_message(DATABASE, envelope=first, now=NOW)
    with pytest.raises(TransportReplayError):
        await service.handle_message(
            DATABASE,
            envelope=replace(first, payload=HeartbeatMessage(WorkerHealth.DEGRADED)),
            now=NOW,
        )


@pytest.mark.asyncio
async def test_result_binds_worker_lease_capability_and_remains_disconnected() -> None:
    service, _, control = make_service()
    session = await established(service, control)
    execution_id = uuid4()
    result = WorkerExecutionResult(
        execution_id=execution_id,
        worker_id=control.worker.id,
        status=WorkerResultStatus.NOT_EXECUTED,
        validation_summary=MappingProxyType({}),
        evidence_summary=MappingProxyType({"repository_mutated": False}),
        output_references=(),
        failure_classification=WorkerFailureClassification.EXECUTION_NOT_CONNECTED,
    )
    message = AuthenticatedMessageEnvelope(
        message_id=uuid4(),
        session_id=session.session_id,
        worker_id=control.worker.id,
        sequence_number=1,
        sent_at=NOW,
        kind=TransportMessageKind.RESULT,
        payload=ResultMessage(
            lease_id=uuid4(),
            expected_lease_version=1,
            capability=WorkerCapability.ENGINEERING_EXECUTE,
            correlation_id=uuid4(),
            result=result,
        ),
        authentication_proof="signed",
        key_version=session.key_version,
    )
    receipt = await service.handle_message(DATABASE, envelope=message, now=NOW)
    assert receipt.outcome_reference.startswith("result:")
    assert control.result_calls == 1

    service2, _, control2 = make_service()
    session2 = await established(
        service2,
        control2,
        capabilities=(WorkerCapability.VALIDATION_RUN,),
    )
    with pytest.raises(TransportCapabilityError):
        await service2.handle_message(
            DATABASE,
            envelope=replace(
                message,
                session_id=session2.session_id,
                worker_id=control2.worker.id,
                payload=replace(
                    cast(ResultMessage, message.payload),
                    result=replace(result, worker_id=control2.worker.id),
                ),
            ),
            now=NOW,
        )
