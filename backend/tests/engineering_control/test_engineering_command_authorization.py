from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.engineering_control.commands import (
    ApproveEngineeringCommand,
    CancelEngineeringCommand,
    EngineeringCommandQuery,
)
from app.engineering_control.errors import (
    EngineeringCommandNotFoundError,
    EngineeringCommandPermissionError,
)
from app.engineering_control.service import EngineeringControlService
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCommandPermission
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    create_input,
    seed_service_fixture,
    utc_now,
)


@pytest_asyncio.fixture
async def authorization_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    try:
        yield fixture
    finally:
        await engine.dispose()


def restricted_context(
    source: AuthorizationContext,
    permissions: tuple[str, ...],
    *,
    membership_status: str = "active",
) -> AuthorizationContext:
    membership = replace(source.membership, status=membership_status)
    return AuthorizationContext(
        user=source.user,
        company=source.company,
        membership=membership,
        authorized_branches=source.authorized_branches,
        active_branch=source.active_branch,
        effective_roles=(),
        effective_permissions=context_with_permissions(
            source.user,
            source.company,
            membership,
            permissions,
        ).effective_permissions,
        credential_version=source.credential_version,
        authorization_version=source.authorization_version,
    )


@pytest.mark.asyncio
async def test_manage_create_cancel_and_approve_permission_are_separate(
    authorization_database: ServiceFixture,
) -> None:
    fixture = authorization_database
    now = utc_now()
    service = EngineeringControlService()
    manage = restricted_context(fixture.context, (EngineeringCommandPermission.MANAGE,))
    async with fixture.factory() as session:
        created = await service.create_command(
            session, context=manage, command=create_input(now=now), now=now
        )
    approval = ApproveEngineeringCommand(
        command_id=created.id,
        expected_version=1,
        instruction_digest=created.instruction_digest,
        request_digest=created.request_digest,
        repository_key=created.repository_key,
        expected_branch=created.expected_branch,
        expected_head=created.expected_head,
        requested_code_changes=created.requested_code_changes,
    )
    async with fixture.factory() as session:
        with pytest.raises(EngineeringCommandPermissionError):
            await service.approve_command(
                session, context=manage, command=approval, now=now
            )
    approve = restricted_context(
        fixture.context, (EngineeringCommandPermission.APPROVE,)
    )
    async with fixture.factory() as session:
        approved = await service.approve_command(
            session, context=approve, command=approval, now=now + timedelta(minutes=1)
        )
    async with fixture.factory() as session:
        canceled = await service.cancel_command(
            session,
            context=manage,
            command=CancelEngineeringCommand(
                command_id=approved.id,
                expected_version=2,
                reason_code="owner_requested",
            ),
            now=now + timedelta(minutes=2),
        )
    assert canceled.canceled_by_user_id == fixture.context.user.id


@pytest.mark.asyncio
async def test_read_and_missing_permissions_cannot_mutate(
    authorization_database: ServiceFixture,
) -> None:
    fixture = authorization_database
    now = utc_now()
    service = EngineeringControlService()
    for permissions in ((EngineeringCommandPermission.READ,), ()):
        context = restricted_context(fixture.context, permissions)
        async with fixture.factory() as session:
            with pytest.raises(EngineeringCommandPermissionError):
                await service.create_command(
                    session, context=context, command=create_input(now=now), now=now
                )


@pytest.mark.asyncio
async def test_listing_requires_read_active_membership_and_not_role_name(
    authorization_database: ServiceFixture,
) -> None:
    fixture = authorization_database
    service = EngineeringControlService()
    read = restricted_context(fixture.context, (EngineeringCommandPermission.READ,))
    async with fixture.factory() as session:
        result = await service.list_commands(
            session, context=read, query=EngineeringCommandQuery()
        )
    assert result.items == ()

    for context in (
        restricted_context(fixture.context, ()),
        restricted_context(
            fixture.context,
            (EngineeringCommandPermission.READ,),
            membership_status="revoked",
        ),
    ):
        async with fixture.factory() as session:
            with pytest.raises(EngineeringCommandPermissionError):
                await service.list_commands(session, context=context)

    assert not fixture.context.role_codes


@pytest.mark.asyncio
async def test_inactive_membership_and_role_name_do_not_grant_access(
    authorization_database: ServiceFixture,
) -> None:
    fixture = authorization_database
    inactive = restricted_context(
        fixture.context,
        (EngineeringCommandPermission.MANAGE,),
        membership_status="revoked",
    )
    async with fixture.factory() as session:
        with pytest.raises(EngineeringCommandPermissionError):
            await EngineeringControlService().create_command(
                session,
                context=inactive,
                command=create_input(now=utc_now()),
            )
    assert not fixture.context.role_codes


@pytest.mark.asyncio
async def test_cross_company_mutations_are_concealed_and_keys_are_independent(
    authorization_database: ServiceFixture,
) -> None:
    fixture = authorization_database
    now = utc_now()
    key = uuid4().hex
    service = EngineeringControlService()
    async with fixture.factory() as session:
        first = await service.create_command(
            session,
            context=fixture.context,
            command=create_input(now=now, idempotency_key=key),
            now=now,
        )
    async with fixture.factory() as session:
        other = await service.create_command(
            session,
            context=fixture.other_context,
            command=create_input(now=now, idempotency_key=key),
            now=now,
        )
    assert first.id != other.id

    cross_approval = ApproveEngineeringCommand(
        command_id=first.id,
        expected_version=1,
        instruction_digest=first.instruction_digest,
        request_digest=first.request_digest,
        repository_key=first.repository_key,
        expected_branch=first.expected_branch,
        expected_head=first.expected_head,
        requested_code_changes=first.requested_code_changes,
    )
    async with fixture.factory() as session:
        with pytest.raises(EngineeringCommandNotFoundError):
            await service.approve_command(
                session,
                context=fixture.other_context,
                command=cross_approval,
                now=now + timedelta(minutes=1),
            )
    async with fixture.factory() as session:
        with pytest.raises(EngineeringCommandNotFoundError):
            await service.cancel_command(
                session,
                context=fixture.other_context,
                command=CancelEngineeringCommand(
                    command_id=first.id,
                    expected_version=1,
                    reason_code="owner_requested",
                ),
                now=now + timedelta(minutes=1),
            )
