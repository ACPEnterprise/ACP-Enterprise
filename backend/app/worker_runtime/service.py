import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.worker_control.contracts import WorkerHealth
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    HeartbeatMessage,
    LeaseRenewalMessage,
    TransportMessageKind,
)
from app.worker_control.transport.crypto import (
    canonical_message,
    decode_private_key,
    encode_signature,
)
from app.worker_runtime.client import Session, WorkerTransportClient
from app.worker_runtime.config import WorkerRuntimeConfig


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
        payload: HeartbeatMessage | LeaseRenewalMessage,
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
