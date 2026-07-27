from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.worker_control.models import WorkerHeartbeat
from app.worker_control.transport.persistence.models import (
    WorkerTransportReceipt,
    WorkerTransportSession,
)
from app.worker_identity.contracts import (
    WorkerCredentialState,
    WorkerIdentityState,
)
from app.worker_identity.models import WorkerCredential, WorkerIdentity


@dataclass(frozen=True)
class MobileConnectivitySource:
    session_id: UUID
    established_at: datetime
    last_message_at: datetime | None
    heartbeat_at: datetime | None


class MobileConnectivityRepository:
    """Read-only Company-scoped projection of authenticated worker connectivity."""

    @staticmethod
    async def load(
        session: AsyncSession,
        *,
        company_id: UUID,
        now: datetime,
    ) -> MobileConnectivitySource | None:
        transport = await session.scalar(
            select(WorkerTransportSession)
            .join(
                WorkerIdentity,
                WorkerIdentity.id == WorkerTransportSession.worker_identity_id,
            )
            .join(
                WorkerCredential,
                WorkerCredential.id == WorkerTransportSession.credential_id,
            )
            .where(
                WorkerTransportSession.company_id == company_id,
                WorkerTransportSession.state == "active",
                WorkerTransportSession.expires_at > now,
                WorkerIdentity.company_id == company_id,
                WorkerIdentity.orchestration_worker_id
                == WorkerTransportSession.worker_id,
                WorkerIdentity.state == WorkerIdentityState.ACTIVE.value,
                WorkerCredential.company_id == company_id,
                WorkerCredential.identity_id
                == WorkerTransportSession.worker_identity_id,
                WorkerCredential.version == WorkerTransportSession.credential_version,
                WorkerCredential.state == WorkerCredentialState.ACTIVE.value,
                WorkerCredential.expires_at > now,
            )
            .order_by(
                WorkerTransportSession.established_at.desc(),
            )
            .limit(1)
        )
        if transport is None:
            return None
        last_message_at = await session.scalar(
            select(WorkerTransportReceipt.accepted_at)
            .where(
                WorkerTransportReceipt.company_id == company_id,
                WorkerTransportReceipt.session_id == transport.id,
            )
            .order_by(
                WorkerTransportReceipt.accepted_at.desc(),
                WorkerTransportReceipt.message_id.desc(),
            )
            .limit(1)
        )
        heartbeat_at = await session.scalar(
            select(WorkerHeartbeat.last_seen)
            .where(
                WorkerHeartbeat.company_id == company_id,
                WorkerHeartbeat.worker_id == transport.worker_id,
            )
            .order_by(WorkerHeartbeat.last_seen.desc(), WorkerHeartbeat.id.desc())
            .limit(1)
        )
        return MobileConnectivitySource(
            session_id=transport.id,
            established_at=transport.established_at,
            last_message_at=last_message_at,
            heartbeat_at=heartbeat_at,
        )
