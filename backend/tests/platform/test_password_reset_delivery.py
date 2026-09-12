import base64
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import Settings, settings
from app.platform.auth.models import (
    PasswordResetToken,
    ProtectedPasswordResetDeliveryEnvelope,
)
from app.platform.auth.recovery_delivery import (
    EmployeeRecoveryDeliveryService,
    RecoveryDeliveryError,
)
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.notifications.models import NotificationOutbox
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def recovery_settings() -> Settings:
    assert settings.access_token_signing_key is not None
    assert settings.security_token_hmac_key is not None
    return Settings(
        environment="test",
        database_url=settings.database_url,
        redis_url=settings.redis_url,
        access_token_signing_key=settings.access_token_signing_key,
        security_token_hmac_key=settings.security_token_hmac_key,
        identity_onboarding_delivery_keys={
            "test": base64.urlsafe_b64encode(b"r" * 32).decode()
        },
        identity_onboarding_active_delivery_kid="test",
    )


@pytest_asyncio.fixture
async def recovery_database() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], EmployeeRecoveryDeliveryService]
]:
    configuration = recovery_settings()
    engine = create_async_engine(configuration.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "TRUNCATE authentication_security_events, "
                "notification_delivery_evidence, notification_outbox, "
                "protected_password_reset_delivery_envelopes, password_reset_tokens, "
                "employees, membership_branch_access, memberships, branches, companies, "
                "users CASCADE"
            )
        )
    try:
        yield factory, EmployeeRecoveryDeliveryService(configuration)
    finally:
        await engine.dispose()


