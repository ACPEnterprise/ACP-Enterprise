from datetime import datetime, timedelta, timezone
import hmac
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.tokens import SecurityTokenService
from app.worker_control.service import WorkerControlService
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    HeartbeatMessage,
    ResultMessage,
    TransportMessageKind,
    TransportReceipt,
    WorkerMessageAuthenticator,
    WorkerSession,
    WorkerSessionChallenge,
    WorkerSessionRequest,
    WorkerSessionState,
)
from app.worker_control.transport.errors import (
    TransportAuthenticationError,
    TransportBindingError,
    TransportCapabilityError,
    TransportChallengeError,
    TransportMessageError,
    TransportReplayError,
    TransportSequenceError,
    TransportSessionError,
    TransportTimestampError,
)
from app.worker_control.transport.repository import (
    StoredChallenge,
    WorkerTransportSessionRepository,
)
from app.worker_control.transport.persistence.repository import (
    PostgreSQLWorkerTransportSessionRepository,
)

CHALLENGE_TTL = timedelta(minutes=2)
SESSION_TTL = timedelta(minutes=15)
MESSAGE_CLOCK_SKEW = timedelta(minutes=2)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkerTransportService:
    def __init__(
        self,
        *,
        authenticator: WorkerMessageAuthenticator,
        sessions: WorkerTransportSessionRepository | None = None,
        worker_control: WorkerControlService | None = None,
        tokens: SecurityTokenService | None = None,
    ) -> None:
        self.authenticator = authenticator
        self.sessions = sessions or PostgreSQLWorkerTransportSessionRepository()
        self.worker_control = worker_control or WorkerControlService()
        self.tokens = tokens or SecurityTokenService()

    async def initiate_session(
        self,
        database: AsyncSession,
        *,
        worker_id: UUID,
        now: datetime | None = None,
    ) -> WorkerSessionChallenge:
        issued_at = now or utc_now()
        raw_challenge = self.tokens.generate_token()
        challenge = WorkerSessionChallenge(
            challenge_id=uuid4(),
            worker_id=worker_id,
            challenge=raw_challenge,
            issued_at=issued_at,
            expires_at=issued_at + CHALLENGE_TTL,
            key_version=self.authenticator.active_key_version,
        )
        async with database.begin():
            await self.sessions.add_challenge(
                database,
                StoredChallenge(
                    challenge_id=challenge.challenge_id,
                    worker_id=worker_id,
                    challenge_digest=self.tokens.hash_token(raw_challenge),
                    issued_at=issued_at,
                    expires_at=challenge.expires_at,
                    key_version=challenge.key_version,
                ),
            )
        return challenge

    async def establish_session(
        self,
        database: AsyncSession,
        *,
        request: WorkerSessionRequest,
        now: datetime | None = None,
    ) -> WorkerSession:
        established_at = now or utc_now()
        async with database.begin():
            challenge = await self.sessions.consume_challenge(
                database, challenge_id=request.challenge_id, now=established_at
            )
            if challenge is None:
                raise TransportReplayError("Challenge is missing or already consumed.")
            if challenge.expires_at <= established_at:
                raise TransportChallengeError("Challenge has expired.")
            if challenge.worker_id != request.worker_id:
                raise TransportBindingError("Challenge worker identity does not match.")
            if not hmac.compare_digest(
                self.tokens.hash_token(request.challenge), challenge.challenge_digest
            ):
                raise TransportAuthenticationError("Challenge response is invalid.")
            context = await self.authenticator.authenticate_challenge_response(
                worker_id=request.worker_id,
                authentication_response=request.authentication_response,
                key_version=challenge.key_version,
                now=established_at,
            )
            if context.worker_id != request.worker_id:
                raise TransportBindingError(
                    "Authenticated worker identity does not match."
                )
            worker = await self.worker_control.validate_worker_in_transaction(
                database, worker_context=context
            )
            requested = tuple(
                sorted(
                    set(request.capabilities), key=lambda capability: capability.value
                )
            )
            if not requested:
                raise TransportCapabilityError("At least one capability is required.")
            if not set(requested).issubset(set(worker.capabilities)):
                raise TransportCapabilityError("Worker cannot expand its capabilities.")
            session = WorkerSession(
                session_id=uuid4(),
                context=context,
                capabilities=requested,
                key_version=challenge.key_version,
                state=WorkerSessionState.ACTIVE,
                established_at=established_at,
                expires_at=established_at + SESSION_TTL,
                next_sequence=1,
            )
            await self.sessions.add_session(database, session)
        return session

    async def handle_message(
        self,
        database: AsyncSession,
        *,
        envelope: AuthenticatedMessageEnvelope,
        now: datetime | None = None,
    ) -> TransportReceipt:
        accepted_at = now or utc_now()
        async with database.begin():
            session = await self.sessions.get_session(database, envelope.session_id)
            if session is None:
                raise TransportSessionError("Worker session was not found.")
            self._validate_envelope(envelope, session=session, now=accepted_at)
            if not await self.authenticator.verify_message(
                envelope=envelope, session=session
            ):
                raise TransportAuthenticationError("Message authentication failed.")
            try:
                current, duplicate = await self.sessions.accept_sequence(
                    database, envelope=envelope, now=accepted_at
                )
            except ValueError as error:
                raise TransportReplayError(str(error)) from error
            if duplicate is not None:
                return TransportReceipt(
                    message_id=duplicate.message_id,
                    sequence_number=duplicate.sequence_number,
                    accepted_at=duplicate.accepted_at,
                    duplicate=True,
                    outcome_reference=duplicate.outcome_reference,
                )
            if current is None or current.state is not WorkerSessionState.ACTIVE:
                raise TransportSessionError("Worker session is expired or invalid.")
            if envelope.sequence_number != current.next_sequence:
                raise TransportSequenceError("Message sequence is out of order.")

            outcome = await self._dispatch(database, envelope=envelope, session=current)
            receipt = TransportReceipt(
                message_id=envelope.message_id,
                sequence_number=envelope.sequence_number,
                accepted_at=accepted_at,
                duplicate=False,
                outcome_reference=outcome,
            )
            await self.sessions.store_receipt(
                database, envelope=envelope, receipt=receipt
            )
        return receipt

    async def _dispatch(
        self,
        database: AsyncSession,
        *,
        envelope: AuthenticatedMessageEnvelope,
        session: WorkerSession,
    ) -> str:
        payload = envelope.payload
        if envelope.kind is TransportMessageKind.HEARTBEAT:
            if not isinstance(payload, HeartbeatMessage):
                raise TransportMessageError("Heartbeat payload is invalid.")
            (
                worker,
                heartbeat,
            ) = await self.worker_control.record_heartbeat_in_transaction(
                database,
                worker_context=session.context,
                health=payload.health,
                now=envelope.sent_at,
            )
            return f"heartbeat:{heartbeat.id}:worker:{worker.id}"
        if envelope.kind is TransportMessageKind.RESULT:
            if not isinstance(payload, ResultMessage):
                raise TransportMessageError("Result payload is invalid.")
            if payload.capability not in session.capabilities:
                raise TransportCapabilityError("Session lacks result capability.")
            if payload.result.worker_id != session.context.worker_id:
                raise TransportBindingError("Result worker identity does not match.")
            record = await self.worker_control.accept_result_in_transaction(
                database,
                worker_context=session.context,
                lease_id=payload.lease_id,
                expected_version=payload.expected_lease_version,
                result=payload.result,
                correlation_id=payload.correlation_id,
                now=envelope.sent_at,
            )
            return f"result:{record.id}:lease:{record.lease_id}"
        raise TransportMessageError("Unsupported transport message kind.")

    @staticmethod
    def _validate_envelope(
        envelope: AuthenticatedMessageEnvelope,
        *,
        session: WorkerSession,
        now: datetime,
    ) -> None:
        if session.state is not WorkerSessionState.ACTIVE or session.expires_at <= now:
            raise TransportSessionError("Worker session has expired.")
        if envelope.worker_id != session.context.worker_id:
            raise TransportBindingError("Envelope worker identity does not match.")
        if envelope.key_version != session.key_version:
            raise TransportAuthenticationError("Message key version does not match.")
        if envelope.sequence_number < 1:
            raise TransportSequenceError("Message sequence is invalid.")
        if abs(now - envelope.sent_at) > MESSAGE_CLOCK_SKEW:
            raise TransportTimestampError(
                "Message timestamp is outside allowed bounds."
            )
        if not envelope.authentication_proof.strip():
            raise TransportAuthenticationError("Message authentication is missing.")
