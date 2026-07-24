from dataclasses import asdict
from datetime import datetime
from enum import Enum
import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.worker_control.contracts import (
    AuthenticatedWorkerContext,
    WorkerCapability,
)
from app.worker_control.models import EngineeringWorker
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    TransportReceipt,
    WorkerSession,
    WorkerSessionState,
)
from app.worker_control.transport.repository import StoredChallenge

from .models import (
    WorkerTransportChallenge,
    WorkerTransportReceipt,
    WorkerTransportSession,
)


def _json_default(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (UUID, datetime)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    raise TypeError(f"Unsupported envelope value: {type(value).__name__}")


def envelope_digest(envelope: AuthenticatedMessageEnvelope) -> str:
    encoded = json.dumps(
        asdict(envelope),
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class PostgreSQLWorkerTransportSessionRepository:
    async def add_challenge(
        self, database: AsyncSession, challenge: StoredChallenge
    ) -> None:
        worker = await database.scalar(
            select(EngineeringWorker).where(EngineeringWorker.id == challenge.worker_id)
        )
        if worker is None:
            raise ValueError("worker does not exist")
        database.add(
            WorkerTransportChallenge(
                id=challenge.challenge_id,
                company_id=worker.company_id,
                worker_id=challenge.worker_id,
                challenge_digest=challenge.challenge_digest,
                issued_at=challenge.issued_at,
                expires_at=challenge.expires_at,
                key_version=challenge.key_version,
            )
        )
        await database.flush()

    async def consume_challenge(
        self, database: AsyncSession, *, challenge_id: UUID, now: datetime
    ) -> StoredChallenge | None:
        entity = await database.scalar(
            select(WorkerTransportChallenge)
            .where(WorkerTransportChallenge.id == challenge_id)
            .with_for_update()
        )
        if entity is None or entity.consumed_at is not None:
            return None
        entity.consumed_at = now
        await database.flush()
        return _challenge(entity)

    async def add_session(self, database: AsyncSession, session: WorkerSession) -> None:
        database.add(
            WorkerTransportSession(
                id=session.session_id,
                company_id=session.context.company_id,
                worker_id=session.context.worker_id,
                worker_identity_id=session.worker_identity_id,
                credential_id=session.credential_id,
                credential_version=session.credential_version,
                provider_identifier=session.context.provider_identifier,
                authentication_subject_digest=hashlib.sha256(
                    session.context.authentication_subject.encode()
                ).hexdigest(),
                capabilities=[capability.value for capability in session.capabilities],
                key_version=session.key_version,
                state=session.state.value,
                established_at=session.established_at,
                expires_at=session.expires_at,
                next_sequence=session.next_sequence,
                version=1,
            )
        )
        await database.flush()

    async def get_session(
        self, database: AsyncSession, session_id: UUID
    ) -> WorkerSession | None:
        entity = await database.scalar(
            select(WorkerTransportSession).where(
                WorkerTransportSession.id == session_id
            )
        )
        return None if entity is None else _session(entity)

    async def accept_sequence(
        self,
        database: AsyncSession,
        *,
        envelope: AuthenticatedMessageEnvelope,
        now: datetime,
    ) -> tuple[WorkerSession | None, TransportReceipt | None]:
        entity = await database.scalar(
            select(WorkerTransportSession)
            .where(WorkerTransportSession.id == envelope.session_id)
            .with_for_update()
        )
        prior = await database.get(WorkerTransportReceipt, envelope.message_id)
        if prior is not None:
            if prior.envelope_digest != envelope_digest(envelope):
                raise ValueError("message identifier reused with different content")
            return _session(entity) if entity is not None else None, _receipt(prior)
        if entity is None:
            return None, None
        if entity.state != WorkerSessionState.ACTIVE.value or entity.expires_at <= now:
            entity.state = WorkerSessionState.EXPIRED.value
            entity.version += 1
            await database.flush()
            return _session(entity), None
        if envelope.sequence_number != entity.next_sequence:
            return _session(entity), None
        return _session(entity), None

    async def store_receipt(
        self,
        database: AsyncSession,
        *,
        envelope: AuthenticatedMessageEnvelope,
        receipt: TransportReceipt,
    ) -> None:
        entity = await database.scalar(
            select(WorkerTransportSession)
            .where(WorkerTransportSession.id == envelope.session_id)
            .with_for_update()
        )
        if entity is None or entity.next_sequence != envelope.sequence_number:
            raise ValueError("session sequence changed before receipt storage")
        entity.next_sequence += 1
        entity.version += 1
        database.add(
            WorkerTransportReceipt(
                message_id=envelope.message_id,
                company_id=entity.company_id,
                session_id=entity.id,
                worker_id=entity.worker_id,
                sequence_number=envelope.sequence_number,
                envelope_digest=envelope_digest(envelope),
                accepted_at=receipt.accepted_at,
                outcome_reference=receipt.outcome_reference,
            )
        )
        await database.flush()


def _challenge(entity: WorkerTransportChallenge) -> StoredChallenge:
    return StoredChallenge(
        challenge_id=entity.id,
        worker_id=entity.worker_id,
        challenge_digest=entity.challenge_digest,
        issued_at=entity.issued_at,
        expires_at=entity.expires_at,
        key_version=entity.key_version,
        consumed_at=entity.consumed_at,
    )


def _session(entity: WorkerTransportSession) -> WorkerSession:
    return WorkerSession(
        session_id=entity.id,
        context=AuthenticatedWorkerContext(
            company_id=entity.company_id,
            worker_id=entity.worker_id,
            provider_identifier=entity.provider_identifier,
            authentication_subject=f"digest:{entity.authentication_subject_digest}",
            authenticated_at=entity.established_at,
        ),
        worker_identity_id=entity.worker_identity_id,
        credential_id=entity.credential_id,
        credential_version=entity.credential_version,
        capabilities=tuple(WorkerCapability(value) for value in entity.capabilities),
        key_version=entity.key_version,
        state=WorkerSessionState(entity.state),
        established_at=entity.established_at,
        expires_at=entity.expires_at,
        next_sequence=entity.next_sequence,
    )


def _receipt(entity: WorkerTransportReceipt) -> TransportReceipt:
    return TransportReceipt(
        message_id=entity.message_id,
        sequence_number=entity.sequence_number,
        accepted_at=entity.accepted_at,
        duplicate=False,
        outcome_reference=entity.outcome_reference,
    )
