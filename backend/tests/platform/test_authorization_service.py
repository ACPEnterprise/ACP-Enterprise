from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError, dataclass
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from sqlalchemy import func, inspect, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.customers import models as customer_models  # noqa: F401
from app.database.session import get_database_session, get_security_database_session
from app.events.models import BusinessEvent
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.auth.access_tokens import AccessTokenClaims
from app.platform.auth.dependencies import get_authenticated_context
from app.platform.auth.models import AuthenticationSession
from app.platform.auth.services import (
    AuthenticatedContext,
    access_token_service,
    utc_now,
)
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.company.models import Company
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationService,
    TenantAccessDeniedError,
)
from app.platform.permissions.dependencies import require_permission
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.permissions.router import router as authorization_router
from app.platform.users.models import User, UserCredential


@dataclass(frozen=True)
class AuthorizationFixture:
    authenticated: AuthenticatedContext
    company_id: UUID
    authorized_branch_id: UUID
    unauthorized_branch_id: UUID
    other_company_id: UUID


class RequestMutationProbe:
    """Exercise the canonical service-owned transaction contract."""

    @staticmethod
    async def execute(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        fail_after_staging: bool = False,
    ) -> None:
        async with session.begin():
            BusinessEventService.stage(
                session,
                BusinessEventCreate(
                    event_type=EventType.CUSTOMER_CREATED,
                    entity_type="transaction_contract_probe",
                    entity_id=uuid4(),
                    company_id=context.company.id,
                    user_id=context.user.id,
                    payload={"contract_version": 1},
                ),
            )
            if fail_after_staging:
                raise RuntimeError("controlled transaction rollback")


@pytest_asyncio.fixture
async def authorization_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


async def seed_authorization_fixture(
    factory: async_sessionmaker[AsyncSession],
    *,
    prefix: str,
    user_status: str = "active",
    membership_status: str = "active",
    company_archived: bool = False,
) -> AuthorizationFixture:
    now = utc_now()
    user = User(
        id=uuid4(),
        normalized_email=f"{prefix.lower()}@example.com",
        first_name="Authorization",
        last_name="Tester",
        display_name="Authorization Tester",
        status=user_status,
        authorization_version=1,
    )
    credential = UserCredential(
        id=uuid4(),
        user_id=user.id,
        password_hash="$argon2id$test-only-encoded-hash",
        password_changed_at=now,
        credential_version=1,
    )
    company = Company(
        id=uuid4(),
        name=f"{prefix} Company",
        code=f"{prefix}A",
        status="active",
        timezone="America/New_York",
        archived_at=now if company_archived else None,
    )
    other_company = Company(
        id=uuid4(),
        name=f"{prefix} Other Company",
        code=f"{prefix}B",
        status="active",
        timezone="America/New_York",
    )
    authorized_branch = Branch(
        id=uuid4(),
        company_id=company.id,
        name="Authorized Branch",
        code=f"{prefix}BR1",
        status="active",
        timezone="America/New_York",
        is_primary=True,
    )
    unauthorized_branch = Branch(
        id=uuid4(),
        company_id=company.id,
        name="Unauthorized Branch",
        code=f"{prefix}BR2",
        status="active",
        timezone="America/New_York",
        is_primary=False,
    )
    membership = Membership(
        id=uuid4(),
        user_id=user.id,
        company_id=company.id,
        status=membership_status,
        has_all_branch_access=False,
    )
    branch_access = MembershipBranchAccess(
        membership_id=membership.id,
        branch_id=authorized_branch.id,
        assigned_at=now,
    )
    permission = Permission(
        id=uuid4(),
        code=f"{prefix}_CUSTOMER_VIEW",
        name="Customer View",
        resource="customer",
        action="view",
        status="active",
    )
    role = Role(
        id=uuid4(),
        company_id=company.id,
        code=f"{prefix}_CSR",
        name="CSR",
        status="active",
        is_system=False,
    )
    role_permission = RolePermission(
        role_id=role.id,
        permission_id=permission.id,
        assigned_at=now,
    )
    membership_role = MembershipRole(
        company_id=company.id,
        membership_id=membership.id,
        role_id=role.id,
        assigned_at=now,
    )
    authentication_session = AuthenticationSession(
        id=uuid4(),
        user_id=user.id,
        status="active",
        created_at=now,
        last_seen_at=now,
        absolute_expires_at=now + timedelta(days=30),
        idle_expires_at=now + timedelta(days=7),
        authentication_method="password",
        credential_version=1,
        authorization_version=1,
    )
    async with factory() as session, session.begin():
        session.add_all(
            [
                user,
                credential,
                company,
                other_company,
                authorized_branch,
                unauthorized_branch,
                membership,
                branch_access,
                permission,
                role,
                role_permission,
                membership_role,
                authentication_session,
            ]
        )
    claims = AccessTokenClaims(
        user_id=user.id,
        session_id=authentication_session.id,
        credential_version=1,
        authorization_version=1,
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
        token_id=uuid4(),
    )
    return AuthorizationFixture(
        authenticated=AuthenticatedContext(user, authentication_session, claims),
        company_id=company.id,
        authorized_branch_id=authorized_branch.id,
        unauthorized_branch_id=unauthorized_branch.id,
        other_company_id=other_company.id,
    )


