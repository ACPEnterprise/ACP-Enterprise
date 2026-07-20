import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.database.session import get_database_session
from app.events.models import BusinessEvent
from app.platform.auth.access_tokens import AccessTokenClaims
from app.platform.auth.models import AuthenticationSession
from app.platform.auth.services import AuthenticatedContext, utc_now
from app.platform.branch.models import Branch
from app.platform.company.admin_router import router as admin_router
from app.platform.company.admin_service import (
    AccessPolicyConflictError,
    AccessPolicyNotFoundError,
    CompanyAdministrationService,
    FinalAdministratorError,
)
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationService,
    TenantAccessDeniedError,
)
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.dependencies import get_authorization_context
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User, UserCredential


@dataclass(frozen=True)
class AdminFixture:
    context: AuthorizationContext
    target_user_id: UUID
    target_membership_id: UUID
    company_branch_id: UUID
    inactive_branch_id: UUID
    other_company_id: UUID
    other_branch_id: UUID
    admin_role_id: UUID
    company_role_id: UUID
    other_role_id: UUID
    platform_permission_id: UUID


@pytest_asyncio.fixture
async def admin_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


async def get_or_create_permission(
    session: AsyncSession, code: str, *, action: str = "manage"
) -> Permission:
    existing = await session.scalar(select(Permission).where(Permission.code == code))
    if existing is not None:
        return existing
    permission = Permission(
        code=code,
        name=code.replace("_", " ").title(),
        resource="company",
        action=action,
        status="active",
    )
    session.add(permission)
    await session.flush()
    return permission


