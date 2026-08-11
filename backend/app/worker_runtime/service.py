import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import cast
from uuid import UUID, uuid4

import httpx
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
from app.worker_runtime.client import (
    Session,
    WorkerRuntimeTransportError,
    WorkerTransportClient,
)
from app.worker_runtime.config import WorkerRuntimeConfig
from app.worker_runtime.execution import (
    AcquiredControlledOffer,
    AmbiguousProviderExecutionError,
    IsolatedWorkspaceExecutionError,
    IsolatedWorkspaceExecutor,
    NodeExecutionProviderClient,
)
from app.worker_runtime.recovery import RecoveryRecord, WorkerRecoveryJournal


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
        journal: WorkerRecoveryJournal | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.private_key = private_key
        self.journal = journal
        self._session: Session | None = None
        self._state = WorkerRuntimeState.STOPPED
        self._last_heartbeat_at: datetime | None = None
        self._workstream_versions: dict[UUID, int] = {}
        self._workstream_actions: dict[UUID, str] = {}
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
            journal=(
                WorkerRecoveryJournal(config.state_directory)
                if config.state_directory is not None
                else None
            ),
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
            if self.journal is not None:
                self.journal.record_health(
                    worker_id=self.config.worker_id,
                    observed_at=sent_at,
                    service_version=self.config.service_version,
                )
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
        delay = self.config.reconnect_min_seconds
        try:
            while not stop.is_set():
                try:
                    await self.establish()
                    delay = self.config.reconnect_min_seconds
                    while not stop.is_set():
                        recovery = self.journal.load() if self.journal else None
                        await self.heartbeat(
                            WorkerHealth.DEGRADED
                            if recovery is not None
                            else WorkerHealth.HEALTHY
                        )
                        if recovery and recovery.phase == "pending_result":
                            await self._deliver_pending_result(recovery)
                        elif recovery and recovery.phase == "acquired":
                            assert self.journal is not None
                            self.journal.store(
                                RecoveryRecord(
                                    phase="reconciliation_required",
                                    offer_id=recovery.offer_id,
                                    lease_id=recovery.lease_id,
                                    started_at=recovery.started_at,
                                )
                            )
                        elif (
                            recovery is None
                            and WorkerCapability.ENGINEERING_EXECUTE
                            in self.config.capabilities
                        ):
                            await self.consume_workstream_control()
                            await self.execute_available_offer()
                        try:
                            await asyncio.wait_for(
                                stop.wait(), timeout=self.config.heartbeat_seconds
                            )
                        except TimeoutError:
                            continue
                except asyncio.CancelledError:
                    raise
                # Transport/authentication failure is retryable by the service.
                except (WorkerRuntimeTransportError, httpx.HTTPError, OSError):
                    self._session = None
                    self._state = WorkerRuntimeState.DEGRADED
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=delay)
                    except TimeoutError:
                        delay = min(delay * 2, self.config.reconnect_max_seconds)
        finally:
            await self.close()

    async def execute_available_offer(self) -> bool:
        async with self._lock:
            session = self._require_session()
            offers = await self.client.poll_offers(session_id=session.session_id)
            if not offers:
                return False
            offered = offers[0]
            command_id = UUID(str(offered["command_id"]))
            offered_payload = offered.get("payload")
            if not isinstance(offered_payload, dict):
                raise IsolatedWorkspaceExecutionError("Offer payload is invalid.")
            if self._workstream_actions.get(command_id) in {"pause", "cancel"}:
                return False
            recovered_lease = "recovery_lease_id" in offered_payload
            if recovered_lease:
                acquired = AcquiredControlledOffer(
                    offer_id=UUID(str(offered["offer_id"])),
                    lease_id=UUID(str(offered_payload["recovery_lease_id"])),
                    lease_version=int(str(offered_payload["recovery_lease_version"])),
                    workspace_id=str(offered["workspace_id"]),
                    command_type=str(offered["command_type"]),
                    payload=offered_payload,
                )
            else:
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
            if self.journal is None:
                raise RuntimeError("Execution-capable worker requires recovery state.")
            self.journal.store(
                RecoveryRecord(
                    phase="acquired",
                    offer_id=acquired.offer_id,
                    lease_id=acquired.lease_id,
                    started_at=started_at,
                )
            )
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
            renewal: asyncio.Task[None] | None = None
            try:
                if acquired.command_type == "execute_code":
                    if (
                        self.config.provider_url is None
                        or self.config.provider_token_file is None
                    ):
                        raise IsolatedWorkspaceExecutionError(
                            "Node Execution Provider is unavailable."
                        )
                    renewal = asyncio.create_task(
                        self._maintain_execution_lease(
                            session=session,
                            lease_id=acquired.lease_id,
                            initial_version=acquired.lease_version,
                            renew_immediately=recovered_lease,
                        )
                    )
                    phase_progress = {
                        "queued": (1, "Acknowledged"),
                        "composed": (5, "Preparing controlled execution"),
                        "workspace_ready": (10, "Starting isolated workspace"),
                        "executing": (20, "Executing approved milestone"),
                        "validating": (70, "Validating approved milestone"),
                        "commit_ready": (82, "Finalizing controlled commit"),
                        "publishing_result": (92, "Reconciling and publishing result"),
                    }

                    async def publish_provider_progress(phase: str) -> None:
                        progress, activity = phase_progress.get(
                            phase, (1, "Controlled execution active")
                        )
                        if command_id in self._workstream_versions:
                            await self._publish_workstream_state(
                                command_id=command_id,
                                state="validating"
                                if phase in {"validating", "commit_ready"}
                                else "running",
                                health="healthy",
                                progress=progress,
                                activity=activity,
                            )

                    output = await NodeExecutionProviderClient(
                        self.config.provider_url, self.config.provider_token_file
                    ).execute(acquired, progress=publish_provider_progress)
                else:
                    assert self.config.workspace_root is not None
                    output = IsolatedWorkspaceExecutor(
                        self.config.workspace_root
                    ).execute(acquired)
            except AmbiguousProviderExecutionError:
                # The provider may have mutated its isolated workspace. Keep the
                # acquired journal entry for explicit reconciliation and never
                # publish a retryable failure result.
                raise
            except IsolatedWorkspaceExecutionError:
                outcome = "failed"
                failure = "workspace_validation_failed"
                output = {"repository_mutated": False}
            finally:
                if renewal is not None:
                    renewal.cancel()
                    try:
                        await renewal
                    except asyncio.CancelledError:
                        pass
            completed_at = datetime.now(timezone.utc)
            pending = RecoveryRecord(
                phase="pending_result",
                offer_id=acquired.offer_id,
                lease_id=acquired.lease_id,
                started_at=started_at,
                result={
                    "outcome": outcome,
                    "output": output,
                    "error_classification": failure,
                    "completed_at": completed_at.isoformat(),
                },
            )
            self.journal.store(pending)
            await self._deliver_pending_result(pending)
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

    async def _maintain_execution_lease(
        self,
        *,
        session: Session,
        lease_id: UUID,
        initial_version: int,
        renew_immediately: bool = False,
    ) -> None:
        version = initial_version
        while True:
            if not renew_immediately:
                await asyncio.sleep(240)
            renew_immediately = False
            sent_at = datetime.now(timezone.utc)
            payload = LeaseRenewalMessage(
                lease_id=lease_id,
                expected_lease_version=version,
                lease_seconds=900,
            )
            envelope = self._envelope(
                session=session,
                sent_at=sent_at,
                kind=TransportMessageKind.LEASE_RENEWAL,
                payload=payload,
            )
            version = await self.client.renew_lease(
                session_id=session.session_id,
                payload={
                    "message_id": str(envelope.message_id),
                    "session_id": str(envelope.session_id),
                    "sequence_number": envelope.sequence_number,
                    "sent_at": envelope.sent_at.isoformat(),
                    "authentication_proof": envelope.authentication_proof,
                    "key_version": envelope.key_version,
                    "lease_id": str(lease_id),
                    "expected_lease_version": version,
                    "lease_seconds": 900,
                },
            )
            self._advance(sent_at)

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
            self._workstream_actions[UUID(str(control["command_id"]))] = action
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

    async def _deliver_pending_result(self, pending: RecoveryRecord) -> None:
        if pending.result is None or self.journal is None:
            raise RuntimeError("Pending worker result is incomplete.")
        current = self._require_session()
        completed_at = datetime.fromisoformat(str(pending.result["completed_at"]))
        result_payload = ControlledExecutionResultMessage(
            offer_id=pending.offer_id,
            lease_id=pending.lease_id,
            outcome=str(pending.result["outcome"]),  # type: ignore[arg-type]
            output=cast(dict[str, object], pending.result["output"]),
            error_classification=(
                str(pending.result["error_classification"])
                if pending.result.get("error_classification") is not None
                else None
            ),
            started_at=pending.started_at,
            completed_at=completed_at,
        )
        result_envelope = self._envelope(
            session=current,
            # The durable operation completion time remains in the payload. The
            # transport envelope must prove freshness at redelivery time after a
            # reconnect; replay protection still binds its new session/sequence.
            sent_at=datetime.now(timezone.utc),
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
                "offer_id": str(pending.offer_id),
                "lease_id": str(pending.lease_id),
                "outcome": pending.result["outcome"],
                "output": pending.result["output"],
                "error_classification": pending.result.get("error_classification"),
                "started_at": pending.started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
            },
        )
        self._advance(completed_at)
        self.journal.clear()

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
