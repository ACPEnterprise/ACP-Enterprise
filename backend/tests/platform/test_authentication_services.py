import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, settings
from app.platform.auth.access_tokens import AccessTokenService
from app.platform.auth.errors import (
    AuthenticationError,
    InvalidCredentialsError,
    InvalidTokenError,
    RefreshTokenReuseError,
    SessionInvalidError,
    RateLimitExceededError,
)
from app.platform.auth.models import (
    AuthenticationSecurityEvent,
    AuthenticationSession,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
)
from app.platform.auth.passwords import PasswordService
from app.platform.auth.rate_limit import AuthenticationRateLimiter
from app.platform.auth.services import (
    AuthenticationService,
    CredentialService,
    RecoveryService,
    utc_now,
)
from app.platform.auth.tokens import SecurityTokenService
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.permissions.models import MembershipRole, Permission, Role
from app.platform.users.models import User, UserCredential


MODEL_REGISTRY = (Branch, Company)


def service_settings() -> Settings:
    assert settings.access_token_signing_key is not None
    assert settings.security_token_hmac_key is not None
    return Settings(
        environment="test",
        database_url=settings.database_url,
        redis_url=settings.redis_url,
        access_token_signing_key=settings.access_token_signing_key,
        security_token_hmac_key=settings.security_token_hmac_key,
        argon2_time_cost=1,
        argon2_memory_cost_kib=1024,
        argon2_parallelism=1,
        credential_lockout_threshold=2,
        credential_lockout_duration_seconds=60,
    )


@pytest_asyncio.fixture
async def service_stack() -> AsyncIterator[
    tuple[
        AsyncEngine,
        async_sessionmaker[AsyncSession],
        PasswordService,
        CredentialService,
        AuthenticationService,
        RecoveryService,
    ]
]:
    configuration = service_settings()
    engine = create_async_engine(configuration.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    password_service = PasswordService(configuration)
    token_service = SecurityTokenService(configuration)
    access_service = AccessTokenService(configuration)
    credential_service = CredentialService(password_service, configuration)
    authentication_service = AuthenticationService(
        password_service,
        token_service,
        access_service,
        configuration,
    )
    recovery_service = RecoveryService(
        password_service,
        token_service,
        configuration,
    )
    try:
        yield (
            engine,
            session_factory,
            password_service,
            credential_service,
            authentication_service,
            recovery_service,
        )
    finally:
        await engine.dispose()


async def create_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    email: str,
    status: str = "active",
) -> UUID:
    user_id = uuid4()
    async with session_factory() as session, session.begin():
        session.add(
            User(
                id=user_id,
                normalized_email=email,
                first_name="Service",
                last_name="Tester",
                display_name="Service Tester",
                status=status,
                authorization_version=1,
            )
        )
    return user_id


async def set_password(
    session_factory: async_sessionmaker[AsyncSession],
    credential_service: CredentialService,
    user_id: UUID,
    password: str = "correct horse battery staple",
) -> None:
    async with session_factory() as session:
        await credential_service.set_initial_password(
            session,
            user_id=user_id,
            password=password,
        )


@pytest.mark.asyncio
async def test_login_failure_lockout_and_authentication_boundary(
    service_stack: tuple[
        AsyncEngine,
        async_sessionmaker[AsyncSession],
        PasswordService,
        CredentialService,
        AuthenticationService,
        RecoveryService,
    ],
) -> None:
    _, factory, password_service, credential_service, auth_service, _ = service_stack
    user_id = await create_user(factory, email="login-service@example.com")
    await set_password(factory, credential_service, user_id)
    async with factory() as session:
        permission_count_before = await session.scalar(
            select(func.count()).select_from(Permission)
        )
        employee_count_before = await session.scalar(
            select(func.count()).select_from(Employee)
        )
        role_count_before = await session.scalar(select(func.count()).select_from(Role))
        membership_role_count_before = await session.scalar(
            select(func.count()).select_from(MembershipRole)
        )

    async with factory() as session:
        result = await auth_service.authenticate(
            session,
            email="LOGIN-SERVICE@example.com",
            password="correct horse battery staple",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
    claims = auth_service.access_token_service.decode(result.access_token)
    assert claims.user_id == user_id
    assert claims.session_id == result.session_id
    assert claims.credential_version == 1
    assert claims.authorization_version == 1

    async with factory() as session:
        credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == user_id)
        )
        assert credential is not None
        assert "correct horse battery staple" not in credential.password_hash
        assert password_service.verify_password(
            credential.password_hash, "correct horse battery staple"
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuthenticationSecurityEvent)
                .where(
                    AuthenticationSecurityEvent.user_id == user_id,
                    AuthenticationSecurityEvent.event_type == "login_succeeded",
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Membership)
                .where(Membership.user_id == user_id)
            )
            == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(Employee))
            == employee_count_before
        )
        assert (
            await session.scalar(select(func.count()).select_from(Role))
            == role_count_before
        )
        assert (
            await session.scalar(select(func.count()).select_from(Permission))
            == permission_count_before
        )
        assert (
            await session.scalar(select(func.count()).select_from(MembershipRole))
            == membership_role_count_before
        )

    public_messages: list[str] = []
    for email in ("login-service@example.com", "missing-service@example.com"):
        async with factory() as session:
            with pytest.raises(InvalidCredentialsError) as caught:
                await auth_service.authenticate(
                    session,
                    email=email,
                    password="wrong password value",
                )
        public_messages.append(str(caught.value))
    assert public_messages[0] == public_messages[1]

    async with factory() as session:
        with pytest.raises(InvalidCredentialsError):
            await auth_service.authenticate(
                session,
                email="login-service@example.com",
                password="wrong password again",
            )
    async with factory() as session:
        credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == user_id)
        )
        assert credential is not None
        assert credential.failed_login_count == 2
        assert credential.locked_until is not None

    inactive_id = await create_user(
        factory, email="inactive-service@example.com", status="disabled"
    )
    await set_password(factory, credential_service, inactive_id)
    async with factory() as session:
        with pytest.raises(InvalidCredentialsError):
            await auth_service.authenticate(
                session,
                email="inactive-service@example.com",
                password="correct horse battery staple",
            )


