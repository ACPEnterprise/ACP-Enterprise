import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.events.models import BusinessEvent
from app.platform.auth import models as auth_models  # noqa: F401
from app.platform.audit.models import AuditRecord
from app.platform.audit.service import AuditEntry, AuditService
from app.platform.branch import models as branch_models  # noqa: F401
from app.platform.company import membership_models  # noqa: F401
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees import models as employee_models  # noqa: F401
from app.platform.permissions.authorization import (
    AuthorizationContext,
    PermissionDeniedError,
)
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.models import Permission
from app.platform.users.identity_models import PendingEmailChange
from app.platform.users.identity_repository import UserIdentityRepository
from app.platform.users.identity_service import (
    IdentityAdministrationConflictError,
    IdentityAdministrationNotFoundError,
    IdentityAdministrationService,
    IdentityAdministrationTokenError,
)
from app.platform.users.models import User, UserCredential


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def identity_service_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


async def create_context_and_target(
    factory: async_sessionmaker[AsyncSession],
    *,
    with_permission: bool = True,
) -> tuple[AuthorizationContext, User]:
    suffix = uuid4().hex[:10]
    company = Company(
        name=f"Identity Service {suffix}",
        code=f"IDS{suffix.upper()}",
        status="active",
        timezone="America/New_York",
    )
    administrator = User(
        normalized_email=f"administrator-{suffix}@example.com",
        first_name="Identity",
        last_name="Administrator",
        display_name="Identity Administrator",
        status="active",
    )
    target = User(
        normalized_email=f"target-{suffix}@example.com",
        first_name="Identity",
        last_name="Target",
        display_name="Identity Target",
        status="active",
    )
    async with factory() as session, session.begin():
        session.add_all([company, administrator, target])
        await session.flush()
        admin_membership = Membership(
            user_id=administrator.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=True,
            invited_at=utc_now(),
            accepted_at=utc_now(),
        )
        target_membership = Membership(
            user_id=target.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=False,
            invited_at=utc_now(),
            accepted_at=utc_now(),
        )
        session.add_all(
            [
                admin_membership,
                target_membership,
                UserCredential(
                    user_id=administrator.id,
                    password_hash="$argon2id$administrator-test-hash",
                ),
                UserCredential(
                    user_id=target.id,
                    password_hash="$argon2id$target-test-hash",
                ),
            ]
        )
        permission: Permission | None = None
        if with_permission:
            permission = Permission(
                code=AdministrationPermission.COMPANY_ADMINISTER,
                name="Identity administration fixture",
                resource="company",
                action="administer",
                status="active",
            )
        await session.flush()

    effective_permissions = (permission,) if permission is not None else ()
    return (
        AuthorizationContext(
            user=administrator,
            company=company,
            membership=admin_membership,
            authorized_branches=(),
            active_branch=None,
            effective_roles=(),
            effective_permissions=effective_permissions,
            credential_version=1,
            authorization_version=1,
        ),
        target,
    )


@pytest.mark.asyncio
async def test_email_change_happy_path_is_atomic_and_emits_committed_events(
    identity_service_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_service_database
    context, target = await create_context_and_target(factory)
    service = IdentityAdministrationService()
    proposed = f"changed-{uuid4().hex}@example.com"

    async with factory() as session:
        assert await service.is_email_available(
            session,
            context=context,
            target_user_id=target.id,
            proposed_email=proposed,
        )
    async with factory() as session:
        delivery = await service.request_administrative_email_change(
            session,
            context=context,
            target_user_id=target.id,
            proposed_email=proposed.upper(),
        )
    assert delivery.created
    assert delivery.plaintext_token is not None
    assert delivery.change.verification_token_hash != delivery.plaintext_token
    assert delivery.change.proposed_normalized_email == proposed
    async with factory() as session:
        assert not await service.is_email_available(
            session,
            context=context,
            target_user_id=target.id,
            proposed_email=proposed,
        )

    async with factory() as session:
        changed_user = await service.confirm_email_change(
            session,
            context=context,
            plaintext_token=delivery.plaintext_token,
        )
    assert changed_user.normalized_email == proposed

    async with factory() as session:
        credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == target.id)
        )
        event_types = set(
            (
                await session.scalars(
                    select(BusinessEvent.event_type).where(
                        BusinessEvent.entity_id == target.id
                    )
                )
            ).all()
        )
        audit_actions = set(
            (
                await session.scalars(
                    select(AuditRecord.action).where(
                        AuditRecord.resource_id == target.id
                    )
                )
            ).all()
        )
    assert credential is not None
    assert credential.credential_version == 2
    assert "identity.email_change_requested" in event_types
    assert "identity.email_changed" in event_types
    assert "identity.email_change_requested" in audit_actions
    assert "identity.email_changed" in audit_actions


