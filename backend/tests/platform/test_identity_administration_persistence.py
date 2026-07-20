import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.platform.auth import models as auth_models  # noqa: F401
from app.platform.audit import models as audit_models  # noqa: F401
from app.platform.branch import models as branch_models  # noqa: F401
from app.platform.company import membership_models  # noqa: F401
from app.platform.company.models import Company  # noqa: F401
from app.platform.employees import models as employee_models  # noqa: F401
from app.platform.permissions import models as permission_models  # noqa: F401
from app.platform.users.identity_models import PendingEmailChange
from app.platform.users.identity_repository import (
    IdentityRepositoryConflictError,
    IdentityRepositoryNotFoundError,
    UserIdentityRepository,
)
from app.platform.users.models import User, UserCredential


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def identity_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


async def create_user(factory: async_sessionmaker[AsyncSession], *, email: str) -> User:
    user = User(
        normalized_email=email,
        first_name="Identity",
        last_name="Tester",
        display_name="Identity Tester",
        status="active",
    )
    async with factory() as session, session.begin():
        session.add(user)
    return user


async def create_credential(
    factory: async_sessionmaker[AsyncSession], *, user: User
) -> UserCredential:
    credential = UserCredential(
        user_id=user.id,
        password_hash="$argon2id$test-only-hash",
    )
    async with factory() as session, session.begin():
        session.add(credential)
    return credential


async def reserve_email(
    factory: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    email: str,
    token_hash: str,
    now: datetime | None = None,
) -> PendingEmailChange:
    created_at = now or utc_now()
    async with factory() as session, session.begin():
        return await UserIdentityRepository.create_pending_email_change(
            session,
            user_id=user_id,
            proposed_normalized_email=email,
            proposed_display_email=email,
            verification_token_hash=token_hash,
            reason_code="self_service",
            initiated_by_user_id=user_id,
            expires_at=created_at + timedelta(hours=1),
            now=created_at,
        )


