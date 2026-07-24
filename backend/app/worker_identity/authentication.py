from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.worker_control.contracts import AuthenticatedWorkerContext
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    AuthenticatedWorkerSessionIdentity,
    WorkerSession,
)
from app.worker_control.transport.errors import TransportAuthenticationError
from app.worker_identity.contracts import WorkerCredentialProofVerifier
from app.worker_identity.repository import WorkerIdentityRepository


class AuthenticatedMessageProofVerifier(Protocol):
    async def verify_message(
        self,
        *,
        envelope: AuthenticatedMessageEnvelope,
        session: WorkerSession,
    ) -> bool: ...


class WorkerIdentityAuthenticator:
    """Provider-neutral bridge from durable identity credentials to transport."""

    def __init__(
        self,
        *,
        proof_verifier: WorkerCredentialProofVerifier,
        message_verifier: AuthenticatedMessageProofVerifier,
        repository: WorkerIdentityRepository | None = None,
    ) -> None:
        self.proof_verifier = proof_verifier
        self.message_verifier = message_verifier
        self.repository = repository or WorkerIdentityRepository()

    async def active_key_version(
        self, database: AsyncSession, *, worker_id: UUID, now: datetime
    ) -> str:
        credential = await self.repository.get_authentication_credential(
            database, worker_id=worker_id, now=now
        )
        if credential is None:
            raise TransportAuthenticationError(
                "Worker has no eligible active credential."
            )
        return str(credential.credential_version)

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
        credential = await self.repository.get_authentication_credential(
            database, worker_id=worker_id, now=now
        )
        if credential is None or str(credential.credential_version) != key_version:
            raise TransportAuthenticationError(
                "Worker credential is unavailable or stale."
            )
        if not await self.proof_verifier.verify(
            challenge=challenge,
            response=authentication_response,
            verifier=credential.verifier,
            verifier_algorithm=credential.verifier_algorithm,
        ):
            raise TransportAuthenticationError("Worker credential proof is invalid.")
        return AuthenticatedWorkerSessionIdentity(
            context=AuthenticatedWorkerContext(
                company_id=credential.company_id,
                worker_id=credential.worker_id,
                provider_identifier=credential.provider_identifier,
                authentication_subject=(
                    f"worker-identity:{credential.identity_id}:"
                    f"credential:{credential.credential_id}"
                ),
                authenticated_at=now,
            ),
            worker_identity_id=credential.identity_id,
            credential_id=credential.credential_id,
            credential_version=credential.credential_version,
        )

    async def validate_session(
        self,
        database: AsyncSession,
        *,
        session: WorkerSession,
        now: datetime,
    ) -> None:
        if (
            session.worker_identity_id is None
            or session.credential_id is None
            or session.credential_version is None
        ):
            raise TransportAuthenticationError(
                "Worker session has no eligible credential binding."
            )
        credential = await self.repository.get_bound_authentication_credential(
            database,
            company_id=session.context.company_id,
            worker_id=session.context.worker_id,
            identity_id=session.worker_identity_id,
            credential_id=session.credential_id,
            credential_version=session.credential_version,
            now=now,
        )
        if (
            credential is None
            or credential.provider_identifier != session.context.provider_identifier
            or str(credential.credential_version) != session.key_version
        ):
            # Preserve the immutable session evidence but make it unusable. The
            # failed message transaction must not persist protocol state.
            raise TransportAuthenticationError(
                "Worker session credential is no longer eligible."
            )

    async def verify_message(
        self,
        *,
        envelope: AuthenticatedMessageEnvelope,
        session: WorkerSession,
    ) -> bool:
        return await self.message_verifier.verify_message(
            envelope=envelope, session=session
        )
