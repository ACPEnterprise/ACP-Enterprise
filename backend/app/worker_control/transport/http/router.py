from types import MappingProxyType
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.worker_control.contracts import WorkerExecutionResult
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    HeartbeatMessage,
    LeaseRenewalMessage,
    ResultMessage,
    TransportPayload,
    TransportMessageKind,
    WorkerSessionRequest,
)
from app.worker_control.transport.errors import WorkerTransportError
from app.worker_control.transport.http.dependencies import (
    AuthenticatedIdentity,
    BootstrapIdentity,
    TransportService,
)
from app.worker_control.transport.http.errors import transport_http_error
from app.worker_control.transport.http.schemas import (
    ChallengeResponse,
    EstablishSessionRequest,
    EnvelopeEvidence,
    HeartbeatRequest,
    LeaseRenewalRequest,
    OfferPageResponse,
    OfferResponse,
    ReceiptResponse,
    ResultRequest,
    SessionResponse,
)
from app.worker_control.transport.http.service import WorkerPollingService
from app.worker_control.transport.service import WorkerTransportService

router = APIRouter(
    prefix="/api/v1/worker-transport",
    tags=["Authenticated Worker Transport"],
)
Database = Annotated[AsyncSession, Depends(get_database_session)]


@router.post(
    "/sessions/challenge",
    response_model=ChallengeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a short-lived worker authentication challenge",
)
async def issue_challenge(
    identity: BootstrapIdentity,
    database: Database,
    service: TransportService,
) -> ChallengeResponse:
    try:
        challenge = await service.initiate_session(
            database, worker_id=identity.worker_id
        )
    except WorkerTransportError as error:
        raise transport_http_error(error) from error
    return ChallengeResponse.model_validate(challenge, from_attributes=True)


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Establish an authenticated bounded worker session",
)
async def establish_session(
    data: EstablishSessionRequest,
    identity: BootstrapIdentity,
    database: Database,
    service: TransportService,
) -> SessionResponse:
    try:
        session = await service.establish_session(
            database,
            request=WorkerSessionRequest(
                challenge_id=data.challenge_id,
                worker_id=identity.worker_id,
                challenge=data.challenge,
                authentication_response=data.authentication_response,
                capabilities=data.capabilities,
            ),
        )
    except WorkerTransportError as error:
        raise transport_http_error(error) from error
    return SessionResponse(
        session_id=session.session_id,
        worker_id=session.context.worker_id,
        capabilities=session.capabilities,
        key_version=session.key_version,
        state=session.state.value,
        established_at=session.established_at,
        expires_at=session.expires_at,
        next_sequence=session.next_sequence,
    )


@router.get(
    "/sessions/{session_id}/offers",
    response_model=OfferPageResponse,
    summary="Poll bounded execution offers without dispatching work",
)
async def poll_offers(
    session_id: UUID,
    identity: AuthenticatedIdentity,
    database: Database,
    service: TransportService,
    limit: Annotated[int, Query(ge=1, le=10)] = 1,
) -> OfferPageResponse:
    polling = WorkerPollingService(
        sessions=service.sessions,
        session_validator=service,
    )
    try:
        offers = await polling.poll(
            database,
            context=identity.context,
            session_id=session_id,
            limit=limit,
        )
    except WorkerTransportError as error:
        raise transport_http_error(error) from error
    return OfferPageResponse(
        items=tuple(
            OfferResponse(
                offer_id=offer.offer_id,
                execution_id=offer.execution_id,
                correlation_id=offer.correlation_id,
                capability_required=offer.capability_required,
                lease_seconds=int(offer.lease_duration.total_seconds()),
                expires_at=offer.expires_at,
            )
            for offer in offers
        ),
        retry_after_seconds=15,
    )


@router.post(
    "/heartbeats",
    response_model=ReceiptResponse,
    summary="Record an authenticated worker heartbeat",
)
async def heartbeat(
    data: HeartbeatRequest,
    identity: AuthenticatedIdentity,
    database: Database,
    service: TransportService,
) -> ReceiptResponse:
    envelope = _envelope(
        data,
        worker_id=identity.context.worker_id,
        kind=TransportMessageKind.HEARTBEAT,
        payload=HeartbeatMessage(health=data.health),
    )
    return await _handle(database, service, envelope)


@router.post(
    "/leases/refresh",
    response_model=ReceiptResponse,
    summary="Refresh a lease through an authenticated ordered message",
)
async def refresh_lease(
    data: LeaseRenewalRequest,
    identity: AuthenticatedIdentity,
    database: Database,
    service: TransportService,
) -> ReceiptResponse:
    envelope = _envelope(
        data,
        worker_id=identity.context.worker_id,
        kind=TransportMessageKind.LEASE_RENEWAL,
        payload=LeaseRenewalMessage(
            lease_id=data.lease_id,
            expected_lease_version=data.expected_lease_version,
            lease_seconds=data.lease_seconds,
        ),
    )
    return await _handle(database, service, envelope)


@router.post(
    "/results",
    response_model=ReceiptResponse,
    summary="Submit a disconnected structured result without integrating work",
)
async def submit_result(
    data: ResultRequest,
    identity: AuthenticatedIdentity,
    database: Database,
    service: TransportService,
) -> ReceiptResponse:
    result = WorkerExecutionResult(
        execution_id=data.execution_id,
        worker_id=identity.context.worker_id,
        status=data.status,
        validation_summary=MappingProxyType({}),
        evidence_summary=MappingProxyType(
            {"repository_mutated": data.repository_mutated}
        ),
        output_references=(),
        failure_classification=data.failure_classification,
    )
    envelope = _envelope(
        data,
        worker_id=identity.context.worker_id,
        kind=TransportMessageKind.RESULT,
        payload=ResultMessage(
            lease_id=data.lease_id,
            expected_lease_version=data.expected_lease_version,
            capability=data.capability,
            correlation_id=data.correlation_id,
            result=result,
        ),
    )
    return await _handle(database, service, envelope)


def _envelope(
    data: EnvelopeEvidence,
    *,
    worker_id: UUID,
    kind: TransportMessageKind,
    payload: TransportPayload,
) -> AuthenticatedMessageEnvelope:
    return AuthenticatedMessageEnvelope(
        message_id=data.message_id,
        session_id=data.session_id,
        worker_id=worker_id,
        sequence_number=data.sequence_number,
        sent_at=data.sent_at,
        kind=kind,
        payload=payload,
        authentication_proof=data.authentication_proof,
        key_version=data.key_version,
    )


async def _handle(
    database: AsyncSession,
    service: WorkerTransportService,
    envelope: AuthenticatedMessageEnvelope,
) -> ReceiptResponse:
    try:
        receipt = await service.handle_message(database, envelope=envelope)
    except WorkerTransportError as error:
        raise transport_http_error(error) from error
    return ReceiptResponse.model_validate(receipt, from_attributes=True)
