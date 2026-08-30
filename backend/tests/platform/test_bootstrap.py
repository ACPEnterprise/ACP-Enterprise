import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from app.core.config import Settings, settings
from app.core.database import Base
from app.customers import models as customer_models  # noqa: F401
from app.inventory import models as inventory_models  # noqa: F401
from app.platform.audit import models as audit_models  # noqa: F401
from app.platform.auth import models as auth_models
from app.platform.auth.access_tokens import AccessTokenService
from app.platform.auth.passwords import PasswordService
from app.platform.auth.services import AuthenticatedContext, AuthenticationService
from app.platform.auth.tokens import SecurityTokenService
from app.platform.bootstrap.config import (
    BootstrapConfiguration,
    load_bootstrap_configuration,
)
from app.platform.bootstrap.repository import BootstrapRepository
from app.platform.bootstrap.service import BootstrapResult, BootstrapService
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.launch_controls import (
    COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS,
    LAUNCH_ROLE_MATRIX,
    LaunchRoleCode,
)
from app.platform.permissions.authorization import AuthorizationService
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.catalog_sync import PermissionCatalogSyncService
from app.platform.permissions.codes import SchedulingPermission
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User, UserCredential
from app.scheduling import models as scheduling_models  # noqa: F401
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@dataclass(frozen=True)
class BootstrapDatabase:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def bootstrap_database() -> AsyncIterator[BootstrapDatabase]:
    schema = f"bootstrap_{uuid4().hex}"
    administration_engine = create_async_engine(settings.database_url)
    async with administration_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_async_engine(
        settings.database_url,
        connect_args={"server_settings": {"search_path": f"{schema}, public"}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection, checkfirst=False
            )
        )

    try:
        yield BootstrapDatabase(
            engine=engine,
            sessions=async_sessionmaker(engine, expire_on_commit=False),
        )
    finally:
        await engine.dispose()
        async with administration_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await administration_engine.dispose()


def bootstrap_settings(database_url: str) -> Settings:
    return Settings(
        environment="test",
        database_url=database_url,
        access_token_keys={"test": "bootstrap-test-signing-key-32-characters"},
        access_token_active_kid="test",
        security_token_hmac_key="bootstrap-test-hmac-key-32-characters",
        argon2_time_cost=1,
        argon2_memory_cost_kib=1024,
        argon2_parallelism=1,
    )


def configuration(*, suffix: str = "A") -> BootstrapConfiguration:
    return BootstrapConfiguration.model_validate(
        {
            "company_name": f"Bootstrap Company {suffix}",
            "company_code": f"BOOT{suffix}",
            "company_timezone": "America/New_York",
            "branch_name": "Main Branch",
            "branch_code": "MAIN",
            "administrator_email": f"admin-{suffix.lower()}@example.com",
            "administrator_first_name": "Initial",
            "administrator_last_name": "Administrator",
            "administrator_password": "correct horse battery staple",
        }
    )


def service(configuration_settings: Settings) -> BootstrapService:
    return BootstrapService(
        repository=BootstrapRepository(),
        password_service=PasswordService(configuration_settings),
    )


async def run_bootstrap(
    database: BootstrapDatabase,
    bootstrap_service: BootstrapService,
    inputs: BootstrapConfiguration,
) -> BootstrapResult:
    async with database.sessions() as session:
        return await bootstrap_service.initialize(session, inputs)


