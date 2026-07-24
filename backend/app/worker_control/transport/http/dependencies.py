from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status

from app.worker_control.contracts import AuthenticatedWorkerContext
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    WorkerSession,
)
from app.worker_control.transport.service import WorkerTransportService
from app.worker_identity.authentication import WorkerIdentityAuthenticator


class FailClosedCredentialProofVerifier:
    """Local composition boundary until an approved cryptographic adapter exists."""

    async def verify(
        self,
        *,
        challenge: str,
        response: str,
        verifier: str,
        verifier_algorithm: str,
    ) -> bool:
        del challenge, response, verifier, verifier_algorithm
        return False


class FailClosedMessageProofVerifier:
    """Rejects every message without inventing keys or custom cryptography."""

    async def verify_message(
        self,
        *,
        envelope: AuthenticatedMessageEnvelope,
        session: WorkerSession,
    ) -> bool:
        del envelope, session
        return False


@dataclass(frozen=True)
class WorkerBootstrapIdentity:
    """DF.7A authentication result; never constructed from request payload."""

    worker_id: UUID


@dataclass(frozen=True)
class WorkerHttpIdentity:
    """Authenticated worker and tenant snapshot supplied by DF.7A."""

    context: AuthenticatedWorkerContext


async def get_worker_bootstrap_identity() -> WorkerBootstrapIdentity:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "worker_authentication_required"},
    )


async def get_worker_http_identity() -> WorkerHttpIdentity:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "worker_authentication_required"},
    )


worker_identity_authenticator = WorkerIdentityAuthenticator(
    proof_verifier=FailClosedCredentialProofVerifier(),
    message_verifier=FailClosedMessageProofVerifier(),
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
