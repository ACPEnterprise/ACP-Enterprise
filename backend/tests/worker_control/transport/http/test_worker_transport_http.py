from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.engineering_execution.composition.contracts import ProviderProgressPhase
from app.worker_control.contracts import (
    AuthenticatedWorkerContext,
    WorkerCapability,
    WorkerHealth,
)
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    TransportReceipt,
    WorkerSession,
    WorkerSessionChallenge,
    WorkerSessionState,
)
from app.worker_control.transport.http.dependencies import (
    WorkerBootstrapIdentity,
    WorkerHttpIdentity,
    get_worker_bootstrap_identity,
    get_worker_http_identity,
    get_worker_transport_service,
)
from app.worker_control.transport.http.router import router
from app.worker_control.transport.http.service import WorkerPollingService
from app.worker_control.transport.repository import WorkerTransportSessionRepository
from app.worker_control.transport.service import WorkerTransportService
from app.worker_identity.authentication import WorkerIdentityAuthenticator

NOW = datetime(2026, 7, 24, 12, tzinfo=timezone.utc)


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeDatabase:
    def begin(self) -> FakeTransaction:
        return FakeTransaction()


class FakeTransport:
    def __init__(self, context: AuthenticatedWorkerContext) -> None:
        self.context = context
        self.sessions = FakeSessions(
            WorkerSession(
                session_id=uuid4(),
                context=context,
                worker_identity_id=uuid4(),
                credential_id=uuid4(),
                credential_version=1,
                capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
                key_version="key-1",
                state=WorkerSessionState.ACTIVE,
                established_at=NOW,
                expires_at=NOW + timedelta(minutes=10),
                next_sequence=1,
            )
        )
        self.last_envelope: AuthenticatedMessageEnvelope | None = None

    async def initiate_session(
        self, database: AsyncSession, *, worker_id: UUID
    ) -> WorkerSessionChallenge:
        del database
        return WorkerSessionChallenge(
            challenge_id=uuid4(),
            worker_id=worker_id,
            challenge="short-lived-challenge",
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=2),
            key_version="key-1",
        )

    async def handle_message(
        self, database: AsyncSession, *, envelope: AuthenticatedMessageEnvelope
    ) -> TransportReceipt:
        del database
        self.last_envelope = envelope
        return TransportReceipt(
            message_id=envelope.message_id,
            sequence_number=envelope.sequence_number,
            accepted_at=NOW,
            duplicate=False,
            outcome_reference="accepted-without-execution",
        )

    async def validate_authenticated_session_in_transaction(
        self,
        database: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        session_id: UUID,
        now=None,
    ) -> WorkerSession:
        del database, now
        session = await self.sessions.get_session(
            cast(AsyncSession, object()), session_id
        )
        if (
            session is None
            or session.context.company_id != context.company_id
            or session.context.worker_id != context.worker_id
        ):
            raise Exception("Worker session was not found.")
        return session


class FakeSessions:
    def __init__(self, session: WorkerSession) -> None:
        self.session = session

    async def get_session(
        self, database: AsyncSession, session_id: UUID
    ) -> WorkerSession | None:
        del database
        return self.session if self.session.session_id == session_id else None


def context() -> AuthenticatedWorkerContext:
    return AuthenticatedWorkerContext(
        company_id=uuid4(),
        worker_id=uuid4(),
        provider_identifier="provider-neutral",
        authentication_subject="credential:public-key",
        authenticated_at=NOW,
    )