@pytest.mark.asyncio
async def test_first_bootstrap_creates_complete_authorization_graph(
    bootstrap_database: BootstrapDatabase,
) -> None:
    result = await run_bootstrap(
        bootstrap_database,
        service(bootstrap_settings(settings.database_url)),
        configuration(),
    )

    assert result.initialized
    assert result.company_id is not None
    assert result.branch_id is not None
    assert result.administrator_user_id is not None

    async with bootstrap_database.sessions() as session:
        company = await session.get(Company, result.company_id)
        branch = await session.get(Branch, result.branch_id)
        user = await session.get(User, result.administrator_user_id)
        credential = await session.scalar(
            select(UserCredential).where(
                UserCredential.user_id == result.administrator_user_id
            )
        )
        membership = await session.scalar(
            select(Membership).where(Membership.user_id == result.administrator_user_id)
        )
        roles = (await session.scalars(select(Role).order_by(Role.code))).all()
        permission_codes = set((await session.scalars(select(Permission.code))).all())
        role_permission_count = await session.scalar(
            select(func.count()).select_from(RolePermission)
        )
        membership_role_count = await session.scalar(
            select(func.count()).select_from(MembershipRole)
        )

    assert company is not None and company.status == "active"
    assert branch is not None and branch.is_primary and branch.company_id == company.id
    assert user is not None and user.status == "active"
    assert user.email_verified_at is not None
    assert credential is not None
    assert credential.password_hash != "correct horse battery staple"
    assert credential.password_hash.startswith("$argon2id$")
    assert membership is not None
    assert membership.company_id == company.id
    assert membership.default_branch_id == branch.id
    assert membership.has_all_branch_access is True
    assert [role.code for role in roles] == sorted(
        [definition.code.value for definition in LAUNCH_ROLE_MATRIX]
        + ["COMPANY_USER"]
    )
    assert all(role.is_system for role in roles)
    assert permission_codes == {
        definition.code for definition in permission_catalog.definitions
    }
    assert role_permission_count == sum(
        len(definition.permission_codes) for definition in LAUNCH_ROLE_MATRIX
    )
    assert membership_role_count == 1

    async with bootstrap_database.sessions() as session:
        scheduling_permissions = tuple(
            (
                await session.scalars(
                    select(Permission).where(
                        Permission.code.in_(SchedulingPermission.ALL)
                    )
                )
            ).all()
        )
        administrator_role = await session.scalar(
            select(Role).where(Role.code == "COMPANY_ADMINISTRATOR")
        )
        assert {permission.code for permission in scheduling_permissions} == set(
            SchedulingPermission.ALL
        )
        assert administrator_role is not None
        assert await session.scalar(
            select(func.count())
            .select_from(RolePermission)
            .where(
                RolePermission.role_id == administrator_role.id,
                RolePermission.permission_id.in_(
                    permission.id for permission in scheduling_permissions
                ),
            )
        ) == len(
            SchedulingPermission.ALL & COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS
        )


@pytest.mark.asyncio
async def test_bootstrap_provisions_approved_service_and_own_data_roles(
    bootstrap_database: BootstrapDatabase,
) -> None:
    await run_bootstrap(
        bootstrap_database,
        service(bootstrap_settings(settings.database_url)),
        configuration(suffix="ROLES"),
    )
    expected = {
        definition.code.value: definition.permission_codes
        for definition in LAUNCH_ROLE_MATRIX
        if definition.code in {LaunchRoleCode.SERVICE_CSR, LaunchRoleCode.OWN_DATA_ROLE}
    }
    async with bootstrap_database.sessions() as session:
        roles = (
            await session.scalars(select(Role).where(Role.code.in_(expected)))
        ).all()
        for role in roles:
            codes = set(
                await session.scalars(
                    select(Permission.code)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .where(RolePermission.role_id == role.id)
                )
            )
            assert codes == expected[role.code]
        assert {role.code for role in roles} == set(expected)


@pytest.mark.asyncio
async def test_catalog_sync_adds_only_missing_permissions_idempotently(
    bootstrap_database: BootstrapDatabase,
) -> None:
    result = await run_bootstrap(
        bootstrap_database,
        service(bootstrap_settings(settings.database_url)),
        configuration(suffix="SYNC"),
    )
    assert result.initialized

    async with bootstrap_database.sessions() as session, session.begin():
        scheduling_permission = await session.scalar(
            select(Permission).where(Permission.code == SchedulingPermission.MANAGE)
        )
        assert scheduling_permission is not None
        assignment = await session.scalar(
            select(RolePermission).where(
                RolePermission.permission_id == scheduling_permission.id
            )
        )
        assert assignment is None
        await session.delete(scheduling_permission)
        noncanonical = Permission(
            code="COMPANY_LOCAL_EXTENSION",
            name="Local Extension",
            resource="local_extension",
            action="read",
            status="active",
        )
        session.add(noncanonical)

    async with bootstrap_database.sessions() as session:
        before = {
            permission.code: permission.id
            for permission in (
                await session.scalars(
                    select(Permission).where(
                        Permission.code != "COMPANY_LOCAL_EXTENSION"
                    )
                )
            ).all()
        }
        role_assignments_before = await session.scalar(
            select(func.count()).select_from(RolePermission)
        )
        assert SchedulingPermission.MANAGE not in before

    sync_service = PermissionCatalogSyncService()
    async with bootstrap_database.sessions() as session:
        first = await sync_service.synchronize(session)
    async with bootstrap_database.sessions() as session:
        second = await sync_service.synchronize(session)
        after_records = tuple((await session.scalars(select(Permission))).all())
        synchronized = await session.scalar(
            select(Permission).where(Permission.code == SchedulingPermission.MANAGE)
        )
        role_assignments_after = await session.scalar(
            select(func.count()).select_from(RolePermission)
        )

    after = {permission.code: permission.id for permission in after_records}
    assert first.created_codes == (SchedulingPermission.MANAGE,)
    assert SchedulingPermission.MANAGE not in first.existing_codes
    assert second.created_codes == ()
    assert SchedulingPermission.MANAGE in second.existing_codes
    assert all(after[code] == permission_id for code, permission_id in before.items())
    assert "COMPANY_LOCAL_EXTENSION" in after
    assert role_assignments_after == role_assignments_before
    assert synchronized is not None
    async with bootstrap_database.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(RolePermission)
                .where(RolePermission.permission_id == synchronized.id)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_repeated_bootstrap_is_idempotent(
    bootstrap_database: BootstrapDatabase,
) -> None:
    bootstrap_service = service(bootstrap_settings(settings.database_url))
    first = await run_bootstrap(bootstrap_database, bootstrap_service, configuration())
    second = await run_bootstrap(
        bootstrap_database, bootstrap_service, configuration(suffix="B")
    )

    assert first.initialized is True
    assert second == BootstrapResult(initialized=False)
    async with bootstrap_database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Company)) == 1
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert await session.scalar(select(func.count()).select_from(Role)) == 2


