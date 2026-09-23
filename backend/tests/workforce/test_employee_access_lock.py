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
from app.platform.audit.models import AuditRecord
from app.platform.auth.models import AuthenticationSession, RefreshToken
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User, UserCredential
from app.workforce.access_lock import EmployeeAccessLockService


@pytest_asyncio.fixture
async def access_lock_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_lock_unlock_revokes_sessions_rotates_versions_and_preserves_history(
    access_lock_database: async_sessionmaker[AsyncSession],
) -> None:
    factory = access_lock_database
    suffix = uuid4().hex[:10]
    now = datetime.now(timezone.utc)
    company = Company(name=f"Access Lock {suffix}", code=f"AL{suffix.upper()}", status="active", timezone="America/New_York")
    actor = User(normalized_email=f"actor-{suffix}@example.test", first_name="Access", last_name="Admin", display_name="Access Admin", status="active")
    target = User(normalized_email=f"target-{suffix}@example.test", first_name="Field", last_name="Employee", display_name="Field Employee", status="active")
    async with factory() as session, session.begin():
        session.add_all([company, actor, target])
        await session.flush()
        branch = Branch(company_id=company.id, name="MAIN", code="MAIN", status="active", timezone="America/New_York", is_primary=True)
        actor_membership = Membership(user_id=actor.id, company_id=company.id, status="active", has_all_branch_access=True, invited_at=now, accepted_at=now)
        target_membership = Membership(user_id=target.id, company_id=company.id, status="active", has_all_branch_access=True, invited_at=now, accepted_at=now)
        session.add_all([branch, actor_membership, target_membership])
        await session.flush()
        target_membership.default_branch_id = branch.id
        employee = Employee(company_id=company.id, membership_id=target_membership.id, home_branch_id=branch.id, employee_number=f"E-{suffix}", first_name="Field", last_name="Employee", display_name="Field Employee", employee_type="employee", status="active", created_by_user_id=actor.id)
        credential = UserCredential(user_id=target.id, password_hash="$argon2id$test", credential_version=1)
        authentication_session = AuthenticationSession(user_id=target.id, status="active", created_at=now, last_seen_at=now, absolute_expires_at=now + timedelta(hours=8), idle_expires_at=now + timedelta(hours=1), authentication_method="password", credential_version=1, authorization_version=1)
        session.add_all([employee, credential, authentication_session])
        await session.flush()
        refresh = RefreshToken(session_id=authentication_session.id, token_hash=f"hash-{suffix}", sequence_number=0, issued_at=now, expires_at=now + timedelta(hours=8))
        session.add(refresh)

    context = AuthorizationContext(user=actor, company=company, membership=actor_membership, authorized_branches=(branch,), active_branch=branch, effective_roles=(), effective_permissions=(), credential_version=1, authorization_version=1)
    service = EmployeeAccessLockService()
    async with factory() as session:
        await service.set_locked(session, context=context, employee_id=employee.id, locked=True, reason="Lost mobile device", expected_authorization_version=1)

    async with factory() as session:
        locked_user = await session.get(User, target.id)
        locked_credential = await session.scalar(select(UserCredential).where(UserCredential.user_id == target.id))
        revoked_session = await session.get(AuthenticationSession, authentication_session.id)
        revoked_refresh = await session.get(RefreshToken, refresh.id)
        assert locked_user is not None and locked_user.status == "locked"
        assert locked_user.authorization_version == 2 and locked_user.disabled_at is not None
        assert locked_credential is not None and locked_credential.credential_version == 2
        assert revoked_session is not None and revoked_session.status == "revoked"
        assert revoked_session.revoked_by_user_id == actor.id
        assert revoked_refresh is not None and revoked_refresh.revoked_at is not None
        assert employee.status == "active"
        assert await session.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.resource_id == employee.id)) == 1
        assert await session.scalar(select(func.count()).select_from(BusinessEvent).where(BusinessEvent.entity_id == employee.id)) == 1

    async with factory() as session:
        await service.set_locked(session, context=context, employee_id=employee.id, locked=True, reason="Exact replay", expected_authorization_version=1)
    async with factory() as session:
        replayed = await session.get(User, target.id)
        assert replayed is not None and replayed.authorization_version == 2
    async with factory() as session:
        await service.set_locked(session, context=context, employee_id=employee.id, locked=False, reason="Device recovered", expected_authorization_version=2)
    async with factory() as session:
        unlocked = await session.get(User, target.id)
        old_session = await session.get(AuthenticationSession, authentication_session.id)
        assert unlocked is not None and unlocked.status == "active"
        assert unlocked.authorization_version == 3 and unlocked.disabled_at is None
        assert old_session is not None and old_session.status == "revoked"
        assert await session.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.resource_id == employee.id)) == 2
