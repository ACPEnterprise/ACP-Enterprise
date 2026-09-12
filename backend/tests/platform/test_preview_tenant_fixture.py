import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.platform.audit.models import AuditRecord
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.onboarding.preview_tenant_fixture import (
    FIXTURE_BRANCH_CODE,
    FIXTURE_BRANCH_ID,
    FIXTURE_COMPANY_CODE,
    FIXTURE_COMPANY_ID,
    FIXTURE_VERSION,
    PreviewSyntheticTenantCommand,
    PreviewSyntheticTenantFixtureService,
)
from app.platform.onboarding.service import OnboardingConflictError
from app.platform.permissions.codes import AdministrationPermission


class Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class Session:
    def __init__(self, company=None, branch=None):
        self.company = company
        self.branch = branch
        self.added = []
        self.execute = AsyncMock()

    def begin(self):
        return Transaction()

    async def get(self, model, identity):
        if identity == FIXTURE_COMPANY_ID:
            return self.company
        if identity == FIXTURE_BRANCH_ID:
            return self.branch
        raise AssertionError((model, identity))

    def add(self, value):
        self.added.append(value)
        if value.id == FIXTURE_COMPANY_ID:
            self.company = value
        elif value.id == FIXTURE_BRANCH_ID:
            self.branch = value

    async def flush(self):
        return None


def context(*permissions):
    return SimpleNamespace(
        user=SimpleNamespace(id=uuid4()), permission_codes=frozenset(permissions)
    )


def configuration(environment="preview", enabled=True):
    return SimpleNamespace(
        environment=environment, preview_acceptance_fixture_enabled=enabled
    )


def authorized_context():
    return context(
        AdministrationPermission.COMPANY_ADMINISTER,
        AdministrationPermission.IDENTITY_ONBOARDING_MANAGE,
    )


def audit_service():
    service = Mock()
    service.stage.return_value = SimpleNamespace(id=uuid4())
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "environment,enabled,authorized,version",
    [
        ("production", True, True, FIXTURE_VERSION),
        ("preview", False, True, FIXTURE_VERSION),
        ("preview", True, False, FIXTURE_VERSION),
        ("preview", True, True, "wrong.fixture"),
    ],
)
async def test_fixture_fails_closed(environment, enabled, authorized, version):
    service = PreviewSyntheticTenantFixtureService(
        configuration=configuration(environment, enabled), auditing=audit_service()
    )
    session = Session()
    with pytest.raises(OnboardingConflictError):
        await service.create_or_reuse(
            session,
            context=authorized_context(),
            command=PreviewSyntheticTenantCommand(version, authorized),
        )
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_fixture_rejects_unauthorized_caller():
    service = PreviewSyntheticTenantFixtureService(
        configuration=configuration(), auditing=audit_service()
    )
    with pytest.raises(OnboardingConflictError):
        await service.create_or_reuse(
            Session(),
            context=context(AdministrationPermission.COMPANY_ADMINISTER),
            command=PreviewSyntheticTenantCommand(FIXTURE_VERSION, True),
        )


@pytest.mark.asyncio
async def test_fixture_create_is_deterministic_and_audited():
    auditing = audit_service()
    service = PreviewSyntheticTenantFixtureService(
        configuration=configuration(), auditing=auditing
    )
    session = Session()
    result = await service.create_or_reuse(
        session,
        context=authorized_context(),
        command=PreviewSyntheticTenantCommand(FIXTURE_VERSION, True),
    )
    assert result.action == "created"
    assert result.company_id == FIXTURE_COMPANY_ID
    assert result.branch_id == FIXTURE_BRANCH_ID
    assert session.company.code == FIXTURE_COMPANY_CODE
    assert session.branch.code == FIXTURE_BRANCH_CODE
    auditing.stage.assert_called_once()
    entry = auditing.stage.call_args.args[1]
    assert entry.actor_user_id is not None
    assert entry.details["fixture_version"] == FIXTURE_VERSION
    assert entry.details["action"] == "created"


@pytest.mark.asyncio
async def test_fixture_reuses_exact_state_without_duplicate_creation():
    auditing = audit_service()
    service = PreviewSyntheticTenantFixtureService(
        configuration=configuration(), auditing=auditing
    )
    first = Session()
    await service.create_or_reuse(
        first,
        context=authorized_context(),
        command=PreviewSyntheticTenantCommand(FIXTURE_VERSION, True),
    )
    second = Session(first.company, first.branch)
    result = await service.create_or_reuse(
        second,
        context=authorized_context(),
        command=PreviewSyntheticTenantCommand(FIXTURE_VERSION, True),
    )
    assert result.action == "reused"
    assert second.added == []
    assert second.execute.await_count == 1


@pytest.mark.asyncio
async def test_reset_preserves_tenant_and_records_audit():
    auditing = audit_service()
    service = PreviewSyntheticTenantFixtureService(
        configuration=configuration(), auditing=auditing
    )
    session = Session()
    await service.create_or_reuse(
        session,
        context=authorized_context(),
        command=PreviewSyntheticTenantCommand(FIXTURE_VERSION, True),
    )
    auditing.reset_mock()
    reset_session = Session(session.company, session.branch)
    audit_id = await service.record_reset(
        reset_session,
        context=authorized_context(),
        command=PreviewSyntheticTenantCommand(FIXTURE_VERSION, True),
    )
    assert audit_id == auditing.stage.return_value.id
    assert reset_session.added == []
    entry = auditing.stage.call_args.args[1]
    assert entry.details["action"] == "reset_in_place"


@pytest.mark.asyncio
async def test_fixture_postgresql_concurrent_create_reuses_one_tenant():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = PreviewSyntheticTenantFixtureService(configuration=configuration())
    command = PreviewSyntheticTenantCommand(FIXTURE_VERSION, True)

    async def invoke():
        async with factory() as session:
            return await service.create_or_reuse(
                session, context=authorized_context(), command=command
            )

    first, second = await asyncio.gather(invoke(), invoke())
    assert {first.action, second.action} == {"created", "reused"}
    async with factory() as session:
        assert await session.scalar(
            select(func.count()).select_from(Company).where(Company.id == FIXTURE_COMPANY_ID)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(Branch).where(Branch.id == FIXTURE_BRANCH_ID)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(AuditRecord).where(
                AuditRecord.action == "preview.acceptance_tenant_fixture",
                AuditRecord.company_id == FIXTURE_COMPANY_ID,
            )
        ) == 2
    await engine.dispose()
