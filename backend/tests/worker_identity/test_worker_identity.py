from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.events.models import BusinessEvent
from app.platform.audit.models import AuditRecord
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import WorkerIdentityPermission
from app.worker_identity.contracts import (
    IssuedCredentialMetadata,
    WorkerCredentialState,
    WorkerIdentityState,
)
from app.worker_identity.errors import (
    WorkerIdentityConflictError,
    WorkerIdentityLifecycleError,
    WorkerIdentityNotFoundError,
    WorkerIdentityPermissionError,
)
from app.worker_identity.models import WorkerCredential
from app.worker_identity.service import WorkerIdentityService
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
    utc_now,
)


class FakeIssuer:
    def __init__(self) -> None:
        self.calls = 0

    async def issue(
        self, *, identity_id, credential_version: int
    ) -> IssuedCredentialMetadata:
        self.calls += 1
        return IssuedCredentialMetadata(
            verifier=f"public-verifier-{identity_id}-{credential_version}",
            verifier_algorithm="ed25519",
            public_key_id=f"kid-{identity_id}-{credential_version}",
        )


def authorized(
    source: AuthorizationContext, *, active: bool = True, permitted: bool = True
) -> AuthorizationContext:
    membership = replace(source.membership, status="active" if active else "revoked")
    permissions = (WorkerIdentityPermission.MANAGE,) if permitted else ()
    return context_with_permissions(
        source.user, source.company, membership, permissions
    )


@pytest_asyncio.fixture
async def identity_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    fixture = await seed_service_fixture(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    try:
        yield fixture
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_identity_lifecycle_is_company_scoped_and_audited(
    identity_database: ServiceFixture,
) -> None:
    fixture = identity_database
    service = WorkerIdentityService(issuer=FakeIssuer())
    now = utc_now()
    async with fixture.factory() as session:
        identity = await service.register(
            session,
            context=authorized(fixture.context),
            name="mobile-worker",
            now=now,
        )
    assert identity.state is WorkerIdentityState.REGISTERED
    with pytest.raises(FrozenInstanceError):
        identity.name = "changed"  # type: ignore[misc]

    async with fixture.factory() as session:
        active = await service.transition_identity(
            session,
            context=authorized(fixture.context),
            identity_id=identity.id,
            expected_version=1,
            state=WorkerIdentityState.ACTIVE,
            now=now + timedelta(seconds=1),
        )
        suspended = await service.transition_identity(
            session,
            context=authorized(fixture.context),
            identity_id=identity.id,
            expected_version=2,
            state=WorkerIdentityState.SUSPENDED,
            now=now + timedelta(seconds=2),
        )
        restored = await service.transition_identity(
            session,
            context=authorized(fixture.context),
            identity_id=identity.id,
            expected_version=3,
            state=WorkerIdentityState.ACTIVE,
            now=now + timedelta(seconds=3),
        )
    assert (active.version, suspended.version, restored.version) == (2, 3, 4)

    async with fixture.factory() as session:
        concealed = await service.repository.get_identity(
            session,
            company_id=fixture.other_context.company.id,
            identity_id=identity.id,
        )
        audits = await session.scalar(
            select(func.count(AuditRecord.id)).where(
                AuditRecord.resource_type == "worker_identity",
                AuditRecord.resource_id == identity.id,
            )
        )
        events = await session.scalar(
            select(func.count(BusinessEvent.id)).where(
                BusinessEvent.entity_type == "worker_identity",
                BusinessEvent.entity_id == identity.id,
            )
        )
    assert concealed is None
    assert audits == events == 4


@pytest.mark.asyncio
async def test_permission_version_and_terminal_state_fail_closed(
    identity_database: ServiceFixture,
) -> None:
    fixture = identity_database
    service = WorkerIdentityService(issuer=FakeIssuer())
    async with fixture.factory() as session:
        with pytest.raises(WorkerIdentityPermissionError):
            await service.register(
                session,
                context=authorized(fixture.context, permitted=False),
                name="denied",
            )
    async with fixture.factory() as session:
        identity = await service.register(
            session, context=authorized(fixture.context), name="controlled"
        )
    async with fixture.factory() as session:
        with pytest.raises(WorkerIdentityConflictError):
            await service.transition_identity(
                session,
                context=authorized(fixture.context),
                identity_id=identity.id,
                expected_version=99,
                state=WorkerIdentityState.ACTIVE,
            )
    async with fixture.factory() as session:
        with pytest.raises(WorkerIdentityNotFoundError):
            await service.transition_identity(
                session,
                context=authorized(fixture.other_context),
                identity_id=identity.id,
                expected_version=1,
                state=WorkerIdentityState.ACTIVE,
            )


@pytest.mark.asyncio
async def test_credential_rotation_revocation_expiration_and_verifier_lookup(
    identity_database: ServiceFixture,
) -> None:
    fixture = identity_database
    issuer = FakeIssuer()
    service = WorkerIdentityService(issuer=issuer)
    now = utc_now()
    async with fixture.factory() as session:
        identity = await service.register(
            session,
            context=authorized(fixture.context),
            name="credential-worker",
            now=now,
        )
    async with fixture.factory() as session:
        first = await service.issue_credential(
            session,
            context=authorized(fixture.context),
            identity_id=identity.id,
            lifetime=timedelta(days=1),
            now=now,
        )
    async with fixture.factory() as session:
        first_active = await service.activate_credential(
            session,
            context=authorized(fixture.context),
            credential_id=first.id,
            now=now,
        )
    assert first_active.state is WorkerCredentialState.ACTIVE
    async with fixture.factory() as session:
        second = await service.issue_credential(
            session,
            context=authorized(fixture.context),
            identity_id=identity.id,
            lifetime=timedelta(days=1),
            now=now + timedelta(seconds=1),
        )
        second_active = await service.activate_credential(
            session,
            context=authorized(fixture.context),
            credential_id=second.id,
            now=now + timedelta(seconds=2),
        )
    assert second.version == 2
    assert second_active.state is WorkerCredentialState.ACTIVE
    async with fixture.factory() as session:
        old = await service.repository.get_credential_for_update(
            session, company_id=identity.company_id, credential_id=first.id
        )
        verifier = await service.repository.get_active_verifier(
            session,
            company_id=identity.company_id,
            public_key_id=second.public_key_id,
        )
    assert old is not None and old.state == WorkerCredentialState.REVOKED.value
    assert verifier is not None and verifier.id == second.id

    async with fixture.factory() as session:
        revoked = await service.revoke_credential(
            session,
            context=authorized(fixture.context),
            credential_id=second.id,
            now=now + timedelta(seconds=3),
        )
    assert revoked.state is WorkerCredentialState.REVOKED
    with pytest.raises(WorkerIdentityLifecycleError):
        async with fixture.factory() as session:
            await service.activate_credential(
                session,
                context=authorized(fixture.context),
                credential_id=second.id,
            )


def test_schema_and_records_have_no_raw_secret_field() -> None:
    columns = set(WorkerCredential.__table__.columns.keys())
    assert not {"secret", "token", "private_key", "credential"} & columns
    assert {"verifier", "verifier_algorithm", "public_key_id"} <= columns
