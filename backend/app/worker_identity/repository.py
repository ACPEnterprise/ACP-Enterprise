from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.worker_identity.contracts import (
    IssuedCredentialMetadata,
    WorkerCredentialState,
    WorkerIdentityState,
)
from app.worker_identity.models import WorkerCredential, WorkerIdentity
from app.worker_identity.records import WorkerCredentialRecord, WorkerIdentityRecord


class WorkerIdentityRepository:
    @staticmethod
    def snapshot_identity(identity: WorkerIdentity) -> WorkerIdentityRecord:
        return _identity_record(identity)

    @staticmethod
    def snapshot_credential(
        credential: WorkerCredential,
    ) -> WorkerCredentialRecord:
        return _credential_record(credential)

    async def create_identity(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        name: str,
        registered_by_user_id: UUID,
        now: datetime,
    ) -> WorkerIdentityRecord:
        entity = WorkerIdentity(
            company_id=company_id,
            name=name,
            state=WorkerIdentityState.REGISTERED.value,
            registered_by_user_id=registered_by_user_id,
            version=1,
            registered_at=now,
            updated_at=now,
        )
        session.add(entity)
        await session.flush()
        return _identity_record(entity)

    async def get_identity(
        self, session: AsyncSession, *, company_id: UUID, identity_id: UUID
    ) -> WorkerIdentityRecord | None:
        entity = await session.scalar(
            select(WorkerIdentity).where(
                WorkerIdentity.company_id == company_id,
                WorkerIdentity.id == identity_id,
            )
        )
        return None if entity is None else _identity_record(entity)

    async def get_identity_for_update(
        self, session: AsyncSession, *, company_id: UUID, identity_id: UUID
    ) -> WorkerIdentity | None:
        return await session.scalar(
            select(WorkerIdentity)
            .where(
                WorkerIdentity.company_id == company_id,
                WorkerIdentity.id == identity_id,
            )
            .with_for_update()
        )

    async def set_identity_state(
        self,
        session: AsyncSession,
        *,
        identity: WorkerIdentity,
        state: WorkerIdentityState,
        now: datetime,
    ) -> WorkerIdentityRecord:
        identity.state = state.value
        identity.version += 1
        identity.updated_at = now
        await session.flush()
        return _identity_record(identity)

    async def issue_credential(
        self,
        session: AsyncSession,
        *,
        identity: WorkerIdentity,
        metadata: IssuedCredentialMetadata,
        expires_at: datetime,
        now: datetime,
    ) -> WorkerCredentialRecord:
        next_version = (
            await session.scalar(
                select(func.coalesce(func.max(WorkerCredential.version), 0)).where(
                    WorkerCredential.company_id == identity.company_id,
                    WorkerCredential.identity_id == identity.id,
                )
            )
            or 0
        ) + 1
        credential = WorkerCredential(
            company_id=identity.company_id,
            identity_id=identity.id,
            version=next_version,
            state=WorkerCredentialState.PENDING.value,
            verifier=metadata.verifier,
            verifier_algorithm=metadata.verifier_algorithm,
            public_key_id=metadata.public_key_id,
            issued_at=now,
            expires_at=expires_at,
            updated_at=now,
        )
        session.add(credential)
        await session.flush()
        return _credential_record(credential)

    async def get_credential_for_update(
        self, session: AsyncSession, *, company_id: UUID, credential_id: UUID
    ) -> WorkerCredential | None:
        return await session.scalar(
            select(WorkerCredential)
            .where(
                WorkerCredential.company_id == company_id,
                WorkerCredential.id == credential_id,
            )
            .with_for_update()
        )

    async def get_active_credential_for_update(
        self, session: AsyncSession, *, company_id: UUID, identity_id: UUID
    ) -> WorkerCredential | None:
        return await session.scalar(
            select(WorkerCredential)
            .where(
                WorkerCredential.company_id == company_id,
                WorkerCredential.identity_id == identity_id,
                WorkerCredential.state == WorkerCredentialState.ACTIVE.value,
            )
            .with_for_update()
        )

    async def get_active_verifier(
        self, session: AsyncSession, *, company_id: UUID, public_key_id: str
    ) -> WorkerCredentialRecord | None:
        entity = await session.scalar(
            select(WorkerCredential).where(
                WorkerCredential.company_id == company_id,
                WorkerCredential.public_key_id == public_key_id,
                WorkerCredential.state == WorkerCredentialState.ACTIVE.value,
            )
        )
        return None if entity is None else _credential_record(entity)

    async def transition_credential(
        self,
        session: AsyncSession,
        *,
        credential: WorkerCredential,
        state: WorkerCredentialState,
        now: datetime,
    ) -> WorkerCredentialRecord:
        credential.state = state.value
        credential.updated_at = now
        if state is WorkerCredentialState.ACTIVE:
            credential.activated_at = now
        elif state is WorkerCredentialState.REVOKED:
            credential.revoked_at = now
        elif state is WorkerCredentialState.EXPIRED:
            credential.expired_at = now
        await session.flush()
        return _credential_record(credential)


def _identity_record(entity: WorkerIdentity) -> WorkerIdentityRecord:
    return WorkerIdentityRecord(
        id=entity.id,
        company_id=entity.company_id,
        name=entity.name,
        state=WorkerIdentityState(entity.state),
        registered_by_user_id=entity.registered_by_user_id,
        version=entity.version,
        registered_at=entity.registered_at,
        updated_at=entity.updated_at,
    )


def _credential_record(entity: WorkerCredential) -> WorkerCredentialRecord:
    return WorkerCredentialRecord(
        id=entity.id,
        company_id=entity.company_id,
        identity_id=entity.identity_id,
        version=entity.version,
        state=WorkerCredentialState(entity.state),
        verifier=entity.verifier,
        verifier_algorithm=entity.verifier_algorithm,
        public_key_id=entity.public_key_id,
        issued_at=entity.issued_at,
        expires_at=entity.expires_at,
        activated_at=entity.activated_at,
        revoked_at=entity.revoked_at,
        expired_at=entity.expired_at,
        updated_at=entity.updated_at,
    )