def app_for(
    transport: FakeTransport | None = None,
    *,
    worker_context: AuthenticatedWorkerContext | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    async def database_override():
        yield cast(AsyncSession, FakeDatabase())

    app.dependency_overrides[get_database_session] = database_override
    if transport is not None:

        async def transport_override():
            return transport

        async def bootstrap_override():
            return WorkerBootstrapIdentity(transport.context.worker_id)

        async def identity_override():
            return WorkerHttpIdentity(worker_context or transport.context)

        app.dependency_overrides[get_worker_transport_service] = transport_override
        app.dependency_overrides[get_worker_bootstrap_identity] = bootstrap_override
        app.dependency_overrides[get_worker_http_identity] = identity_override
    return app


async def request(app: FastAPI, method: str, path: str, json=None) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(method, path, json=json)


@pytest.mark.asyncio
async def test_local_composition_fails_closed_without_authenticated_identity() -> None:
    response = await request(
        app_for(), "POST", "/api/v1/worker-transport/sessions/challenge"
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "worker_authentication_required"


@pytest.mark.asyncio
async def test_local_transport_composition_uses_integrated_identity_authenticator() -> (
    None
):
    service = await get_worker_transport_service()
    assert isinstance(service, WorkerTransportService)
    assert isinstance(service.authenticator, WorkerIdentityAuthenticator)


@pytest.mark.asyncio
async def test_challenge_uses_authenticated_worker_not_request_scope() -> None:
    transport = FakeTransport(context())
    response = await request(
        app_for(transport),
        "POST",
        "/api/v1/worker-transport/sessions/challenge",
        json={"worker_id": str(uuid4()), "company_id": str(uuid4())},
    )
    assert response.status_code == 201
    assert response.json()["worker_id"] == str(transport.context.worker_id)


@pytest.mark.asyncio
async def test_heartbeat_builds_bound_envelope_and_returns_receipt() -> None:
    transport = FakeTransport(context())
    session = transport.sessions.session
    payload = {
        "message_id": str(uuid4()),
        "session_id": str(session.session_id),
        "sequence_number": 1,
        "sent_at": NOW.isoformat(),
        "authentication_proof": "signed-proof",
        "key_version": "key-1",
        "health": WorkerHealth.HEALTHY.value,
    }
    response = await request(
        app_for(transport),
        "POST",
        "/api/v1/worker-transport/heartbeats",
        json=payload,
    )
    assert response.status_code == 200
    assert response.json()["outcome_reference"] == "accepted-without-execution"
    assert transport.last_envelope is not None
    assert transport.last_envelope.worker_id == transport.context.worker_id
    assert transport.last_envelope.payload.health is WorkerHealth.HEALTHY  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_composition_progress_contract_derives_worker_authority() -> None:
    transport = FakeTransport(context())
    session = transport.sessions.session
    payload = {
        "message_id": str(uuid4()),
        "session_id": str(session.session_id),
        "sequence_number": 1,
        "sent_at": NOW.isoformat(),
        "authentication_proof": "signed-proof",
        "key_version": "key-1",
        "composition_id": str(uuid4()),
        "attempt_id": str(uuid4()),
        "lease_id": str(uuid4()),
        "composition_digest": "a" * 64,
        "instruction_digest": "b" * 64,
        "request_digest": "c" * 64,
        "phase": ProviderProgressPhase.EXECUTING.value,
        "message_code": "simulated_progress",
        "summary": "Structured progress only.",
        "percentage": 25,
    }
    response = await request(
        app_for(transport),
        "POST",
        "/api/v1/worker-transport/progress",
        json=payload,
    )
    assert response.status_code == 200
    assert transport.last_envelope is not None
    assert transport.last_envelope.worker_id == transport.context.worker_id
    assert transport.last_envelope.kind.value == "provider_progress"

    rejected = await request(
        app_for(transport),
        "POST",
        "/api/v1/worker-transport/progress",
        json={**payload, "company_id": str(uuid4())},
    )
    assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_polling_conceals_cross_company_session_and_default_has_no_offers() -> (
    None
):
    transport = FakeTransport(context())
    polling = WorkerPollingService(
        sessions=cast(WorkerTransportSessionRepository, transport.sessions),
        session_validator=transport,
    )
    offers = await polling.poll(
        cast(AsyncSession, FakeDatabase()),
        context=transport.context,
        session_id=transport.sessions.session.session_id,
        limit=1,
    )
    assert offers == ()
    with pytest.raises(Exception, match="not found"):
        await polling.poll(
            cast(AsyncSession, FakeDatabase()),
            context=replace(transport.context, company_id=uuid4()),
            session_id=transport.sessions.session.session_id,
            limit=1,
        )


def test_openapi_is_provider_neutral_and_has_no_execution_endpoint() -> None:
    schema = app_for(FakeTransport(context())).openapi()
    paths = schema["paths"]
    assert "/api/v1/worker-transport/heartbeats" in paths
    assert "/api/v1/worker-transport/results" in paths
    assert "/api/v1/worker-transport/leases/refresh" in paths
    assert "/api/v1/worker-transport/compositions/next" in paths
    assert "/api/v1/worker-transport/compositions/acknowledge" in paths
    assert "/api/v1/worker-transport/progress" in paths
    assert "/api/v1/worker-transport/composition-results" in paths
    assert "/api/v1/worker-transport/cancellations/acknowledge" in paths
    assert all("execute" not in path and "provider" not in path for path in paths)
