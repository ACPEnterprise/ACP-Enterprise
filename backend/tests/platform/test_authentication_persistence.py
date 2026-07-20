from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import warnings

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError, SAWarning
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import configure_mappers

from app.core.config import settings
from app.platform.auth.models import (
    AuthenticationSession,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
)
from app.platform.company.membership_models import Membership
from app.platform.permissions.models import MembershipRole
from app.platform.users.models import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def authentication_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(settings.database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


async def create_user(engine: AsyncEngine, email: str) -> UUID:
    user_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(User).values(
                id=user_id,
                normalized_email=email,
                first_name="Authentication",
                last_name="Tester",
                display_name="Authentication Tester",
                status="active",
                authorization_version=1,
            )
        )
    return user_id


async def create_session(engine: AsyncEngine, user_id: UUID) -> tuple[UUID, datetime]:
    session_id = uuid4()
    created_at = utc_now()
    async with engine.begin() as connection:
        await connection.execute(
            insert(AuthenticationSession).values(
                id=session_id,
                user_id=user_id,
                status="active",
                created_at=created_at,
                last_seen_at=created_at,
                absolute_expires_at=created_at + timedelta(days=30),
                idle_expires_at=created_at + timedelta(days=7),
                authentication_method="password",
                credential_version=1,
                authorization_version=1,
            )
        )
    return session_id, created_at


@pytest.mark.asyncio
async def test_session_status_expiration_revocation_and_restrictive_user_fk(
    authentication_engine: AsyncEngine,
) -> None:
    user_id = await create_user(authentication_engine, "session@example.com")
    session_id, created_at = await create_session(authentication_engine, user_id)

    invalid_sessions: tuple[dict[str, object], ...] = (
        {
            "status": "unknown",
            "absolute_expires_at": created_at + timedelta(days=1),
        },
        {
            "status": "active",
            "absolute_expires_at": created_at,
        },
        {
            "status": "active",
            "absolute_expires_at": created_at + timedelta(days=1),
            "revoked_at": created_at,
        },
        {
            "status": "revoked",
            "absolute_expires_at": created_at + timedelta(days=1),
            "revoked_at": None,
        },
    )
    for invalid in invalid_sessions:
        with pytest.raises(IntegrityError):
            async with authentication_engine.begin() as connection:
                await connection.execute(
                    insert(AuthenticationSession).values(
                        user_id=user_id,
                        created_at=created_at,
                        last_seen_at=created_at,
                        authentication_method="password",
                        credential_version=1,
                        authorization_version=1,
                        **invalid,
                    )
                )

    with pytest.raises(IntegrityError):
        async with authentication_engine.begin() as connection:
            await connection.execute(delete(User).where(User.id == user_id))

    assert session_id is not None


@pytest.mark.asyncio
async def test_refresh_token_rotation_constraints(
    authentication_engine: AsyncEngine,
) -> None:
    user_id = await create_user(authentication_engine, "refresh@example.com")
    session_id, issued_at = await create_session(authentication_engine, user_id)
    family_id = uuid4()
    token_id = uuid4()
    async with authentication_engine.begin() as connection:
        await connection.execute(
            insert(RefreshToken).values(
                id=token_id,
                session_id=session_id,
                token_hash="hash:refresh:one",
                family_id=family_id,
                sequence_number=0,
                issued_at=issued_at,
                expires_at=issued_at + timedelta(days=30),
            )
        )

    invalid_tokens: tuple[dict[str, object], ...] = (
        {
            "token_hash": "hash:refresh:one",
            "family_id": uuid4(),
            "sequence_number": 0,
            "expires_at": issued_at + timedelta(days=30),
        },
        {
            "token_hash": "hash:refresh:duplicate-sequence",
            "family_id": family_id,
            "sequence_number": 0,
            "expires_at": issued_at + timedelta(days=30),
        },
        {
            "token_hash": "hash:refresh:expired",
            "family_id": uuid4(),
            "sequence_number": 0,
            "expires_at": issued_at,
        },
        {
            "token_hash": "hash:refresh:unused-reuse",
            "family_id": uuid4(),
            "sequence_number": 0,
            "expires_at": issued_at + timedelta(days=30),
            "reuse_detected_at": issued_at + timedelta(seconds=1),
        },
    )
    for invalid in invalid_tokens:
        with pytest.raises(IntegrityError):
            async with authentication_engine.begin() as connection:
                await connection.execute(
                    insert(RefreshToken).values(
                        session_id=session_id,
                        issued_at=issued_at,
                        **invalid,
                    )
                )

    self_reference_id = uuid4()
    with pytest.raises(IntegrityError):
        async with authentication_engine.begin() as connection:
            await connection.execute(
                insert(RefreshToken).values(
                    id=self_reference_id,
                    session_id=session_id,
                    token_hash="hash:refresh:self",
                    family_id=uuid4(),
                    sequence_number=0,
                    issued_at=issued_at,
                    expires_at=issued_at + timedelta(days=30),
                    used_at=issued_at + timedelta(seconds=1),
                    replaced_by_token_id=self_reference_id,
                )
            )

    replacement_id = uuid4()
    async with authentication_engine.begin() as connection:
        await connection.execute(
            insert(RefreshToken).values(
                id=replacement_id,
                session_id=session_id,
                token_hash="hash:refresh:two",
                family_id=family_id,
                sequence_number=1,
                issued_at=issued_at + timedelta(seconds=1),
                expires_at=issued_at + timedelta(days=30),
                parent_token_id=token_id,
            )
        )
        await connection.execute(
            update(RefreshToken)
            .where(RefreshToken.id == token_id)
            .values(
                used_at=issued_at + timedelta(seconds=1),
                replaced_by_token_id=replacement_id,
            )
        )