async def seed_admin_fixture(
    factory: async_sessionmaker[AsyncSession], prefix: str
) -> AdminFixture:
    now = utc_now()
    run_id = uuid4().hex[:8]
    namespace = f"{prefix}{run_id.upper()}"
    async with factory() as session, session.begin():
        admin_user = User(
            normalized_email=f"{prefix.lower()}-{run_id}-admin@example.com",
            first_name="Company",
            last_name="Administrator",
            display_name="Company Administrator",
            status="active",
        )
        target_user = User(
            normalized_email=f"{prefix.lower()}-{run_id}-target@example.com",
            first_name="Target",
            last_name="User",
            display_name="Target User",
            status="active",
        )
        session.add_all([admin_user, target_user])
        await session.flush()
        session.add_all(
            [
                UserCredential(
                    user_id=admin_user.id,
                    password_hash="$argon2id$admin-test-hash",
                    password_changed_at=now,
                ),
                UserCredential(
                    user_id=target_user.id,
                    password_hash="$argon2id$target-test-hash",
                    password_changed_at=now,
                ),
            ]
        )
        company = Company(
            name=f"{prefix} Company",
            code=f"{namespace}CO",
            status="active",
            timezone="America/New_York",
        )
        other_company = Company(
            name=f"{prefix} Other Company",
            code=f"{namespace}OT",
            status="active",
            timezone="America/New_York",
        )
        session.add_all([company, other_company])
        await session.flush()
        branch = Branch(
            company_id=company.id,
            name="Main Branch",
            code=f"{namespace}MAIN",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        inactive_branch = Branch(
            company_id=company.id,
            name="Inactive Branch",
            code=f"{namespace}INACTIVE",
            status="inactive",
            timezone="America/New_York",
            is_primary=False,
        )
        other_branch = Branch(
            company_id=other_company.id,
            name="Other Branch",
            code=f"{namespace}OTHER",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        session.add_all([branch, inactive_branch, other_branch])
        await session.flush()
        admin_membership = Membership(
            user_id=admin_user.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=True,
            accepted_at=now,
        )
        target_membership = Membership(
            user_id=target_user.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=False,
            accepted_at=now,
        )
        session.add_all([admin_membership, target_membership])
        await session.flush()

        permission_codes = AdministrationPermission.ALL
        admin_permissions = [
            await get_or_create_permission(session, code) for code in permission_codes
        ]
        platform_permission = await get_or_create_permission(
            session, f"{namespace}_CUSTOMER_VIEW", action="view"
        )
        admin_role = Role(
            company_id=company.id,
            code=f"{namespace}_ADMIN",
            name="Company Administrator",
            status="active",
            is_system=True,
        )
        company_role = Role(
            company_id=company.id,
            code=f"{namespace}_DISPATCH",
            name="Dispatcher",
            status="active",
            is_system=False,
        )
        other_role = Role(
            company_id=other_company.id,
            code=f"{namespace}_OTHER_ROLE",
            name="Other Role",
            status="active",
            is_system=False,
        )
        session.add_all([admin_role, company_role, other_role])
        await session.flush()
        session.add(
            MembershipRole(
                company_id=company.id,
                membership_id=admin_membership.id,
                role_id=admin_role.id,
                assigned_at=now,
            )
        )
        session.add_all(
            [
                RolePermission(
                    role_id=admin_role.id,
                    permission_id=permission.id,
                    assigned_at=now,
                )
                for permission in admin_permissions
            ]
        )
        authentication_session = AuthenticationSession(
            user_id=admin_user.id,
            status="active",
            created_at=now,
            last_seen_at=now,
            absolute_expires_at=now + timedelta(days=30),
            idle_expires_at=now + timedelta(days=7),
            authentication_method="password",
            credential_version=1,
            authorization_version=1,
        )
        session.add(authentication_session)
        await session.flush()

    claims = AccessTokenClaims(
        user_id=admin_user.id,
        session_id=authentication_session.id,
        credential_version=1,
        authorization_version=1,
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
        token_id=uuid4(),
    )
    authenticated = AuthenticatedContext(admin_user, authentication_session, claims)
    async with factory() as session:
        context = await AuthorizationService().resolve(
            session,
            authenticated=authenticated,
            company_id=company.id,
        )
    return AdminFixture(
        context=context,
        target_user_id=target_user.id,
        target_membership_id=target_membership.id,
        company_branch_id=branch.id,
        inactive_branch_id=inactive_branch.id,
        other_company_id=other_company.id,
        other_branch_id=other_branch.id,
        admin_role_id=admin_role.id,
        company_role_id=company_role.id,
        other_role_id=other_role.id,
        platform_permission_id=platform_permission.id,
    )


async def user_version(factory: async_sessionmaker[AsyncSession], user_id: UUID) -> int:
    async with factory() as session:
        value = await session.scalar(
            select(User.authorization_version).where(User.id == user_id)
        )
        assert value is not None
        return value


@pytest.mark.asyncio
async def test_membership_branch_policy_and_cross_tenant_guards(
    admin_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = admin_database
    fixture = await seed_admin_fixture(factory, "ADMINA")
    service = CompanyAdministrationService()
    before = await user_version(factory, fixture.target_user_id)

    async with factory() as session:
        access = await service.add_branch_access(
            session,
            context=fixture.context,
            membership_id=fixture.target_membership_id,
            branch_id=fixture.company_branch_id,
        )
    assert access.branch_id == fixture.company_branch_id
    assert await user_version(factory, fixture.target_user_id) == before + 1

    async with factory() as session:
        same_access = await service.add_branch_access(
            session,
            context=fixture.context,
            membership_id=fixture.target_membership_id,
            branch_id=fixture.company_branch_id,
        )
    assert same_access.id == access.id
    assert await user_version(factory, fixture.target_user_id) == before + 1

    for rejected_branch in (fixture.other_branch_id, fixture.inactive_branch_id):
        async with factory() as session:
            with pytest.raises(AccessPolicyNotFoundError):
                await service.add_branch_access(
                    session,
                    context=fixture.context,
                    membership_id=fixture.target_membership_id,
                    branch_id=rejected_branch,
                )

    async with factory() as session:
        membership = await service.set_all_branch_access(
            session,
            context=fixture.context,
            membership_id=fixture.target_membership_id,
            enabled=True,
        )
    assert membership.has_all_branch_access
    async with factory() as session:
        removed = await service.remove_branch_access(
            session,
            context=fixture.context,
            membership_id=fixture.target_membership_id,
            branch_id=fixture.company_branch_id,
        )
    assert removed
    async with factory() as session:
        assert not await service.remove_branch_access(
            session,
            context=fixture.context,
            membership_id=fixture.target_membership_id,
            branch_id=fixture.company_branch_id,
        )

    async with factory() as session:
        suspended = await service.set_membership_status(
            session,
            context=fixture.context,
            membership_id=fixture.target_membership_id,
            status="suspended",
        )
    assert suspended.status == "suspended"
    async with factory() as session:
        revoked = await service.set_membership_status(
            session,
            context=fixture.context,
            membership_id=fixture.target_membership_id,
            status="revoked",
        )
    assert revoked.status == "revoked"

    async with factory() as session:
        events = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(BusinessEvent.company_id == fixture.context.company.id)
        )
    assert events is not None and events >= 4


@pytest.mark.asyncio
async def test_membership_creation_and_cross_company_mutation_denial(
    admin_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = admin_database
    fixture = await seed_admin_fixture(factory, "ADMINF")
    service = CompanyAdministrationService()
    new_user = User(
        normalized_email=f"adminf-{uuid4().hex[:8]}-new@example.com",
        first_name="New",
        last_name="Member",
        display_name="New Member",
        status="active",
    )
    async with factory() as session, session.begin():
        session.add(new_user)
        await session.flush()
        session.add(
            UserCredential(
                user_id=new_user.id,
                password_hash="$argon2id$new-test-hash",
                password_changed_at=utc_now(),
            )
        )
        cross_company_membership = Membership(
            user_id=fixture.target_user_id,
            company_id=fixture.other_company_id,
            status="active",
            has_all_branch_access=False,
        )
        session.add(cross_company_membership)
        await session.flush()

    async with factory() as session:
        created = await service.create_membership(
            session,
            context=fixture.context,
            user_id=new_user.id,
            status="active",
        )
    assert created.company_id == fixture.context.company.id
    assert await user_version(factory, new_user.id) == 2

    async with factory() as session:
        with pytest.raises(AccessPolicyNotFoundError):
            await service.set_membership_status(
                session,
                context=fixture.context,
                membership_id=cross_company_membership.id,
                status="suspended",
            )
    async with factory() as session:
        with pytest.raises(AccessPolicyNotFoundError):
            await service.create_membership(
                session,
                context=fixture.context,
                user_id=uuid4(),
                status="active",
                default_branch_id=fixture.other_branch_id,
            )


@pytest.mark.asyncio
async def test_role_permission_mutations_invalidate_all_affected_users(
    admin_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = admin_database
    fixture = await seed_admin_fixture(factory, "ADMINB")
    service = CompanyAdministrationService()

    async with factory() as session:
        assignment = await service.assign_role(
            session,
            context=fixture.context,
            membership_id=fixture.target_membership_id,
            role_id=fixture.company_role_id,
        )
    first_version = await user_version(factory, fixture.target_user_id)
    async with factory() as session:
        same_assignment = await service.assign_role(
            session,
            context=fixture.context,
            membership_id=fixture.target_membership_id,
            role_id=fixture.company_role_id,
        )
    assert same_assignment.id == assignment.id
    assert await user_version(factory, fixture.target_user_id) == first_version

    async with factory() as session:
        with pytest.raises(AccessPolicyNotFoundError):
            await service.assign_role(
                session,
                context=fixture.context,
                membership_id=fixture.target_membership_id,
                role_id=fixture.other_role_id,
            )

    second_user = User(
        normalized_email=f"adminb-{uuid4().hex[:8]}-second@example.com",
        first_name="Second",
        last_name="User",
        display_name="Second User",
        status="active",
    )
    async with factory() as session, session.begin():
        session.add(second_user)
        await session.flush()
        session.add(
            UserCredential(
                user_id=second_user.id,
                password_hash="$argon2id$second-test-hash",
                password_changed_at=utc_now(),
            )
        )
        second_membership = Membership(
            user_id=second_user.id,
            company_id=fixture.context.company.id,
            status="active",
            has_all_branch_access=False,
        )
        session.add(second_membership)
        await session.flush()
        session.add(
            MembershipRole(
                company_id=fixture.context.company.id,
                membership_id=second_membership.id,
                role_id=fixture.company_role_id,
            )
        )
    target_before = await user_version(factory, fixture.target_user_id)
    second_before = await user_version(factory, second_user.id)
    async with factory() as session:
        permission_assignment = await service.assign_permission(
            session,
            context=fixture.context,
            role_id=fixture.company_role_id,
            permission_id=fixture.platform_permission_id,
        )
    assert permission_assignment.permission_id == fixture.platform_permission_id
    assert await user_version(factory, fixture.target_user_id) == target_before + 1
    assert await user_version(factory, second_user.id) == second_before + 1

    async with factory() as session:
        same_permission = await service.assign_permission(
            session,
            context=fixture.context,
            role_id=fixture.company_role_id,
            permission_id=fixture.platform_permission_id,
        )
    assert same_permission.id == permission_assignment.id
    assert await user_version(factory, fixture.target_user_id) == target_before + 1

    async with factory() as session:
        assert await service.remove_permission(
            session,
            context=fixture.context,
            role_id=fixture.company_role_id,
            permission_id=fixture.platform_permission_id,
        )
    async with factory() as session:
        assert not await service.remove_permission(
            session,
            context=fixture.context,
            role_id=fixture.company_role_id,
            permission_id=fixture.platform_permission_id,
        )
    async with factory() as session:
        assert await service.revoke_role(
            session,
            context=fixture.context,
            membership_id=fixture.target_membership_id,
            role_id=fixture.company_role_id,
        )


@pytest.mark.asyncio
async def test_inactive_role_and_permission_are_rejected(
    admin_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = admin_database
    fixture = await seed_admin_fixture(factory, "ADMING")
    service = CompanyAdministrationService()
    async with factory() as session, session.begin():
        role = await session.get(Role, fixture.company_role_id)
        permission = await session.get(Permission, fixture.platform_permission_id)
        assert role is not None and permission is not None
        role.status = "inactive"
        permission.status = "retired"
        permission.retired_at = utc_now()

    async with factory() as session:
        with pytest.raises(AccessPolicyConflictError):
            await service.assign_role(
                session,
                context=fixture.context,
                membership_id=fixture.target_membership_id,
                role_id=fixture.company_role_id,
            )
    async with factory() as session, session.begin():
        role = await session.get(Role, fixture.company_role_id)
        assert role is not None
        role.status = "active"
    async with factory() as session:
        with pytest.raises(AccessPolicyNotFoundError):
            await service.assign_permission(
                session,
                context=fixture.context,
                role_id=fixture.company_role_id,
                permission_id=fixture.platform_permission_id,
            )


@pytest.mark.asyncio
async def test_version_increment_invalidates_existing_authorization_context(
    admin_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = admin_database
    fixture = await seed_admin_fixture(factory, "ADMINC")
    service = CompanyAdministrationService()
    old_context = fixture.context
    async with factory() as session:
        await service.set_all_branch_access(
            session,
            context=fixture.context,
            membership_id=fixture.target_membership_id,
            enabled=True,
        )

    target_now = await user_version(factory, fixture.target_user_id)
    assert target_now == 2
    admin_before = fixture.context.user.authorization_version
    async with factory() as session:
        await service.set_all_branch_access(
            session,
            context=fixture.context,
            membership_id=fixture.context.membership.id,
            enabled=False,
        )
    assert await user_version(factory, fixture.context.user.id) == admin_before + 1
    async with factory() as session:
        with pytest.raises(TenantAccessDeniedError):
            await AuthorizationService().resolve(
                session,
                authenticated=AuthenticatedContext(
                    old_context.user,
                    AuthenticationSession(
                        id=old_context.membership.id,
                        user_id=old_context.user.id,
                        status="active",
                        created_at=utc_now(),
                        last_seen_at=utc_now(),
                        absolute_expires_at=utc_now() + timedelta(days=1),
                        authentication_method="password",
                        credential_version=old_context.credential_version,
                        authorization_version=old_context.authorization_version,
                    ),
                    AccessTokenClaims(
                        user_id=old_context.user.id,
                        session_id=old_context.membership.id,
                        credential_version=old_context.credential_version,
                        authorization_version=old_context.authorization_version,
                        issued_at=utc_now(),
                        expires_at=utc_now() + timedelta(minutes=5),
                        token_id=uuid4(),
                    ),
                ),
                company_id=fixture.context.company.id,
            )


@pytest.mark.asyncio
async def test_final_admin_guard_is_concurrency_safe(
    admin_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = admin_database
    fixture = await seed_admin_fixture(factory, "ADMIND")
    service = CompanyAdministrationService()
    async with factory() as session:
        admin_permission = await session.scalar(
            select(Permission).where(
                Permission.code == AdministrationPermission.COMPANY_ADMINISTER
            )
        )
        assert admin_permission is not None
    second_admin = User(
        normalized_email=f"admind-{uuid4().hex[:8]}-second-admin@example.com",
        first_name="Second",
        last_name="Administrator",
        display_name="Second Administrator",
        status="active",
    )
    async with factory() as session, session.begin():
        session.add(second_admin)
        await session.flush()
        session.add(
            UserCredential(
                user_id=second_admin.id,
                password_hash="$argon2id$second-admin-hash",
                password_changed_at=utc_now(),
            )
        )
        second_membership = Membership(
            user_id=second_admin.id,
            company_id=fixture.context.company.id,
            status="active",
            has_all_branch_access=True,
        )
        second_role = Role(
            company_id=fixture.context.company.id,
            code="ADMIND_SECOND_ADMIN",
            name="Second Administrator",
            status="active",
            is_system=True,
        )
        session.add_all([second_membership, second_role])
        await session.flush()
        session.add_all(
            [
                MembershipRole(
                    company_id=fixture.context.company.id,
                    membership_id=second_membership.id,
                    role_id=second_role.id,
                ),
                RolePermission(
                    role_id=second_role.id,
                    permission_id=admin_permission.id,
                ),
            ]
        )
        first_admin_role_id = fixture.admin_role_id

    async def revoke(membership_id: UUID, role_id: UUID) -> object:
        async with factory() as session:
            try:
                return await service.revoke_role(
                    session,
                    context=fixture.context,
                    membership_id=membership_id,
                    role_id=role_id,
                )
            except FinalAdministratorError as error:
                return error

    outcomes = await asyncio.gather(
        revoke(fixture.context.membership.id, first_admin_role_id),
        revoke(second_membership.id, second_role.id),
    )
    assert sum(outcome is True for outcome in outcomes) == 1
    assert (
        sum(isinstance(outcome, FinalAdministratorError) for outcome in outcomes) == 1
    )


@pytest.mark.asyncio
async def test_router_permission_dependency_denies_missing_admin_permission(
    admin_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = admin_database
    fixture = await seed_admin_fixture(factory, "ADMINE")
    restricted_context = AuthorizationContext(
        user=fixture.context.user,
        company=fixture.context.company,
        membership=fixture.context.membership,
        authorized_branches=fixture.context.authorized_branches,
        active_branch=None,
        effective_roles=(),
        effective_permissions=(),
        credential_version=fixture.context.credential_version,
        authorization_version=fixture.context.authorization_version,
    )
    app = FastAPI()
    app.include_router(admin_router)

    async def database_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    async def authorization_override() -> AuthorizationContext:
        return restricted_context

    app.dependency_overrides[get_database_session] = database_override
    app.dependency_overrides[get_authorization_context] = authorization_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/company-admin/roles",
            json={"code": "DENIED", "name": "Denied Role"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_authorized_router_enforces_context_and_rejects_unknown_fields(
    admin_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = admin_database
    fixture = await seed_admin_fixture(factory, "ADMINH")
    app = FastAPI()
    app.include_router(admin_router)

    async def database_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    async def authorization_override() -> AuthorizationContext:
        return fixture.context

    app.dependency_overrides[get_database_session] = database_override
    app.dependency_overrides[get_authorization_context] = authorization_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/company-admin/memberships")
        invalid = await client.post(
            "/api/v1/company-admin/roles",
            json={"code": "ROUTER", "name": "Router Role", "is_system": True},
        )
    assert response.status_code == 200
    assert {record["company_id"] for record in response.json()} == {
        str(fixture.context.company.id)
    }
    assert invalid.status_code == 422