@pytest.mark.asyncio
async def test_duplicate_email_request_is_rejected_without_extra_event(
    identity_service_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_service_database
    context, target = await create_context_and_target(factory)
    service = IdentityAdministrationService()
    proposed = f"duplicate-{uuid4().hex}@example.com"
    async with factory() as session:
        await service.request_administrative_email_change(
            session,
            context=context,
            target_user_id=target.id,
            proposed_email=proposed,
        )
    with pytest.raises(IdentityAdministrationConflictError):
        async with factory() as session:
            await service.request_administrative_email_change(
                session,
                context=context,
                target_user_id=target.id,
                proposed_email=proposed,
            )
    async with factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(
                BusinessEvent.entity_id == target.id,
                BusinessEvent.event_type == "identity.email_change_requested",
            )
        )
    assert count == 1


@pytest.mark.asyncio
async def test_expired_and_revoked_email_changes_cannot_be_confirmed(
    identity_service_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_service_database
    context, target = await create_context_and_target(factory)
    service = IdentityAdministrationService()
    old_now = utc_now() - timedelta(hours=2)
    expired_token = f"expired-{uuid4().hex}"
    async with factory() as session, session.begin():
        await UserIdentityRepository.create_pending_email_change(
            session,
            user_id=target.id,
            proposed_normalized_email=f"expired-{uuid4().hex}@example.com",
            proposed_display_email=None,
            verification_token_hash=service.token_service.hash_token(expired_token),
            reason_code="company_administration",
            initiated_by_user_id=context.user.id,
            initiating_company_id=context.company.id,
            expires_at=old_now + timedelta(hours=1),
            now=old_now,
        )
    with pytest.raises(IdentityAdministrationTokenError):
        async with factory() as session:
            await service.confirm_email_change(
                session,
                context=context,
                plaintext_token=expired_token,
            )

    async with factory() as session:
        delivery = await service.request_administrative_email_change(
            session,
            context=context,
            target_user_id=target.id,
            proposed_email=f"revoked-{uuid4().hex}@example.com",
        )
    assert delivery.plaintext_token is not None
    async with factory() as session:
        assert await service.revoke_email_change(
            session,
            context=context,
            change_id=delivery.change.id,
        )
        assert not await service.revoke_email_change(
            session,
            context=context,
            change_id=delivery.change.id,
        )
    with pytest.raises(IdentityAdministrationTokenError):
        async with factory() as session:
            await service.confirm_email_change(
                session,
                context=context,
                plaintext_token=delivery.plaintext_token,
            )


@pytest.mark.asyncio
async def test_concurrent_requests_leave_one_active_pending_change(
    identity_service_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_service_database
    context, target = await create_context_and_target(factory)
    service = IdentityAdministrationService()

    async def request(email: str) -> bool:
        try:
            async with factory() as session:
                await service.request_administrative_email_change(
                    session,
                    context=context,
                    target_user_id=target.id,
                    proposed_email=email,
                )
        except IdentityAdministrationConflictError:
            return False
        return True

    outcomes = await asyncio.gather(
        request(f"concurrent-a-{uuid4().hex}@example.com"),
        request(f"concurrent-b-{uuid4().hex}@example.com"),
    )
    assert any(outcomes)
    async with factory() as session:
        pending_count = await session.scalar(
            select(func.count())
            .select_from(PendingEmailChange)
            .where(
                PendingEmailChange.user_id == target.id,
                PendingEmailChange.status == "pending",
            )
        )
    assert pending_count == 1


class FailingAuditService(AuditService):
    @staticmethod
    def stage(session: AsyncSession, entry: AuditEntry) -> AuditRecord:
        raise RuntimeError("controlled audit failure")


@pytest.mark.asyncio
async def test_transaction_rolls_back_identity_and_business_event_on_failure(
    identity_service_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_service_database
    context, target = await create_context_and_target(factory)
    service = IdentityAdministrationService(audit=FailingAuditService())
    proposed = f"rollback-{uuid4().hex}@example.com"
    with pytest.raises(RuntimeError, match="controlled audit failure"):
        async with factory() as session:
            await service.request_administrative_email_change(
                session,
                context=context,
                target_user_id=target.id,
                proposed_email=proposed,
            )
    async with factory() as session:
        pending_count = await session.scalar(
            select(func.count())
            .select_from(PendingEmailChange)
            .where(PendingEmailChange.user_id == target.id)
        )
        event_count = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(BusinessEvent.entity_id == target.id)
        )
    assert pending_count == 0
    assert event_count == 0


@pytest.mark.asyncio
async def test_authorization_failure_precedes_identity_mutation(
    identity_service_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_service_database
    context, target = await create_context_and_target(factory, with_permission=False)
    service = IdentityAdministrationService()
    with pytest.raises(PermissionDeniedError):
        async with factory() as session:
            await service.request_administrative_email_change(
                session,
                context=context,
                target_user_id=target.id,
                proposed_email=f"denied-{uuid4().hex}@example.com",
            )


@pytest.mark.asyncio
async def test_company_administrator_cannot_mutate_another_company_request(
    identity_service_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_service_database
    first_context, target = await create_context_and_target(factory)
    second_context, _ = await create_context_and_target(factory)
    async with factory() as session, session.begin():
        session.add(
            Membership(
                user_id=target.id,
                company_id=second_context.company.id,
                status="active",
                has_all_branch_access=False,
                invited_at=utc_now(),
                accepted_at=utc_now(),
            )
        )
    service = IdentityAdministrationService()
    async with factory() as session:
        delivery = await service.request_administrative_email_change(
            session,
            context=first_context,
            target_user_id=target.id,
            proposed_email=f"company-boundary-{uuid4().hex}@example.com",
        )
    assert delivery.plaintext_token is not None

    with pytest.raises(IdentityAdministrationNotFoundError):
        async with factory() as session:
            await service.revoke_email_change(
                session,
                context=second_context,
                change_id=delivery.change.id,
            )
    with pytest.raises(IdentityAdministrationNotFoundError):
        async with factory() as session:
            await service.confirm_email_change(
                session,
                context=second_context,
                plaintext_token=delivery.plaintext_token,
            )


@pytest.mark.asyncio
async def test_forced_reset_is_idempotent_and_clears_only_after_password_change(
    identity_service_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_service_database
    context, target = await create_context_and_target(factory)
    service = IdentityAdministrationService()
    async with factory() as session:
        credential, changed = await service.require_password_reset(
            session,
            context=context,
            target_user_id=target.id,
            reason_code="administrator_required",
        )
    assert changed
    required_version = credential.credential_version
    async with factory() as session:
        repeated, repeated_changed = await service.require_password_reset(
            session,
            context=context,
            target_user_id=target.id,
            reason_code="administrator_required",
        )
    assert not repeated_changed
    assert repeated.credential_version == required_version

    with pytest.raises(IdentityAdministrationConflictError):
        async with factory() as session:
            await service.clear_password_reset_after_change(
                session,
                context=context,
                target_user_id=target.id,
            )

    async with factory() as session, session.begin():
        locked = await UserIdentityRepository.get_credential_for_update(
            session, target.id
        )
        assert locked is not None
        assert locked.password_change_required_at is not None
        locked.password_changed_at = locked.password_change_required_at + timedelta(
            seconds=1
        )
    async with factory() as session:
        cleared, clear_changed = await service.clear_password_reset_after_change(
            session,
            context=context,
            target_user_id=target.id,
        )
    assert clear_changed
    assert not cleared.password_change_required

    async with factory() as session:
        state = await service.get_identity_state(
            session,
            context=context,
            target_user_id=target.id,
        )
    assert not state.password_change_required
    assert state.password_change_required_cleared_at is not None
