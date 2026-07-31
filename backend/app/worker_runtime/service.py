import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.worker_control.contracts import WorkerCapability, WorkerHealth
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    ControlledExecutionResultMessage,
    ControlledOfferAcquisitionMessage,
    HeartbeatMessage,
    LeaseRenewalMessage,
    TransportMessageKind,
    WorkstreamAcknowledgementMessage,
    WorkstreamRuntimeUpdateMessage,
)
from app.worker_control.transport.crypto import (
    canonical_message,
    decode_private_key,
    encode_signature,
)
from app.worker_runtime.client import Session, WorkerTransportClient
from app.worker_runtime.config import WorkerRuntimeConfig
from app.worker_runtime.execution import (
    IsolatedWorkspaceExecutionError,
    IsolatedWorkspaceExecutor,
)


class WorkerRuntimeState(StrEnum):
    STOPPED = "stopped"
    AUTHENTICATING = "authenticating"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    CLOSED = "closed"


@dataclass(frozen=True)
class WorkerRuntimeSnapshot:
    state: WorkerRuntimeState
    session_id: UUID | None
    session_expires_at: datetime | None
    next_sequence: int
    last_heartbeat_at: datetime | None


class AuthenticatedWorkerRuntime:
    """Own only worker authentication, session continuity, heartbeats, and leases."""

    def __init__(
        self,
        *,
        config: WorkerRuntimeConfig,
        client: WorkerTransportClient,
        private_key: Ed25519PrivateKey,
    ) -> None:
        self.config = config
        self.client = client
        self.private_key = private_key
        self._session: Session | None = None
        self._state = WorkerRuntimeState.STOPPED
        self._last_heartbeat_at: datetime | None = None
        self._workstream_versions: dict[UUID, int] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def production(cls, config: WorkerRuntimeConfig) -> "AuthenticatedWorkerRuntime":
        return cls(
            config=config,
            client=WorkerTransportClient(
                base_url=config.base_url,
                timeout_seconds=config.request_timeout_seconds,
            ),
            private_key=decode_private_key(config.read_private_key()),
        )

    @property
    def snapshot(self) -> WorkerRuntimeSnapshot:
        return WorkerRuntimeSnapshot(
            state=self._state,
            session_id=self._session.session_id if self._session else None,
            session_expires_at=self._session.expires_at if self._session else None,
            next_sequence=self._session.next_sequence if self._session else 0,
            last_heartbeat_at=self._last_heartbeat_at,
        )

    async def establish(self) -> WorkerRuntimeSnapshot:
        async with self._lock:
            self._state = WorkerRuntimeState.AUTHENTICATING
            challenge = await self.client.challenge(self.config.worker_id)
            proof = encode_signature(
                self.private_key.sign(challenge.challenge.encode())
            )
            self._session = await self.client.establish(
                worker_id=self.config.worker_id,
                challenge=challenge,
                proof=proof,
                capabilities=self.config.capabilities,
            )
            self._state = WorkerRuntimeState.CONNECTED
            return self.snapshot

    async def heartbeat(
        self, health: WorkerHealth = WorkerHealth.HEALTHY
    ) -> WorkerRuntimeSnapshot:
        async with self._lock:
            session = self._require_session()
            sent_at = datetime.now(timezone.utc)
            envelope = self._envelope(
                session=session,
                sent_at=sent_at,
                kind=TransportMessageKind.HEARTBEAT,
                payload=HeartbeatMessage(health=health),
            )
            await self.client.heartbeat(
                session_id=session.session_id,
                payload={
                    "message_id": str(envelope.message_id),
                    "session_id": str(envelope.session_id),
                    "sequence_number": envelope.sequence_number,
                    "sent_at": envelope.sent_at.isoformat(),
                    "authentication_proof": envelope.authentication_proof,
                    "key_version": envelope.key_version,
                    "health": health.value,
                },
            )
            self._advance(sent_at)
            return self.snapshot

    async def renew_lease(
        self,
        *,
        lease_id: UUID,
        expected_version: int,
        lease_seconds: int,
    ) -> WorkerRuntimeSnapshot:
        async with self._lock:
            session = self._require_session()
            sent_at = datetime.now(timezone.utc)
            payload = LeaseRenewalMessage(
                lease_id=lease_id,
                expected_lease_version=expected_version,
                lease_seconds=lease_seconds,
            )
            envelope = self._envelope(
                session=session,
                sent_at=sent_at,
                kind=TransportMessageKind.LEASE_RENEWAL,
                payload=payload,
            )
            await self.client.renew_lease(
                session_id=session.session_id,
                payload={
                    "message_id": str(envelope.message_id),
                    "session_id": str(envelope.session_id),
                    "sequence_number": envelope.sequence_number,
                    "sent_at": envelope.sent_at.isoformat(),
                    "authentication_proof": envelope.authentication_proof,
                    "key_version": envelope.key_version,
                    "lease_id": str(lease_id),
                    "expected_lease_version": expected_version,
                    "lease_seconds": lease_seconds,
                },
            )
            self._advance(sent_at)
            return self.snapshot

    async def run(self, stop: asyncio.Event) -> None:
        try:
            await self.establish()
            while not stop.is_set():
                await self.heartbeat()
                if WorkerCapability.ENGINEERING_EXECUTE in self.config.capabilities:
                    await self.consume_workstream_control()
                    await self.execute_available_offer()
                try:
                    await asyncio.wait_for(
                        stop.wait(), timeout=self.config.heartbeat_seconds
                    )
                except TimeoutError:
                    continue
        except Exception:
            self._state = WorkerRuntimeState.DEGRADED
            raise
        finally:
            await self.close()

    async def execute_available_offer(self) -> bool:
        async with self._lock:
            session = self._require_session()
            offers = await self.client.poll_offers(session_id=session.session_id)
            if not offers:
                return False
            offered = offers[0]
            sent_at = datetime.now(timezone.utc)
            acquisition = ControlledOfferAcquisitionMessage(
                offer_id=UUID(str(offered["offer_id"]))
            )
            envelope = self._envelope(
                session=session,
                sent_at=sent_at,
                kind=TransportMessageKind.CONTROLLED_OFFER_ACQUISITION,
                payload=acquisition,
            )
            acquired = await self.client.acquire_offer(
                session_id=session.session_id,
                payload={
                    "message_id": str(envelope.message_id),
                    "session_id": str(envelope.session_id),
                    "sequence_number": envelope.sequence_number,
                    "sent_at": envelope.sent_at.isoformat(),
                    "authentication_proof": envelope.authentication_proof,
                    "key_version": envelope.key_version,
                    "offer_id": str(acquisition.offer_id),
                },
            )
            self._advance(sent_at)
            started_at = datetime.now(timezone.utc)
            command_id = UUID(str(offered["command_id"]))
            if command_id in self._workstream_versions:
                await self._publish_workstream_state(
                    command_id=command_id,
                    state="running",
                    health="healthy",
                    progress=0,
                    activity="Executing controlled workstream",
                )
            outcome = "succeeded"
            failure = None
            try:
                assert self.config.workspace_root is not None
                output = IsolatedWorkspaceExecutor(self.config.workspace_root).execute(
                    acquired
                )
            except IsolatedWorkspaceExecutionError:
                outcome = "failed"
                failure = "workspace_validation_failed"
                output = {"repository_mutated": False}
            completed_at = datetime.now(timezone.utc)
            current = self._require_session()
            result_payload = ControlledExecutionResultMessage(
                offer_id=acquired.offer_id,
                lease_id=acquired.lease_id,
                outcome=outcome,
                output=output,
                error_classification=failure,
                started_at=started_at,
                completed_at=completed_at,
            )
            result_envelope = self._envelope(
                session=current,
                sent_at=completed_at,
                kind=TransportMessageKind.CONTROLLED_EXECUTION_RESULT,
                payload=result_payload,
            )
            await self.client.submit_controlled_result(
                session_id=current.session_id,
                payload={
                    "message_id": str(result_envelope.message_id),
                    "session_id": str(result_envelope.session_id),
                    "sequence_number": result_envelope.sequence_number,
                    "sent_at": result_envelope.sent_at.isoformat(),
                    "authentication_proof": result_envelope.authentication_proof,
                    "key_version": result_envelope.key_version,
                    "offer_id": str(acquired.offer_id),
                    "lease_id": str(acquired.lease_id),
                    "outcome": outcome,
                    "output": output,
                    "error_classification": failure,
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                },
            )
            self._advance(completed_at)
            if command_id in self._workstream_versions:
                await self._publish_workstream_state(
                    command_id=command_id,
                    state="completed" if outcome == "succeeded" else "failed",
                    health="healthy" if outcome == "succeeded" else "degraded",
                    progress=100 if outcome == "succeeded" else None,
                    activity="Controlled execution completed"
                    if outcome == "succeeded"
                    else "Controlled execution failed",
                    reason_code=failure,
                )
            return True

    async def consume_workstream_control(self) -> bool:
        async with self._lock:
            session = self._require_session()
            controls = await self.client.poll_workstream_controls(
                session_id=session.session_id
            )
            if not controls:
                return False
            control = controls[0]
            sent_at = datetime.now(timezone.utc)
            action = str(control["action"])
            message = WorkstreamAcknowledgementMessage(
                control_id=UUID(str(control["control_id"])),
                expected_control_version=int(str(control["version"])),
                action=action,
                idempotency_key=f"ack:{control['control_id']}:{control['version']}:{session.session_id}",
                reason_code=None,
            )
            envelope = self._envelope(
                session=session,
                sent_at=sent_at,
                kind=TransportMessageKind.WORKSTREAM_ACKNOWLEDGEMENT,
                payload=message,
            )
            runtime_version = await self.client.acknowledge_workstream_control(
                session_id=session.session_id,
                payload={
                    "message_id": str(envelope.message_id),
                    "session_id": str(envelope.session_id),
                    "sequence_number": envelope.sequence_number,
                    "sent_at": envelope.sent_at.isoformat(),
                    "authentication_proof": envelope.authentication_proof,
                    "key_version": envelope.key_version,
                    "control_id": str(message.control_id),
                    "expected_control_version": message.expected_control_version,
                    "action": action,
                    "idempotency_key": message.idempotency_key,
                    "reason_code": message.reason_code,
                },
            )
            self._advance(sent_at)
            self._workstream_versions[UUID(str(control["command_id"]))] = (
                runtime_version
            )
            return True

    async def _publish_workstream_state(
        self,
        *,
        command_id: UUID,
        state: str,
        health: str,
        progress: int | None,
        activity: str,
        reason_code: str | None = None,
    ) -> None:
        session = self._require_session()
        sent_at = datetime.now(timezone.utc)
        expected = self._workstream_versions[command_id]
        message = WorkstreamRuntimeUpdateMessage(
            command_id=command_id,
            expected_runtime_version=expected,
            runtime_state=state,
            worker_health=health,
            progress_percent=progress,
            current_activity=activity,
            reason_code=reason_code,
            idempotency_key=f"runtime:{command_id}:{expected}:{state}",
        )
        envelope = self._envelope(
            session=session,
            sent_at=sent_at,
            kind=TransportMessageKind.WORKSTREAM_RUNTIME_UPDATE,
            payload=message,
        )
        version = await self.client.publish_workstream_runtime(
            session_id=session.session_id,
            payload={
                "message_id": str(envelope.message_id),
                "session_id": str(envelope.session_id),
                "sequence_number": envelope.sequence_number,
                "sent_at": envelope.sent_at.isoformat(),
                "authentication_proof": envelope.authentication_proof,
                "key_version": envelope.key_version,
                "command_id": str(command_id),
                "expected_runtime_version": expected,
                "runtime_state": state,
                "worker_health": health,
                "progress_percent": progress,
                "current_activity": activity,
                "reason_code": reason_code,
                "idempotency_key": message.idempotency_key,
            },
        )
        self._advance(sent_at)
        self._workstream_versions[command_id] = version

    async def close(self) -> None:
        await self.client.close()
        self._session = None
        self._state = WorkerRuntimeState.CLOSED

    def _envelope(
        self,
        *,
        session: Session,
        sent_at: datetime,
        kind: TransportMessageKind,
        payload: (
            HeartbeatMessage
            | LeaseRenewalMessage
            | ControlledOfferAcquisitionMessage
            | ControlledExecutionResultMessage
            | WorkstreamAcknowledgementMessage
            | WorkstreamRuntimeUpdateMessage
        ),
    ) -> AuthenticatedMessageEnvelope:
        unsigned = AuthenticatedMessageEnvelope(
            message_id=uuid4(),
            session_id=session.session_id,
            worker_id=self.config.worker_id,
            sequence_number=session.next_sequence,
            sent_at=sent_at,
            kind=kind,
            payload=payload,
            authentication_proof="",
            key_version=session.key_version,
        )
        return AuthenticatedMessageEnvelope(
            **{
                **unsigned.__dict__,
                "authentication_proof": encode_signature(
                    self.private_key.sign(canonical_message(unsigned))
                ),
            }
        )

    def _advance(self, occurred_at: datetime) -> None:
        session = self._require_session()
        self._session = Session(
            session_id=session.session_id,
            key_version=session.key_version,
            next_sequence=session.next_sequence + 1,
            expires_at=session.expires_at,
        )
        self._last_heartbeat_at = occurred_at

    def _require_session(self) -> Session:
        if self._session is None or self._state is not WorkerRuntimeState.CONNECTED:
            raise RuntimeError("Worker runtime is not connected.")
        return self._session