@pytest.mark.asyncio
async def test_pending_email_change_model_and_restrictive_foreign_key(
    identity_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_database
    user = await create_user(factory, email=f"model-{uuid4().hex}@example.com")
    now = utc_now()
    record = await reserve_email(
        factory,
        user_id=user.id,
        email=f"reserved-{uuid4().hex}@example.com",
        token_hash=f"hash-{uuid4().hex}",
        now=now,
    )

    assert record.status == "pending"
    assert record.expires_at > record.created_at
    assert "verification_token_hash" in PendingEmailChange.__table__.columns
    assert "verification_token" not in PendingEmailChange.__table__.columns

    with pytest.raises(IntegrityError):
        async with factory() as session, session.begin():
            await session.execute(delete(User).where(User.id == user.id))


@pytest.mark.asyncio
async def test_repository_lookup_availability_and_normalization(
    identity_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_database
    email = f"lookup-{uuid4().hex}@example.com"
    user = await create_user(factory, email=email)
    async with factory() as session:
        found_user = await UserIdentityRepository.get_user_by_normalized_email(
            session, email
        )
        assert found_user is not None
        assert found_user.id == user.id
        assert not await UserIdentityRepository.is_normalized_email_available(
            session, email, now=utc_now()
        )
        assert await UserIdentityRepository.is_normalized_email_available(
            session,
            f"available-{uuid4().hex}@example.com",
            now=utc_now(),
        )
        with pytest.raises(ValueError):
            await UserIdentityRepository.get_user_by_normalized_email(
                session, "Not-Normalized@Example.com"
            )


@pytest.mark.asyncio
async def test_second_request_supersedes_prior_request_and_expired_email_is_reusable(
    identity_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_database
    user = await create_user(factory, email=f"supersede-{uuid4().hex}@example.com")
    first = await reserve_email(
        factory,
        user_id=user.id,
        email=f"first-{uuid4().hex}@example.com",
        token_hash=f"hash-{uuid4().hex}",
    )
    second = await reserve_email(
        factory,
        user_id=user.id,
        email=f"second-{uuid4().hex}@example.com",
        token_hash=f"hash-{uuid4().hex}",
    )
    async with factory() as session:
        first_status = await session.scalar(
            select(PendingEmailChange.status).where(PendingEmailChange.id == first.id)
        )
        second_status = await session.scalar(
            select(PendingEmailChange.status).where(PendingEmailChange.id == second.id)
        )
    assert first_status == "superseded"
    assert second_status == "pending"

    expired_user = await create_user(
        factory, email=f"expired-user-{uuid4().hex}@example.com"
    )
    reusable_email = f"reusable-{uuid4().hex}@example.com"
    past = utc_now() - timedelta(hours=2)
    expired = await reserve_email(
        factory,
        user_id=expired_user.id,
        email=reusable_email,
        token_hash=f"hash-{uuid4().hex}",
        now=past,
    )
    replacement_user = await create_user(
        factory, email=f"replacement-{uuid4().hex}@example.com"
    )
    replacement = await reserve_email(
        factory,
        user_id=replacement_user.id,
        email=reusable_email,
        token_hash=f"hash-{uuid4().hex}",
    )
    async with factory() as session:
        expired_status = await session.scalar(
            select(PendingEmailChange.status).where(PendingEmailChange.id == expired.id)
        )
    assert expired_status == "expired"
    assert replacement.status == "pending"

    revoked_at = utc_now()
    async with factory() as session, session.begin():
        revoked_count = (
            await UserIdentityRepository.revoke_active_pending_email_changes(
                session,
                user_id=replacement_user.id,
                now=revoked_at,
            )
        )
    async with factory() as session:
        revoked = await session.get(PendingEmailChange, replacement.id)
    assert revoked_count == 1
    assert revoked is not None
    assert revoked.status == "revoked"
    assert revoked.revoked_at == revoked_at


@pytest.mark.asyncio
async def test_confirmation_is_single_transition_and_applies_verified_email(
    identity_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_database
    user = await create_user(factory, email=f"confirm-{uuid4().hex}@example.com")
    proposed = f"confirmed-{uuid4().hex}@example.com"
    token_hash = f"hash-{uuid4().hex}"
    await reserve_email(
        factory,
        user_id=user.id,
        email=proposed,
        token_hash=token_hash,
    )
    confirmed_at = utc_now()
    async with factory() as session, session.begin():
        record = await UserIdentityRepository.get_pending_email_change_for_update(
            session, token_hash
        )
        assert record is not None
        UserIdentityRepository.mark_pending_email_change_confirmed(
            record, now=confirmed_at
        )
        await UserIdentityRepository.apply_verified_email_change(
            session,
            user_id=user.id,
            normalized_email=proposed,
            verified_at=confirmed_at,
        )

    async with factory() as session:
        record = await UserIdentityRepository.get_pending_email_change_for_update(
            session, token_hash
        )
        assert record is not None
        with pytest.raises(IdentityRepositoryConflictError):
            UserIdentityRepository.mark_pending_email_change_confirmed(
                record, now=utc_now()
            )
        changed_user = await session.get(User, user.id)
    assert changed_user is not None
    assert changed_user.normalized_email == proposed
    assert changed_user.email_verified_at is not None


@pytest.mark.asyncio
async def test_forced_password_reset_state_is_explicit_idempotent_and_clearable(
    identity_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_database
    user = await create_user(factory, email=f"forced-{uuid4().hex}@example.com")
    await create_credential(factory, user=user)
    required_at = utc_now()
    async with factory() as session, session.begin():
        (
            credential,
            changed,
        ) = await UserIdentityRepository.set_forced_password_reset_required(
            session,
            user_id=user.id,
            required_at=required_at,
            reason_code="security_incident",
            required_by_user_id=user.id,
            company_id=None,
        )
        (
            _,
            repeated_changed,
        ) = await UserIdentityRepository.set_forced_password_reset_required(
            session,
            user_id=user.id,
            required_at=required_at,
            reason_code="security_incident",
            required_by_user_id=user.id,
            company_id=None,
        )
    assert changed
    assert not repeated_changed
    assert credential.password_change_required

    cleared_at = required_at + timedelta(minutes=1)
    async with factory() as session, session.begin():
        (
            credential,
            cleared,
        ) = await UserIdentityRepository.clear_forced_password_reset_required(
            session, user_id=user.id, cleared_at=cleared_at
        )
        (
            _,
            repeated_clear,
        ) = await UserIdentityRepository.clear_forced_password_reset_required(
            session, user_id=user.id, cleared_at=cleared_at
        )
    assert cleared
    assert not repeated_clear
    assert not credential.password_change_required
    assert credential.password_change_required_cleared_at == cleared_at


@pytest.mark.asyncio
async def test_missing_identity_resources_are_controlled(
    identity_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_database
    async with factory() as session, session.begin():
        with pytest.raises(IdentityRepositoryNotFoundError):
            await UserIdentityRepository.create_pending_email_change(
                session,
                user_id=uuid4(),
                proposed_normalized_email=f"missing-{uuid4().hex}@example.com",
                proposed_display_email=None,
                verification_token_hash=f"hash-{uuid4().hex}",
                reason_code="self_service",
                expires_at=utc_now() + timedelta(hours=1),
                now=utc_now(),
            )


@pytest.mark.asyncio
async def test_concurrent_users_cannot_reserve_same_email(
    identity_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_database
    first_user = await create_user(factory, email=f"race-a-{uuid4().hex}@example.com")
    second_user = await create_user(factory, email=f"race-b-{uuid4().hex}@example.com")
    proposed = f"race-target-{uuid4().hex}@example.com"

    async def attempt(user_id: UUID) -> bool:
        try:
            await reserve_email(
                factory,
                user_id=user_id,
                email=proposed,
                token_hash=f"hash-{uuid4().hex}",
            )
        except (IdentityRepositoryConflictError, IntegrityError):
            return False
        return True

    outcomes = await asyncio.gather(attempt(first_user.id), attempt(second_user.id))
    assert sorted(outcomes) == [False, True]


@pytest.mark.asyncio
async def test_concurrent_confirmations_allow_one_transition(
    identity_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_database
    user = await create_user(factory, email=f"confirm-race-{uuid4().hex}@example.com")
    token_hash = f"hash-{uuid4().hex}"
    await reserve_email(
        factory,
        user_id=user.id,
        email=f"confirm-target-{uuid4().hex}@example.com",
        token_hash=token_hash,
    )

    async def confirm() -> bool:
        try:
            async with factory() as session, session.begin():
                record = (
                    await UserIdentityRepository.get_pending_email_change_for_update(
                        session, token_hash
                    )
                )
                assert record is not None
                UserIdentityRepository.mark_pending_email_change_confirmed(
                    record, now=utc_now()
                )
        except IdentityRepositoryConflictError:
            return False
        return True

    outcomes = await asyncio.gather(confirm(), confirm())
    assert sorted(outcomes) == [False, True]


@pytest.mark.asyncio
async def test_concurrent_requests_for_one_user_leave_one_pending_record(
    identity_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_database
    user = await create_user(factory, email=f"user-race-{uuid4().hex}@example.com")
    await asyncio.gather(
        reserve_email(
            factory,
            user_id=user.id,
            email=f"choice-a-{uuid4().hex}@example.com",
            token_hash=f"hash-{uuid4().hex}",
        ),
        reserve_email(
            factory,
            user_id=user.id,
            email=f"choice-b-{uuid4().hex}@example.com",
            token_hash=f"hash-{uuid4().hex}",
        ),
    )
    async with factory() as session:
        pending_count = await session.scalar(
            select(func.count())
            .select_from(PendingEmailChange)
            .where(
                PendingEmailChange.user_id == user.id,
                PendingEmailChange.status == "pending",
            )
        )
    assert pending_count == 1


@pytest.mark.asyncio
async def test_confirmation_wins_against_competing_reservation(
    identity_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_database
    owner = await create_user(factory, email=f"owner-{uuid4().hex}@example.com")
    competitor = await create_user(
        factory, email=f"competitor-{uuid4().hex}@example.com"
    )
    proposed = f"claim-{uuid4().hex}@example.com"
    token_hash = f"hash-{uuid4().hex}"
    await reserve_email(
        factory,
        user_id=owner.id,
        email=proposed,
        token_hash=token_hash,
    )

    async def confirm() -> bool:
        async with factory() as session, session.begin():
            record = await UserIdentityRepository.get_pending_email_change_for_update(
                session, token_hash
            )
            assert record is not None
            now = utc_now()
            UserIdentityRepository.mark_pending_email_change_confirmed(record, now=now)
            await UserIdentityRepository.apply_verified_email_change(
                session,
                user_id=owner.id,
                normalized_email=proposed,
                verified_at=now,
            )
        return True

    async def compete() -> bool:
        try:
            await reserve_email(
                factory,
                user_id=competitor.id,
                email=proposed,
                token_hash=f"hash-{uuid4().hex}",
            )
        except (IdentityRepositoryConflictError, IntegrityError):
            return False
        return True

    outcomes = await asyncio.gather(confirm(), compete())
    assert outcomes == [True, False]


@pytest.mark.asyncio
async def test_concurrent_forced_reset_updates_remain_coherent(
    identity_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_database
    user = await create_user(factory, email=f"forced-race-{uuid4().hex}@example.com")
    await create_credential(factory, user=user)

    async def require(reason: str) -> None:
        async with factory() as session, session.begin():
            await UserIdentityRepository.set_forced_password_reset_required(
                session,
                user_id=user.id,
                required_at=utc_now(),
                reason_code=reason,
                required_by_user_id=user.id,
                company_id=None,
            )

    await asyncio.gather(require("security_incident"), require("policy_compliance"))
    async with factory() as session:
        credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == user.id)
        )
    assert credential is not None
    assert credential.password_change_required
    assert credential.password_change_required_reason_code in {
        "security_incident",
        "policy_compliance",
    }
    assert credential.password_change_required_at is not None
    assert credential.password_change_required_cleared_at is None
