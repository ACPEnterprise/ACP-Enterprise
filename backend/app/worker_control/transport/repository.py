import asyncio
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    TransportReceipt,
    WorkerSession,
    WorkerSessionState,
)


@dataclass(frozen=True)
class StoredChallenge:
    challenge_id: UUID
    worker_id: UUID
    challenge_digest: str
    issued_at: datetime
    expires_at: datetime
    key_version: str
    consumed_at: datetime | None = None


class WorkerTransportSessionRepository(Protocol):
    async def add_challenge(self, challenge: StoredChallenge) -> None: ...

    async def consume_challenge(
        self, *, challenge_id: UUID, now: datetime
    ) -> StoredChallenge | None: ...

    async def add_session(self, session: WorkerSession) -> None: ...

    async def get_session(self, session_id: UUID) -> WorkerSession | None: ...

    async def accept_sequence(
        self,
        *,
        envelope: AuthenticatedMessageEnvelope,
        now: datetime,
    ) -> tuple[WorkerSession | None, TransportReceipt | None]: ...

    async def store_receipt(
        self,
        *,
        envelope: AuthenticatedMessageEnvelope,
        receipt: TransportReceipt,
    ) -> None: ...


class InMemoryWorkerTransportSessionRepository:
    """Deterministic local reference store, not a production transport backend."""

    def __init__(self) -> None:
        self._challenges: dict[UUID, StoredChallenge] = {}
        self._sessions: dict[UUID, WorkerSession] = {}
        self._receipts: dict[
            UUID, tuple[AuthenticatedMessageEnvelope, TransportReceipt]
        ] = {}
        self._lock = asyncio.Lock()

    async def add_challenge(self, challenge: StoredChallenge) -> None:
        async with self._lock:
            if challenge.challenge_id in self._challenges:
                raise ValueError("challenge already exists")
            self._challenges[challenge.challenge_id] = challenge

    async def consume_challenge(
        self, *, challenge_id: UUID, now: datetime
    ) -> StoredChallenge | None:
        async with self._lock:
            challenge = self._challenges.get(challenge_id)
            if challenge is None or challenge.consumed_at is not None:
                return None
            consumed = replace(challenge, consumed_at=now)
            self._challenges[challenge_id] = consumed
            return consumed

    async def add_session(self, session: WorkerSession) -> None:
        async with self._lock:
            if session.session_id in self._sessions:
                raise ValueError("session already exists")
            self._sessions[session.session_id] = session

    async def get_session(self, session_id: UUID) -> WorkerSession | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def accept_sequence(
        self,
        *,
        envelope: AuthenticatedMessageEnvelope,
        now: datetime,
    ) -> tuple[WorkerSession | None, TransportReceipt | None]:
        async with self._lock:
            prior = self._receipts.get(envelope.message_id)
            if prior is not None:
                prior_envelope, receipt = prior
                if prior_envelope != envelope:
                    raise ValueError("message identifier reused with different content")
                return self._sessions.get(envelope.session_id), receipt
            session = self._sessions.get(envelope.session_id)
            if session is None:
                return None, None
            if (
                session.state is not WorkerSessionState.ACTIVE
                or session.expires_at <= now
            ):
                expired = replace(session, state=WorkerSessionState.EXPIRED)
                self._sessions[session.session_id] = expired
                return expired, None
            if envelope.sequence_number != session.next_sequence:
                return session, None
            advanced = replace(session, next_sequence=session.next_sequence + 1)
            self._sessions[session.session_id] = advanced
            return advanced, None

    async def store_receipt(
        self,
        *,
        envelope: AuthenticatedMessageEnvelope,
        receipt: TransportReceipt,
    ) -> None:
        async with self._lock:
            self._receipts[envelope.message_id] = (envelope, receipt)