async def employee_fixture(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[User, Company, Branch, Membership]:
    async with factory() as session, session.begin():
        company = Company(
            name="Recovery Test Company",
            code=f"RECOVERY{uuid4().hex[:8].upper()}",
            timezone="America/New_York",
            status="active",
        )
        session.add(company)
        await session.flush()
        branch = Branch(
            company_id=company.id,
            name="Main",
            code="MAIN",
            timezone="America/New_York",
            status="active",
            is_primary=True,
        )
        user = User(
            normalized_email=f"employee-{uuid4().hex}@example.com",
            first_name="Recovery",
            last_name="Employee",
            display_name="Recovery Employee",
            status="active",
            authorization_version=1,
        )
        session.add_all([branch, user])
        await session.flush()
        membership = Membership(
            user_id=user.id,
            company_id=company.id,
            status="active",
            default_branch_id=branch.id,
            has_all_branch_access=True,
        )
        session.add(membership)
        await session.flush()
        session.add(
            Employee(
                company_id=company.id,
                membership_id=membership.id,
                home_branch_id=branch.id,
                employee_number=f"E-{uuid4().hex[:8]}",
                first_name="Recovery",
                last_name="Employee",
                display_name="Recovery Employee",
                employee_type="employee",
                status="active",
            )
        )
    return user, company, branch, membership


def context_for(
    user: User, company: Company, branch: Branch, membership: Membership
) -> AuthorizationContext:
    return AuthorizationContext(
        user=user,
        company=company,
        membership=membership,
        authorized_branches=(branch,),
        active_branch=branch,
        effective_roles=(),
        effective_permissions=(),
        credential_version=1,
        authorization_version=1,
    )


@pytest.mark.asyncio
async def test_reset_outbox_is_encrypted_secret_free_and_idempotent(
    recovery_database: tuple[
        async_sessionmaker[AsyncSession], EmployeeRecoveryDeliveryService
    ],
) -> None:
    factory, service = recovery_database
    user, company, branch, membership = await employee_fixture(factory)
    async with factory() as session:
        first = await service.request_public(
            session,
            email=user.normalized_email,
            ip_address="127.0.0.1",
            user_agent="test",
        )
    async with factory() as session:
        repeated = await service.request_public(
            session,
            email=user.normalized_email,
            ip_address="127.0.0.1",
            user_agent="test",
        )
    assert first is not None and repeated is not None
    assert (first.token_id, first.outbox_id) == (repeated.token_id, repeated.outbox_id)
    assert first.plaintext_token is not None

    async with factory() as session:
        outbox = await session.get(NotificationOutbox, first.outbox_id)
        envelope = await session.scalar(
            select(ProtectedPasswordResetDeliveryEnvelope).where(
                ProtectedPasswordResetDeliveryEnvelope.password_reset_token_id
                == first.token_id
            )
        )
        assert outbox is not None and envelope is not None
        assert outbox.payload == {
            "password_reset_token_id": str(first.token_id),
            "protected_envelope": True,
        }
        serialized = str(outbox.payload)
        assert first.plaintext_token not in serialized
        assert first.plaintext_token.encode() not in envelope.ciphertext
        status = await service.status_admin(
            session,
            context=context_for(user, company, branch, membership),
            user_id=user.id,
        )
        assert status.state == "RESET_PENDING_DELIVERY"
    now = datetime.now(timezone.utc)
    async with factory() as session, session.begin():
        outbox = await session.get(NotificationOutbox, first.outbox_id)
        assert outbox is not None
        outbox.status = "accepted"
        outbox.submitted_at = now
        outbox.provider_reference = "provider-reference-withheld"
    async with factory() as session:
        accepted = await service.status_admin(
            session,
            context=context_for(user, company, branch, membership),
            user_id=user.id,
        )
        assert accepted.state == "RESET_ACCEPTED_BY_PROVIDER"
        assert accepted.provider_reference_present
    async with factory() as session, session.begin():
        outbox = await session.get(NotificationOutbox, first.outbox_id)
        assert outbox is not None
        outbox.status = "sent"
        outbox.sent_at = datetime.now(timezone.utc)
    async with factory() as session:
        delivered = await service.status_admin(
            session,
            context=context_for(user, company, branch, membership),
            user_id=user.id,
        )
        assert delivered.state == "RESET_DELIVERED"


@pytest.mark.asyncio
async def test_failed_reset_reissue_preserves_history_and_rejects_inactive_authority(
    recovery_database: tuple[
        async_sessionmaker[AsyncSession], EmployeeRecoveryDeliveryService
    ],
) -> None:
    factory, service = recovery_database
    user, _, _, membership = await employee_fixture(factory)
    async with factory() as session:
        first = await service.request_public(
            session, email=user.normalized_email, ip_address=None, user_agent=None
        )
    assert first is not None
    async with factory() as session, session.begin():
        outbox = await session.get(NotificationOutbox, first.outbox_id)
        assert outbox is not None
        outbox.status = "failed"
        outbox.failed_at = datetime.now(timezone.utc)
        outbox.terminal_failure = True
    async with factory() as session:
        replacement = await service.request_public(
            session, email=user.normalized_email, ip_address=None, user_agent=None
        )
    assert replacement is not None and replacement.token_id != first.token_id
    async with factory() as session:
        original = await session.get(PasswordResetToken, first.token_id)
        history = await session.scalar(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.recipient == user.normalized_email)
        )
        assert original is not None and original.revoked_at is not None
        assert history == 2
    async with factory() as session, session.begin():
        persisted_membership = await session.get(Membership, membership.id)
        assert persisted_membership is not None
        persisted_membership.status = "suspended"
    async with factory() as session:
        denied = await service.request_public(
            session, email=user.normalized_email, ip_address=None, user_agent=None
        )
    assert denied is None
    async with factory() as session, session.begin():
        persisted_membership = await session.get(Membership, membership.id)
        persisted_user = await session.get(User, user.id)
        assert persisted_membership is not None and persisted_user is not None
        persisted_membership.status = "active"
        persisted_user.status = "disabled"
        persisted_user.disabled_at = datetime.now(timezone.utc)
    async with factory() as session:
        disabled = await service.request_public(
            session, email=user.normalized_email, ip_address=None, user_agent=None
        )
    assert disabled is None
    async with factory() as session:
        with pytest.raises(RecoveryDeliveryError):
            await service.claim(session, token_id=replacement.token_id)


@pytest.mark.asyncio
async def test_expired_reset_material_cannot_be_claimed_and_is_destroyed(
    recovery_database: tuple[
        async_sessionmaker[AsyncSession], EmployeeRecoveryDeliveryService
    ],
) -> None:
    factory, service = recovery_database
    user, _, _, _ = await employee_fixture(factory)
    async with factory() as session:
        issued = await service.request_public(
            session, email=user.normalized_email, ip_address=None, user_agent=None
        )
    assert issued is not None
    async with factory() as session, session.begin():
        token = await session.get(PasswordResetToken, issued.token_id)
        assert token is not None
        token.issued_at = datetime.now(timezone.utc) - timedelta(hours=2)
        token.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    async with factory() as session:
        with pytest.raises(
            RecoveryDeliveryError,
            match="Protected recovery delivery is unavailable",
        ):
            await service.claim(session, token_id=issued.token_id)
    async with factory() as session:
        envelope = await session.scalar(
            select(ProtectedPasswordResetDeliveryEnvelope).where(
                ProtectedPasswordResetDeliveryEnvelope.password_reset_token_id
                == issued.token_id
            )
        )
        assert envelope is not None
        assert envelope.status == "destroyed"
        assert envelope.ciphertext == b""
