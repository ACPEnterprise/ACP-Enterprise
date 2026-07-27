from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.worker_control.contracts import AuthenticatedWorkerContext
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    WorkerSession,
)
from app.worker_control.transport.crypto import (
    ED25519_ALGORITHM,
    canonical_message,
    verify_signature,
)
from app.worker_control.transport.errors import WorkerTransportError
from app.worker_control.transport.service import WorkerTransportService
from app.worker_identity.authentication import WorkerIdentityAuthenticator


class Ed25519CredentialProofVerifier:
    """Verify challenge signatures against persisted public metadata."""

    async def verify(
        self,
        *,
        challenge: str,
        response: str,
        verifier: str,
        verifier_algorithm: str,
    ) -> bool:
        return verifier_algorithm == ED25519_ALGORITHM and verify_signature(
            public_key=verifier,
            signature=response,
            message=challenge.encode(),
        )


class Ed25519MessageProofVerifier:
    """Verify the canonical immutable transport envelope."""

    async def verify_message(
        self,
        *,
        envelope: AuthenticatedMessageEnvelope,
        session: WorkerSession,
        verifier: str,
        verifier_algorithm: str,
    ) -> bool:
        del session
        return verifier_algorithm == ED25519_ALGORITHM and verify_signature(
            public_key=verifier,
            signature=envelope.authentication_proof,
            message=canonical_message(envelope),
        )


@dataclass(frozen=True)
class WorkerBootstrapIdentity:
    """DF.7A authentication result; never constructed from request payload."""

    worker_id: UUID


@dataclass(frozen=True)
class WorkerHttpIdentity:
    """Authenticated worker and tenant snapshot supplied by DF.7A."""

    context: AuthenticatedWorkerContext
    session_id: UUID


async def get_worker_bootstrap_identity(
    worker_id: Annotated[UUID | None, Header(alias="X-Worker-ID")] = None,
) -> WorkerBootstrapIdentity:
    # The identifier locates public verification metadata only. Possession of
    # the private key is proven when the one-time challenge is consumed.
    if worker_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "worker_authentication_required"},
        )
    return WorkerBootstrapIdentity(worker_id=worker_id)


async def get_worker_http_identity(
    database: Annotated[AsyncSession, Depends(get_database_session)],
    transport_session_id: Annotated[
        UUID | None, Header(alias="X-Worker-Session-ID")
    ] = None,
) -> WorkerHttpIdentity:
    if transport_session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "worker_authentication_required"},
        )
    try:
        session = await worker_transport_service.authenticate_http_session(
            database, session_id=transport_session_id
        )
    except WorkerTransportError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "worker_authentication_required"},
        ) from error
    return WorkerHttpIdentity(context=session.context, session_id=session.session_id)


worker_identity_authenticator = WorkerIdentityAuthenticator(
    proof_verifier=Ed25519CredentialProofVerifier(),
    message_verifier=Ed25519MessageProofVerifier(),
)
worker_transport_service = WorkerTransportService(
    authenticator=worker_identity_authenticator
)


async def get_worker_transport_service() -> WorkerTransportService:
    return worker_transport_service


BootstrapIdentity = Annotated[
    WorkerBootstrapIdentity, Depends(get_worker_bootstrap_identity)
]
AuthenticatedIdentity = Annotated[WorkerHttpIdentity, Depends(get_worker_http_identity)]
TransportService = Annotated[
    WorkerTransportService, Depends(get_worker_transport_service)
]