@pytest.mark.asyncio
async def test_password_reset_token_constraints(
    authentication_engine: AsyncEngine,
) -> None:
    user_id = await create_user(authentication_engine, "reset@example.com")
    issued_at = utc_now()
    async with authentication_engine.begin() as connection:
        await connection.execute(
            insert(PasswordResetToken).values(
                user_id=user_id,
                token_hash="hash:reset:one",
                issued_at=issued_at,
                expires_at=issued_at + timedelta(hours=1),
            )
        )

    invalid_tokens: tuple[dict[str, object], ...] = (
        {
            "token_hash": "hash:reset:one",
            "expires_at": issued_at + timedelta(hours=1),
        },
        {
            "token_hash": "hash:reset:expired",
            "expires_at": issued_at,
        },
        {
            "token_hash": "hash:reset:two-states",
            "expires_at": issued_at + timedelta(hours=1),
            "consumed_at": issued_at + timedelta(minutes=1),
            "revoked_at": issued_at + timedelta(minutes=2),
        },
    )
    for invalid in invalid_tokens:
        with pytest.raises(IntegrityError):
            async with authentication_engine.begin() as connection:
                await connection.execute(
                    insert(PasswordResetToken).values(
                        user_id=user_id,
                        issued_at=issued_at,
                        **invalid,
                    )
                )


@pytest.mark.asyncio
async def test_email_verification_token_constraints_and_binding(
    authentication_engine: AsyncEngine,
) -> None:
    user_id = await create_user(authentication_engine, "verify@example.com")
    issued_at = utc_now()
    async with authentication_engine.begin() as connection:
        await connection.execute(
            insert(EmailVerificationToken).values(
                user_id=user_id,
                normalized_email="verify@example.com",
                token_hash="hash:verify:one",
                issued_at=issued_at,
                expires_at=issued_at + timedelta(hours=24),
            )
        )

    invalid_tokens: tuple[dict[str, object], ...] = (
        {
            "normalized_email": "verify@example.com",
            "token_hash": "hash:verify:one",
            "expires_at": issued_at + timedelta(hours=24),
        },
        {
            "normalized_email": "Verify@Example.com",
            "token_hash": "hash:verify:uppercase",
            "expires_at": issued_at + timedelta(hours=24),
        },
        {
            "normalized_email": " ",
            "token_hash": "hash:verify:blank",
            "expires_at": issued_at + timedelta(hours=24),
        },
        {
            "normalized_email": "verify@example.com",
            "token_hash": "hash:verify:expired",
            "expires_at": issued_at,
        },
        {
            "normalized_email": "verify@example.com",
            "token_hash": "hash:verify:two-states",
            "expires_at": issued_at + timedelta(hours=24),
            "consumed_at": issued_at + timedelta(minutes=1),
            "revoked_at": issued_at + timedelta(minutes=2),
        },
    )
    for invalid in invalid_tokens:
        with pytest.raises(IntegrityError):
            async with authentication_engine.begin() as connection:
                await connection.execute(
                    insert(EmailVerificationToken).values(
                        user_id=user_id,
                        issued_at=issued_at,
                        **invalid,
                    )
                )


@pytest.mark.asyncio
async def test_authentication_creates_no_membership_or_role_access(
    authentication_engine: AsyncEngine,
) -> None:
    user_id = await create_user(authentication_engine, "identity-only@example.com")
    await create_session(authentication_engine, user_id)

    async with authentication_engine.connect() as connection:
        membership_count = await connection.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.user_id == user_id)
        )
        role_count = await connection.scalar(
            select(func.count())
            .select_from(MembershipRole)
            .join(Membership, Membership.id == MembershipRole.membership_id)
            .where(Membership.user_id == user_id)
        )
    assert membership_count == 0
    assert role_count == 0


def test_token_models_have_no_plaintext_secret_columns() -> None:
    for model in (RefreshToken, PasswordResetToken, EmailVerificationToken):
        column_names = set(model.__table__.c.keys())
        assert "token" not in column_names
        assert "plaintext_token" not in column_names
        assert "secret" not in column_names
        assert "token_hash" in column_names


def test_authentication_orm_configuration_has_no_warnings() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        configure_mappers()