@pytest.mark.asyncio
async def test_permission_resolution_and_company_branch_isolation(
    authorization_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = authorization_database
    fixture = await seed_authorization_fixture(factory, prefix="AUTHZA")
    service = AuthorizationService()

    async with factory() as session:
        context = await service.resolve(
            session,
            authenticated=fixture.authenticated,
            company_id=fixture.company_id,
            branch_id=fixture.authorized_branch_id,
        )
    assert context.company.id == fixture.company_id
    assert context.membership.user_id == fixture.authenticated.user.id
    assert context.active_branch is not None
    assert context.active_branch.id == fixture.authorized_branch_id
    assert context.authorized_branch_ids == {fixture.authorized_branch_id}
    assert context.role_codes == {"AUTHZA_CSR"}
    assert context.permission_codes == {"AUTHZA_CUSTOMER_VIEW"}
    assert context.credential_version == 1
    assert context.authorization_version == 1
    assert all(
        inspect(value, raiseerr=False) is None
        for value in (
            context.user,
            context.company,
            context.membership,
            *context.authorized_branches,
            *context.effective_roles,
            *context.effective_permissions,
        )
    )
    with pytest.raises(FrozenInstanceError):
        setattr(context.user, "display_name", "Changed")

    async with factory() as session:
        with pytest.raises(TenantAccessDeniedError):
            await service.resolve(
                session,
                authenticated=fixture.authenticated,
                company_id=fixture.other_company_id,
            )
    async with factory() as session:
        with pytest.raises(TenantAccessDeniedError):
            await service.resolve(
                session,
                authenticated=fixture.authenticated,
                company_id=fixture.company_id,
                branch_id=fixture.unauthorized_branch_id,
            )


@pytest.mark.asyncio
async def test_accessible_companies_include_only_active_tenant_memberships(
    authorization_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = authorization_database
    fixture = await seed_authorization_fixture(factory, prefix="AUTHZACCESS")

    async with factory() as session:
        accessible = await AuthorizationService().list_accessible_companies(
            session,
            authenticated=fixture.authenticated,
        )

    assert len(accessible) == 1
    assert accessible[0].company.id == fixture.company_id
    assert accessible[0].membership.user_id == fixture.authenticated.user.id
    assert tuple(branch.id for branch in accessible[0].authorized_branches) == (
        fixture.authorized_branch_id,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prefix", "user_status", "membership_status", "company_archived"),
    [
        ("AUTHZDISABLED", "disabled", "active", False),
        ("AUTHZNOMEM", "active", "suspended", False),
        ("AUTHZARCHIVED", "active", "active", True),
    ],
)
async def test_inactive_identity_and_tenant_states_are_rejected(
    authorization_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    prefix: str,
    user_status: str,
    membership_status: str,
    company_archived: bool,
) -> None:
    _, factory = authorization_database
    fixture = await seed_authorization_fixture(
        factory,
        prefix=prefix,
        user_status=user_status,
        membership_status=membership_status,
        company_archived=company_archived,
    )
    async with factory() as session:
        with pytest.raises(TenantAccessDeniedError):
            await AuthorizationService().resolve(
                session,
                authenticated=fixture.authenticated,
                company_id=fixture.company_id,
            )


@pytest.mark.asyncio
async def test_authorization_version_change_invalidates_context(
    authorization_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = authorization_database
    fixture = await seed_authorization_fixture(factory, prefix="AUTHZVERSION")
    async with factory() as session, session.begin():
        await session.execute(
            update(User)
            .where(User.id == fixture.authenticated.user.id)
            .values(authorization_version=2)
        )
    async with factory() as session:
        with pytest.raises(TenantAccessDeniedError):
            await AuthorizationService().resolve(
                session,
                authenticated=fixture.authenticated,
                company_id=fixture.company_id,
            )


@pytest.mark.asyncio
async def test_inactive_assigned_branch_is_not_authorized(
    authorization_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = authorization_database
    fixture = await seed_authorization_fixture(factory, prefix="AUTHZINACTIVEBR")
    async with factory() as session, session.begin():
        await session.execute(
            update(Branch)
            .where(Branch.id == fixture.authorized_branch_id)
            .values(status="inactive")
        )
    async with factory() as session:
        with pytest.raises(TenantAccessDeniedError):
            await AuthorizationService().resolve(
                session,
                authenticated=fixture.authenticated,
                company_id=fixture.company_id,
                branch_id=fixture.authorized_branch_id,
            )


@pytest.mark.asyncio
async def test_router_dependency_enforces_permission_and_branch_scope(
    authorization_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = authorization_database
    fixture = await seed_authorization_fixture(factory, prefix="AUTHZROUTER")
    app = FastAPI()

    async def database_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    async def identity_override() -> AuthenticatedContext:
        return fixture.authenticated

    app.dependency_overrides[get_database_session] = database_override
    app.dependency_overrides[get_security_database_session] = database_override
    app.dependency_overrides[get_authenticated_context] = identity_override

    @app.get("/allowed")
    async def allowed(
        context: AuthorizationContext = Depends(
            require_permission("AUTHZROUTER_CUSTOMER_VIEW")
        ),
    ) -> dict[str, str]:
        return {"company_id": str(context.company.id)}

    @app.get("/missing-permission")
    async def missing_permission(
        context: AuthorizationContext = Depends(require_permission("CUSTOMER_DELETE")),
    ) -> dict[str, str]:
        return {"company_id": str(context.company.id)}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        allowed_response = await client.get(
            "/allowed",
            headers={
                "X-Company-ID": str(fixture.company_id),
                "X-Branch-ID": str(fixture.authorized_branch_id),
            },
        )
        assert allowed_response.status_code == 200

        missing_permission_response = await client.get(
            "/missing-permission",
            headers={"X-Company-ID": str(fixture.company_id)},
        )
        assert missing_permission_response.status_code == 403

        wrong_branch_response = await client.get(
            "/allowed",
            headers={
                "X-Company-ID": str(fixture.company_id),
                "X-Branch-ID": str(fixture.unauthorized_branch_id),
            },
        )
        assert wrong_branch_response.status_code == 403

        missing_company_response = await client.get("/allowed")
        assert missing_company_response.status_code == 422


@pytest.mark.asyncio
async def test_accessible_companies_router_uses_authenticated_identity(
    authorization_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = authorization_database
    fixture = await seed_authorization_fixture(factory, prefix="AUTHZDISCOVERY")
    app = FastAPI()
    app.include_router(authorization_router)

    async def database_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    async def identity_override() -> AuthenticatedContext:
        return fixture.authenticated

    app.dependency_overrides[get_database_session] = database_override
    app.dependency_overrides[get_authenticated_context] = identity_override

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/authorization/companies")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(fixture.company_id),
            "code": "AUTHZDISCOVERYA",
            "name": "AUTHZDISCOVERY Company",
            "membership_id": response.json()[0]["membership_id"],
            "default_branch_id": None,
            "has_all_branch_access": False,
            "branches": [
                {
                    "id": str(fixture.authorized_branch_id),
                    "code": "AUTHZDISCOVERYBR1",
                    "name": "Authorized Branch",
                    "is_primary": True,
                }
            ],
        }
    ]


@pytest.mark.asyncio
async def test_request_security_reads_do_not_conflict_with_service_transaction(
    authorization_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = authorization_database
    fixture = await seed_authorization_fixture(factory, prefix="REQUESTTX")
    claims = fixture.authenticated.claims
    token, _ = access_token_service.issue(
        user_id=claims.user_id,
        session_id=claims.session_id,
        credential_version=claims.credential_version,
        authorization_version=claims.authorization_version,
    )
    application_sessions: list[AsyncSession] = []
    security_sessions: list[AsyncSession] = []
    app = FastAPI()

    async def application_session_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            application_sessions.append(session)
            yield session

    async def security_session_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            security_sessions.append(session)
            yield session

    app.dependency_overrides[get_database_session] = application_session_override
    app.dependency_overrides[get_security_database_session] = security_session_override

    @app.post("/mutate")
    async def mutate(
        context: AuthorizationContext = Depends(
            require_permission("REQUESTTX_CUSTOMER_VIEW")
        ),
        session: AsyncSession = Depends(get_database_session),
        fail_after_staging: bool = False,
    ) -> dict[str, str]:
        await RequestMutationProbe.execute(
            session,
            context=context,
            fail_after_staging=fail_after_staging,
        )
        return {"status": "committed"}

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Company-ID": str(fixture.company_id),
    }
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        committed = await client.post("/mutate", headers=headers)
        rolled_back = await client.post(
            "/mutate?fail_after_staging=true", headers=headers
        )
        unauthenticated = await client.post(
            "/mutate", headers={"X-Company-ID": str(fixture.company_id)}
        )

    assert committed.status_code == 200
    assert committed.json() == {"status": "committed"}
    assert rolled_back.status_code == 500
    assert unauthenticated.status_code == 401
    assert len(application_sessions) == 2
    assert len(security_sessions) == 3
    assert all(
        application is not security
        for application, security in zip(
            application_sessions, security_sessions[:2], strict=True
        )
    )
    async with factory() as session:
        event_count = await session.scalar(
            select(func.count())
            .select_from(BusinessEvent)
            .where(
                BusinessEvent.company_id == fixture.company_id,
                BusinessEvent.entity_type == "transaction_contract_probe",
            )
        )
    assert event_count == 1
