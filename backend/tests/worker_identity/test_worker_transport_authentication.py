from collections.abc import AsyncIterator
from datetime import timedelta
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.worker_control.contracts import WorkerCapability, WorkerHealth
from app.worker_control.models import WorkerHeartbeat
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    HeartbeatMessage,
    TransportMessageKind,
    WorkerSession,
    WorkerSessionRequest,
)
from app.worker_control.transport.errors import TransportAuthenticationError
from app.worker_control.transport.http.service import WorkerPollingService
from app.worker_control.transport.persistence.models import (
    WorkerTransportReceipt,
    WorkerTransportSession,
)
from app.worker_control.transport.service import WorkerTransportService
from app.worker_identity.authentication import WorkerIdentityAuthenticator
from app.worker_identity.contracts import (
    IssuedCredentialMetadata,
    WorkerCredentialState,
    WorkerIdentityState,
)
from app.worker_identity.models import WorkerCredential, WorkerIdentity
from app.worker_identity.service import WorkerIdentityService
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    seed_service_fixture,
)
from tests.worker_control.test_worker_control import register_available_worker
from tests.worker_identity.test_worker_identity import authorized


class AuthenticationIssuer:
    async def issue(
        self, *, identity_id, credential_version: int
    ) -> IssuedCredentialMetadata:
        return IssuedCredentialMetadata(
            verifier=f"verifier:{identity_id}:{credential_version}",
            verifier_algorithm="ed25519",
            public_key_id=f"kid:{identity_id}:{credential_version}",
        )


class ProofVerifier:
    async def verify(
        self,
        *,
        challenge: str,
        response: str,
        verifier: str,
        verifier_algorithm: str,
    ) -> bool:
        return response == f"{challenge}:{verifier}" and verifier_algorithm == "ed25519"


class MessageVerifier:
    async def verify_message(
        self,
        *,
        envelope: AuthenticatedMessageEnvelope,
        session: WorkerSession,
        verifier: str,
        verifier_algorithm: str,
    ) -> bool:
        del verifier, verifier_algorithm
        return (
            envelope.worker_id == session.context.worker_id
            and envelope.authentication_proof == "signed"
        )


