import hmac
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_execution.composition.errors import ExecutionCompositionError
from app.engineering_execution.composition.records import CompositionDeliveryPackage
from app.engineering_execution.composition.service import (
    ExecutionCompositionService,
    RecordProviderResult,
)
from app.engineering_execution.controlled.contracts import ControlledOutcome
from app.engineering_execution.controlled.errors import ControlledExecutionError
from app.engineering_execution.controlled.service import ControlledExecutionService
from app.platform.auth.tokens import SecurityTokenService
from app.worker_control.contracts import (
    AuthenticatedWorkerContext,
    WorkerCapability,
)
from app.worker_control.service import WorkerControlService
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    CancellationAcknowledgementMessage,
    CompositionAcknowledgementMessage,
    CompositionFetchMessage,
    ControlledExecutionResultMessage,
    ControlledOfferAcquisitionMessage,
    HeartbeatMessage,
    LeaseRenewalMessage,
    ProviderProgressMessage,
    ProviderResultMessage,
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
from app.worker_control.transport.persistence.repository import (
    PostgreSQLWorkerTransportSessionRepository,
)
from app.worker_control.transport.repository import (
    StoredChallenge,
    WorkerTransportSessionRepository,
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
        compositions: ExecutionCompositionService | None = None,
        controlled: ControlledExecutionService | None = None,
    ) -> None:
        self.authenticator = authenticator
        self.sessions = sessions or PostgreSQLWorkerTransportSessionRepository()
        self.worker_control = worker_control or WorkerControlService()
        self.tokens = tokens or SecurityTokenService()
        self.compositions = compositions or ExecutionCompositionService()
        self.controlled = controlled or ControlledExecutionService(
            workers=self.worker_control
        )

    async def initiate_session(
        self,
        database: AsyncSession,
        *,
        worker_id: UUID,
        now: datetime | None = None,
    ) -> WorkerSessionChallenge:
        issued_at = now or utc_now()
        raw_challenge = self.tokens.generate_token()
        async with database.begin():
            key_version = await self.authenticator.active_key_version(
                database, worker_id=worker_id, now=issued_at
            )
            challenge = WorkerSessionChallenge(
                challenge_id=uuid4(),
                worker_id=worker_id,
                challenge=raw_challenge,
                issued_at=issued_at,
                expires_at=issued_at + CHALLENGE_TTL,
                key_version=key_version,
            )
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
            authenticated = await self.authenticator.authenticate_challenge_response(
                database,
                worker_id=request.worker_id,
                challenge=request.challenge,
                authentication_response=request.authentication_response,
                key_version=challenge.key_version,
                now=established_at,
            )
            if authenticated.context.worker_id != request.worker_id:
                raise TransportBindingError(
                    "Authenticated worker identity does not match."
                )
            worker = await self.worker_control.validate_worker_in_transaction(
                database, worker_context=authenticated.context
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
                context=authenticated.context,
                worker_identity_id=authenticated.worker_identity_id,
                credential_id=authenticated.credential_id,
                credential_version=authenticated.credential_version,
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
            await self.authenticator.validate_session(
                database, session=session, now=accepted_at
            )
            if not await self.authenticator.verify_message(
                database, envelope=envelope, session=session
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

    async def validate_authenticated_session_in_transaction(
        self,
        database: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        session_id: UUID,
        now: datetime | None = None,
    ) -> WorkerSession:
        """Validate a bound session inside the caller-owned transaction."""
        checked_at = now or utc_now()
        session = await self.sessions.get_session(database, session_id)
        if (
            session is None
            or session.context.company_id != context.company_id
            or session.context.worker_id != context.worker_id
            or session.context.provider_identifier != context.provider_identifier
            or session.state is not WorkerSessionState.ACTIVE
            or session.expires_at <= checked_at
        ):
            raise TransportBindingError("Worker session was not found.")
        await self.authenticator.validate_session(
            database, session=session, now=checked_at
        )
        return session

    async def authenticate_http_session(
        self,
        database: AsyncSession,
        *,
        session_id: UUID,
        now: datetime | None = None,
    ) -> WorkerSession:
        checked_at = now or utc_now()
        async with database.begin():
            session = await self.sessions.get_session(database, session_id)
            if (
                session is None
                or session.state is not WorkerSessionState.ACTIVE
                or session.expires_at <= checked_at
            ):
                raise TransportSessionError("Worker session was not found.")
            await self.authenticator.validate_session(
                database, session=session, now=checked_at
            )
            return session

    async def _dispatch(
        self,
        database: AsyncSession,
        *,
        envelope: AuthenticatedMessageEnvelope,
        session: WorkerSession,
    ) -> str:
        try:
            return await self._dispatch_composition(
                database, envelope=envelope, session=session
            )
        except (ExecutionCompositionError, ControlledExecutionError) as error:
            raise TransportMessageError(str(error)) from error

    async def _dispatch_composition(
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
        if envelope.kind is TransportMessageKind.LEASE_RENEWAL:
            if not isinstance(payload, LeaseRenewalMessage):
                raise TransportMessageError("Lease renewal payload is invalid.")
            lease = await self.worker_control.renew_lease_in_transaction(
                database,
                worker_context=session.context,
                lease_id=payload.lease_id,
                expected_version=payload.expected_lease_version,
                lease_seconds=payload.lease_seconds,
                now=envelope.sent_at,
            )
            return f"lease:{lease.id}:version:{lease.version}"
        if envelope.kind is TransportMessageKind.COMPOSITION_FETCH:
            if not isinstance(payload, CompositionFetchMessage):
                raise TransportMessageError("Composition fetch payload is invalid.")
            if WorkerCapability.ENGINEERING_EXECUTE not in session.capabilities:
                raise TransportCapabilityError("Session lacks execution capability.")
            package = await self.compositions.deliver_next_in_transaction(
                database,
                worker_context=session.context,
                now=envelope.sent_at,
            )
            return (
                "composition:none"
                if package is None
                else f"composition:{package.composition.id}"
            )
        if envelope.kind is TransportMessageKind.COMPOSITION_ACKNOWLEDGEMENT:
            if not isinstance(payload, CompositionAcknowledgementMessage):
                raise TransportMessageError(
                    "Composition acknowledgement payload is invalid."
                )
            composition = (
                await self.compositions.acknowledge_composition_in_transaction(
                    database,
                    worker_context=session.context,
                    composition_id=payload.composition_id,
                    composition_digest=payload.composition_digest,
                    instruction_digest=payload.instruction_digest,
                    request_digest=payload.request_digest,
                    now=envelope.sent_at,
                )
            )
            return f"composition_acknowledged:{composition.id}"
        if envelope.kind is TransportMessageKind.PROVIDER_PROGRESS:
            if not isinstance(payload, ProviderProgressMessage):
                raise TransportMessageError("Provider progress payload is invalid.")
            if WorkerCapability.ENGINEERING_EXECUTE not in session.capabilities:
                raise TransportCapabilityError("Session lacks execution capability.")
            progress = await self.compositions.append_progress_in_transaction(
                database,
                worker_context=session.context,
                attempt_id=payload.attempt_id,
                lease_id=payload.lease_id,
                composition_digest=payload.composition_digest,
                instruction_digest=payload.instruction_digest,
                request_digest=payload.request_digest,
                phase=payload.phase,
                message_code=payload.message_code,
                summary=payload.summary,
                percentage=payload.percentage,
                now=envelope.sent_at,
            )
            return (
                f"provider_progress:{progress.id}:sequence:{progress.sequence_number}"
            )
        if envelope.kind is TransportMessageKind.PROVIDER_RESULT:
            if not isinstance(payload, ProviderResultMessage):
                raise TransportMessageError("Provider result payload is invalid.")
            if WorkerCapability.ENGINEERING_EXECUTE not in session.capabilities:
                raise TransportCapabilityError("Session lacks execution capability.")
            provider_result = await self.compositions.record_result_in_transaction(
                database,
                worker_context=session.context,
                lease_id=payload.lease_id,
                composition_digest=payload.composition_digest,
                instruction_digest=payload.instruction_digest,
                request_digest=payload.request_digest,
                command=RecordProviderResult(
                    attempt_id=payload.attempt_id,
                    status=payload.status,
                    evidence_summary=payload.evidence_summary,
                    validation_summary=payload.validation_summary,
                    output_references=payload.output_references,
                    failure_classification=payload.failure_classification,
                    repository_mutated=payload.repository_mutated,
                ),
                now=envelope.sent_at,
            )
            return (
                f"provider_result:{provider_result.id}:"
                f"{provider_result.disposition.value}"
            )
        if envelope.kind is TransportMessageKind.CANCELLATION_ACKNOWLEDGEMENT:
            if not isinstance(payload, CancellationAcknowledgementMessage):
                raise TransportMessageError(
                    "Cancellation acknowledgement payload is invalid."
                )
            attempt = await self.compositions.acknowledge_cancellation_in_transaction(
                database,
                worker_context=session.context,
                attempt_id=payload.attempt_id,
                lease_id=payload.lease_id,
                expected_version=payload.expected_version,
                composition_digest=payload.composition_digest,
                now=envelope.sent_at,
            )
            return f"cancellation_acknowledged:{attempt.id}:version:{attempt.version}"
        if envelope.kind is TransportMessageKind.CONTROLLED_OFFER_ACQUISITION:
            if not isinstance(payload, ControlledOfferAcquisitionMessage):
                raise TransportMessageError(
                    "Controlled acquisition payload is invalid."
                )
            if WorkerCapability.ENGINEERING_EXECUTE not in session.capabilities:
                raise TransportCapabilityError("Session lacks execution capability.")
            offer = await self.controlled.acquire_in_transaction(
                database,
                worker_context=session.context,
                session_id=session.session_id,
                offer_id=payload.offer_id,
                now=envelope.sent_at,
            )
            return f"controlled_offer:{offer.id}:lease:{offer.lease_id}"
        if envelope.kind is TransportMessageKind.CONTROLLED_EXECUTION_RESULT:
            if not isinstance(payload, ControlledExecutionResultMessage):
                raise TransportMessageError("Controlled result payload is invalid.")
            if WorkerCapability.ENGINEERING_EXECUTE not in session.capabilities:
                raise TransportCapabilityError("Session lacks execution capability.")
            try:
                outcome = ControlledOutcome(payload.outcome)
            except ValueError as error:
                raise TransportMessageError(
                    "Controlled result outcome is invalid."
                ) from error
            controlled_result = await self.controlled.complete_in_transaction(
                database,
                worker_context=session.context,
                session_id=session.session_id,
                offer_id=payload.offer_id,
                lease_id=payload.lease_id,
                outcome=outcome,
                output=payload.output,
                error_classification=payload.error_classification,
                started_at=payload.started_at,
                completed_at=payload.completed_at,
            )
            return (
                f"controlled_result:{controlled_result.id}:"
                f"offer:{controlled_result.offer_id}"
            )
        raise TransportMessageError("Unsupported transport message kind.")

    async def delivery_package(
        self,
        database: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        composition_id: UUID,
    ) -> CompositionDeliveryPackage | None:
        return await self.compositions.get_delivery_package(
            database,
            worker_context=context,
            composition_id=composition_id,
        )

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