@pytest.mark.asyncio
async def test_refresh_rotation_reuse_versions_and_concurrency(
    service_stack: tuple[
        AsyncEngine,
        async_sessionmaker[AsyncSession],
        PasswordService,
        CredentialService,
        AuthenticationService,
        RecoveryService,
    ],
) -> None:
    _, factory, _, credential_service, auth_service, _ = service_stack
    user_id = await create_user(factory, email="refresh-service@example.com")
    await set_password(factory, credential_service, user_id)
    async with factory() as session:
        login = await auth_service.authenticate(
            session,
            email="refresh-service@example.com",
            password="correct horse battery staple",
        )
    original_hash = auth_service.token_service.hash_token(login.refresh_token)
    async with factory() as session:
        rotated = await auth_service.rotate_refresh_token(
            session, plaintext_token=login.refresh_token
        )
    async with factory() as session:
        original = await session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == original_hash)
        )
        replacement = await session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash
                == auth_service.token_service.hash_token(rotated.refresh_token)
            )
        )
        assert original is not None and replacement is not None
        assert original.used_at is not None
        assert original.replaced_by_token_id == replacement.id
        assert replacement.parent_token_id == original.id
        assert replacement.family_id == original.family_id
        assert replacement.sequence_number == original.sequence_number + 1

    async with factory() as session:
        with pytest.raises(RefreshTokenReuseError):
            await auth_service.rotate_refresh_token(
                session, plaintext_token=login.refresh_token
            )
    async with factory() as session:
        compromised = await session.get(AuthenticationSession, login.session_id)
        assert compromised is not None
        assert compromised.status == "compromised"
        family_tokens = list(
            (
                await session.scalars(
                    select(RefreshToken).where(
                        RefreshToken.family_id == original.family_id
                    )
                )
            ).all()
        )
        assert all(token.revoked_at is not None for token in family_tokens)

    concurrent_id = await create_user(factory, email="concurrent-refresh@example.com")
    await set_password(factory, credential_service, concurrent_id)
    async with factory() as session:
        concurrent_login = await auth_service.authenticate(
            session,
            email="concurrent-refresh@example.com",
            password="correct horse battery staple",
        )

    async def rotate_once() -> object:
        async with factory() as session:
            try:
                return await auth_service.rotate_refresh_token(
                    session,
                    plaintext_token=concurrent_login.refresh_token,
                )
            except AuthenticationError as error:
                return error

    outcomes = await asyncio.gather(rotate_once(), rotate_once())
    assert (
        sum(not isinstance(outcome, AuthenticationError) for outcome in outcomes) == 1
    )
    assert sum(isinstance(outcome, RefreshTokenReuseError) for outcome in outcomes) == 1

    version_id = await create_user(factory, email="version-refresh@example.com")
    await set_password(factory, credential_service, version_id)
    async with factory() as session:
        version_login = await auth_service.authenticate(
            session,
            email="version-refresh@example.com",
            password="correct horse battery staple",
        )
    async with factory() as session, session.begin():
        await session.execute(
            update(User).where(User.id == version_id).values(authorization_version=2)
        )
    async with factory() as session:
        with pytest.raises(SessionInvalidError):
            await auth_service.rotate_refresh_token(
                session, plaintext_token=version_login.refresh_token
            )