@pytest_asyncio.fixture
async def authentication_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    identity_table = cast(Table, WorkerIdentity.__table__)
    credential_table = cast(Table, WorkerCredential.__table__)
    async with engine.begin() as connection:
        await connection.run_sync(identity_table.create, checkfirst=True)
        await connection.run_sync(credential_table.create, checkfirst=True)
    fixture = await seed_service_fixture(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    try:
        yield fixture
    finally:
        await engine.dispose()


async def identity_credential(
    fixture, *, worker, now, lifetime: timedelta = timedelta(days=1)
):
    identity_service = WorkerIdentityService(issuer=AuthenticationIssuer())
    async with fixture.factory() as session:
        identity = await identity_service.register(
            session,
            context=authorized(fixture.context),
            name=f"identity-{worker.id}",
            now=now,
        )
    async with fixture.factory() as session:
        identity = await identity_service.bind_orchestration_worker(
            session,
            context=authorized(fixture.context),
            identity_id=identity.id,
            worker_id=worker.id,
            expected_version=identity.version,
            now=now,
        )
    async with fixture.factory() as session:
        identity = await identity_service.transition_identity(
            session,
            context=authorized(fixture.context),
            identity_id=identity.id,
            expected_version=identity.version,
            state=WorkerIdentityState.ACTIVE,
            now=now,
        )
        credential = await identity_service.issue_credential(
            session,
            context=authorized(fixture.context),
            identity_id=identity.id,
            lifetime=lifetime,
            now=now,
        )
    async with fixture.factory() as session:
        credential = await identity_service.activate_credential(
            session,
            context=authorized(fixture.context),
            credential_id=credential.id,
            now=now,
        )
    return identity_service, identity, credential


@pytest.mark.asyncio
async def test_active_credential_establishes_company_bound_transport_session(
    authentication_database,
) -> None:
    fixture = authentication_database
    _, worker, _, heartbeat = await register_available_worker(fixture)
    now = heartbeat.last_seen
    _, identity, credential = await identity_credential(fixture, worker=worker, now=now)
    authenticator = WorkerIdentityAuthenticator(
        proof_verifier=ProofVerifier(),
        message_verifier=MessageVerifier(),
    )
    transport = WorkerTransportService(authenticator=authenticator)
    async with fixture.factory() as session:
        challenge = await transport.initiate_session(
            session, worker_id=worker.id, now=now
        )
    assert challenge.key_version == str(credential.version)

    async with fixture.factory() as session:
        established = await transport.establish_session(
            session,
            request=WorkerSessionRequest(
                challenge_id=challenge.challenge_id,
                worker_id=worker.id,
                challenge=challenge.challenge,
                authentication_response=(
                    f"{challenge.challenge}:{credential.verifier}"
                ),
                capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
            ),
            now=now,
        )
    assert established.context.company_id == fixture.context.company.id
    assert established.context.worker_id == worker.id
    assert str(identity.id) in established.context.authentication_subject


@pytest.mark.asyncio
async def test_rotated_or_revoked_credential_rejects_existing_challenge(
    authentication_database,
) -> None:
    fixture = authentication_database
    _, worker, _, heartbeat = await register_available_worker(fixture)
    now = heartbeat.last_seen
    identity_service, identity, credential = await identity_credential(
        fixture, worker=worker, now=now
    )
    authenticator = WorkerIdentityAuthenticator(
        proof_verifier=ProofVerifier(),
        message_verifier=MessageVerifier(),
    )
    transport = WorkerTransportService(authenticator=authenticator)
    async with fixture.factory() as session:
        challenge = await transport.initiate_session(
            session, worker_id=worker.id, now=now
        )
    async with fixture.factory() as session:
        revoked = await identity_service.revoke_credential(
            session,
            context=authorized(fixture.context),
            credential_id=credential.id,
            now=now + timedelta(seconds=1),
        )
    assert revoked.state is WorkerCredentialState.REVOKED

    with pytest.raises(TransportAuthenticationError):
        async with fixture.factory() as session:
            await transport.establish_session(
                session,
                request=WorkerSessionRequest(
                    challenge_id=challenge.challenge_id,
                    worker_id=worker.id,
                    challenge=challenge.challenge,
                    authentication_response=(
                        f"{challenge.challenge}:{credential.verifier}"
                    ),
                    capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
                ),
                now=now + timedelta(seconds=2),
            )

    async with fixture.factory() as session:
        stored = await identity_service.repository.get_identity(
            session,
            company_id=fixture.other_context.company.id,
            identity_id=identity.id,
        )
    assert stored is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalidating_change",
    ("revoke", "rotate", "expire", "suspend"),
)
async def test_existing_session_credential_invalidation_rolls_back_message(
    authentication_database,
    invalidating_change: str,
) -> None:
    fixture = authentication_database
    _, worker, _, heartbeat = await register_available_worker(fixture)
    now = heartbeat.last_seen
    lifetime = (
        timedelta(minutes=5) if invalidating_change == "expire" else timedelta(days=1)
    )
    identity_service, identity, credential = await identity_credential(
        fixture, worker=worker, now=now, lifetime=lifetime
    )
    authenticator = WorkerIdentityAuthenticator(
        proof_verifier=ProofVerifier(),
        message_verifier=MessageVerifier(),
    )
    transport = WorkerTransportService(authenticator=authenticator)
    async with fixture.factory() as database:
        challenge = await transport.initiate_session(
            database, worker_id=worker.id, now=now
        )
    async with fixture.factory() as database:
        session = await transport.establish_session(
            database,
            request=WorkerSessionRequest(
                challenge_id=challenge.challenge_id,
                worker_id=worker.id,
                challenge=challenge.challenge,
                authentication_response=(
                    f"{challenge.challenge}:{credential.verifier}"
                ),
                capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
            ),
            now=now,
        )

    message_time = now + timedelta(seconds=2)
    if invalidating_change == "revoke":
        async with fixture.factory() as database:
            await identity_service.revoke_credential(
                database,
                context=authorized(fixture.context),
                credential_id=credential.id,
                now=now + timedelta(seconds=1),
            )
    elif invalidating_change == "rotate":
        async with fixture.factory() as database:
            replacement = await identity_service.issue_credential(
                database,
                context=authorized(fixture.context),
                identity_id=identity.id,
                lifetime=timedelta(days=1),
                now=now + timedelta(seconds=1),
            )
        async with fixture.factory() as database:
            await identity_service.activate_credential(
                database,
                context=authorized(fixture.context),
                credential_id=replacement.id,
                now=now + timedelta(seconds=2),
            )
        message_time = now + timedelta(seconds=3)
    elif invalidating_change == "expire":
        message_time = now + timedelta(minutes=6)
    else:
        async with fixture.factory() as database:
            await identity_service.transition_identity(
                database,
                context=authorized(fixture.context),
                identity_id=identity.id,
                expected_version=identity.version,
                state=WorkerIdentityState.SUSPENDED,
                now=now + timedelta(seconds=1),
            )

    envelope = AuthenticatedMessageEnvelope(
        message_id=credential.id,
        session_id=session.session_id,
        worker_id=worker.id,
        sequence_number=1,
        sent_at=message_time,
        kind=TransportMessageKind.HEARTBEAT,
        payload=HeartbeatMessage(health=WorkerHealth.HEALTHY),
        authentication_proof="signed",
        key_version=session.key_version,
    )
    with pytest.raises(TransportAuthenticationError):
        async with fixture.factory() as database:
            await transport.handle_message(
                database, envelope=envelope, now=message_time
            )
    polling = WorkerPollingService(
        sessions=transport.sessions,
        session_validator=transport,
    )
    if invalidating_change != "expire":
        with pytest.raises(TransportAuthenticationError):
            async with fixture.factory() as database:
                await polling.poll(
                    database,
                    context=session.context,
                    session_id=session.session_id,
                    limit=1,
                )

    async with fixture.factory() as database:
        persisted = await database.get(WorkerTransportSession, session.session_id)
        receipts = await database.scalar(
            select(func.count(WorkerTransportReceipt.message_id)).where(
                WorkerTransportReceipt.session_id == session.session_id
            )
        )
        heartbeats = await database.scalar(
            select(func.count(WorkerHeartbeat.id)).where(
                WorkerHeartbeat.worker_id == worker.id,
                WorkerHeartbeat.last_seen == message_time,
            )
        )
    assert persisted is not None and persisted.next_sequence == 1
    assert receipts == 0
    assert heartbeats == 0