@pytest.mark.asyncio
async def test_concurrent_bootstrap_has_exactly_one_winner(
    bootstrap_database: BootstrapDatabase,
) -> None:
    bootstrap_service = service(bootstrap_settings(settings.database_url))
    results = await asyncio.gather(
        run_bootstrap(bootstrap_database, bootstrap_service, configuration(suffix="C")),
        run_bootstrap(bootstrap_database, bootstrap_service, configuration(suffix="D")),
    )

    assert sorted(result.initialized for result in results) == [False, True]
    async with bootstrap_database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Company)) == 1
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert await session.scalar(select(func.count()).select_from(Membership)) == 1


def test_missing_bootstrap_configuration_is_rejected() -> None:
    with pytest.raises(ValidationError):
        load_bootstrap_configuration({})


class FailingBootstrapRepository(BootstrapRepository):
    def create_system_roles(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        actor_user_id: UUID,
    ) -> dict[str, Role]:
        raise RuntimeError("controlled bootstrap failure")


@pytest.mark.asyncio
async def test_bootstrap_rolls_back_completely_on_failure(
    bootstrap_database: BootstrapDatabase,
) -> None:
    bootstrap_service = BootstrapService(
        repository=FailingBootstrapRepository(),
        password_service=PasswordService(bootstrap_settings(settings.database_url)),
    )
    with pytest.raises(RuntimeError, match="controlled bootstrap failure"):
        await run_bootstrap(bootstrap_database, bootstrap_service, configuration())

    async with bootstrap_database.sessions() as session:
        for model in (
            Company,
            Branch,
            User,
            UserCredential,
            Membership,
            Permission,
            Role,
        ):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.asyncio
async def test_bootstrapped_administrator_can_login_and_resolve_authorization(
    bootstrap_database: BootstrapDatabase,
) -> None:
    runtime_settings = bootstrap_settings(settings.database_url)
    result = await run_bootstrap(
        bootstrap_database,
        service(runtime_settings),
        configuration(),
    )
    assert result.company_id is not None
    assert result.branch_id is not None

    authentication_service = AuthenticationService(
        PasswordService(runtime_settings),
        SecurityTokenService(runtime_settings),
        AccessTokenService(runtime_settings),
        runtime_settings,
    )
    async with bootstrap_database.sessions() as session:
        authenticated = await authentication_service.authenticate(
            session,
            email="ADMIN-A@EXAMPLE.COM",
            password="correct horse battery staple",
            ip_address="127.0.0.1",
            user_agent="bootstrap-test",
        )
    async with bootstrap_database.sessions() as session:
        authentication_session = await session.get(
            auth_models.AuthenticationSession, authenticated.session_id
        )
        assert authentication_session is not None
        claims = AccessTokenService(runtime_settings).decode(authenticated.access_token)
        context = await AuthorizationService().resolve(
            session,
            authenticated=AuthenticatedContext(
                authenticated.user, authentication_session, claims
            ),
            company_id=result.company_id,
            branch_id=result.branch_id,
        )

    assert context.membership.status == "active"
    assert context.role_codes == frozenset({"COMPANY_ADMINISTRATOR"})
    assert context.permission_codes == COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS
    assert context.authorized_branch_ids == frozenset({result.branch_id})