@pytest.mark.asyncio
async def test_logout_password_reset_and_email_verification(
    service_stack: tuple[
        AsyncEngine,
        async_sessionmaker[AsyncSession],
        PasswordService,
        CredentialService,
        AuthenticationService,
        RecoveryService,
    ],
) -> None:
    _, factory, password_service, credential_service, auth_service, recovery = (
        service_stack
    )
    user_id = await create_user(factory, email="recovery-service@example.com")
    await set_password(factory, credential_service, user_id)
    async with factory() as session:
        first_login = await auth_service.authenticate(
            session,
            email="recovery-service@example.com",
            password="correct horse battery staple",
        )
    async with factory() as session:
        await auth_service.logout(
            session,
            authentication_session_id=first_login.session_id,
            actor_user_id=user_id,
        )
        await auth_service.logout(
            session,
            authentication_session_id=first_login.session_id,
            actor_user_id=user_id,
        )
    async with factory() as session:
        session_record = await session.get(
            AuthenticationSession, first_login.session_id
        )
        assert session_record is not None and session_record.status == "revoked"
        tokens = list(
            (
                await session.scalars(
                    select(RefreshToken).where(
                        RefreshToken.session_id == first_login.session_id
                    )
                )
            ).all()
        )
        assert all(token.revoked_at is not None for token in tokens)

    async with factory() as session:
        old_delivery = await recovery.request_password_reset(
            session, email="recovery-service@example.com"
        )
    async with factory() as session:
        delivery = await recovery.request_password_reset(
            session, email="recovery-service@example.com"
        )
    assert old_delivery.plaintext_token is not None
    assert delivery.plaintext_token is not None
    async with factory() as session:
        persisted = await session.scalar(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash
                == auth_service.token_service.hash_token(delivery.plaintext_token)
            )
        )
        old = await session.scalar(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash
                == auth_service.token_service.hash_token(old_delivery.plaintext_token)
            )
        )
        assert (
            persisted is not None and persisted.token_hash != delivery.plaintext_token
        )
        assert old is not None and old.revoked_at is not None

    async with factory() as session:
        await recovery.confirm_password_reset(
            session,
            plaintext_token=delivery.plaintext_token,
            new_password="new correct horse battery staple",
        )
    async with factory() as session:
        credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == user_id)
        )
        assert credential is not None and credential.credential_version == 2
        assert password_service.verify_password(
            credential.password_hash, "new correct horse battery staple"
        )
    async with factory() as session:
        with pytest.raises(InvalidTokenError):
            await recovery.confirm_password_reset(
                session,
                plaintext_token=delivery.plaintext_token,
                new_password="another valid password value",
            )

    async with factory() as session:
        verification = await recovery.request_email_verification(
            session, user_id=user_id
        )
    assert verification.plaintext_token is not None
    async with factory() as session, session.begin():
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(normalized_email="changed-recovery@example.com")
        )
    async with factory() as session:
        with pytest.raises(InvalidTokenError):
            await recovery.confirm_email_verification(
                session, plaintext_token=verification.plaintext_token
            )
    async with factory() as session:
        current_verification = await recovery.request_email_verification(
            session, user_id=user_id
        )
    assert current_verification.plaintext_token is not None
    async with factory() as session:
        await recovery.confirm_email_verification(
            session, plaintext_token=current_verification.plaintext_token
        )
    async with factory() as session:
        user = await session.get(User, user_id)
        assert user is not None and user.email_verified_at is not None
        verification_record = await session.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash
                == auth_service.token_service.hash_token(
                    current_verification.plaintext_token
                )
            )
        )
        assert verification_record is not None
        assert verification_record.consumed_at is not None


@pytest.mark.asyncio
async def test_expired_revoked_refresh_and_rate_limit_enforcement(
    service_stack: tuple[
        AsyncEngine,
        async_sessionmaker[AsyncSession],
        PasswordService,
        CredentialService,
        AuthenticationService,
        RecoveryService,
    ],
) -> None:
    _, factory, _, credential_service, auth_service, _ = service_stack
    user_id = await create_user(factory, email="refresh-state@example.com")
    await set_password(factory, credential_service, user_id)

    async with factory() as session:
        expired_login = await auth_service.authenticate(
            session,
            email="refresh-state@example.com",
            password="correct horse battery staple",
        )
    expired_hash = auth_service.token_service.hash_token(expired_login.refresh_token)
    now = utc_now()
    async with factory() as session, session.begin():
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == expired_hash)
            .values(
                issued_at=now - timedelta(days=2),
                expires_at=now - timedelta(days=1),
            )
        )
    async with factory() as session:
        with pytest.raises(InvalidTokenError):
            await auth_service.rotate_refresh_token(
                session, plaintext_token=expired_login.refresh_token
            )

    async with factory() as session:
        active_login = await auth_service.authenticate(
            session,
            email="refresh-state@example.com",
            password="correct horse battery staple",
        )
    active_hash = auth_service.token_service.hash_token(active_login.refresh_token)
    async with factory() as session, session.begin():
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == active_hash)
            .values(revoked_at=utc_now(), revocation_reason="test_revocation")
        )
    async with factory() as session:
        with pytest.raises(InvalidTokenError):
            await auth_service.rotate_refresh_token(
                session, plaintext_token=active_login.refresh_token
            )

    limiter = AuthenticationRateLimiter(service_settings())
    identifier = f"pytest-{uuid4()}"
    await limiter.enforce(
        bucket="test",
        identifier_hash=identifier,
        limit=1,
        window_seconds=30,
    )
    with pytest.raises(RateLimitExceededError):
        await limiter.enforce(
            bucket="test",
            identifier_hash=identifier,
            limit=1,
            window_seconds=30,
        )
