from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.database.session import get_database_session
from app.platform.auth import models as auth_models  # noqa: F401
from app.platform.branch import models as branch_models  # noqa: F401
from app.platform.company import membership_models  # noqa: F401
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees import models as employee_models  # noqa: F401
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.dependencies import get_authorization_context
from app.platform.permissions.models import Permission
from app.platform.users.identity_models import PendingEmailChange
from app.platform.users.identity_repository import UserIdentityRepository
from app.platform.users.identity_router import (
    administration_router,
    self_service_router,
)
from app.platform.users.models import User, UserCredential


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ApiFixture:
    administrator_context: AuthorizationContext
    target_context: AuthorizationContext
    target_user: User


@pytest_asyncio.fixture
async def identity_api_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


async def create_api_fixture(
    factory: async_sessionmaker[AsyncSession],
    *,
    administrator_has_permission: bool = True,
) -> ApiFixture:
    suffix = uuid4().hex[:10]
    company = Company(
        name=f"Identity API {suffix}",
        code=f"IDA{suffix.upper()}",
        status="active",
        timezone="America/New_York",
    )
    administrator = User(
        normalized_email=f"api-admin-{suffix}@example.com",
        first_name="API",
        last_name="Administrator",
        display_name="API Administrator",
        status="active",
    )
    target = User(
        normalized_email=f"api-target-{suffix}@example.com",
        first_name="API",
        last_name="Target",
        display_name="API Target",
        status="active",
    )
    now = utc_now()
    async with factory() as session, session.begin():
        session.add_all([company, administrator, target])
        await session.flush()
        admin_membership = Membership(
            user_id=administrator.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=True,
            invited_at=now,
            accepted_at=now,
        )
        target_membership = Membership(
            user_id=target.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=False,
            invited_at=now,
            accepted_at=now,
        )
        session.add_all(
            [
                admin_membership,
                target_membership,
                UserCredential(
                    user_id=administrator.id,
                    password_hash="$argon2id$api-admin-test-hash",
                ),
                UserCredential(
                    user_id=target.id,
                    password_hash="$argon2id$api-target-test-hash",
                ),
            ]
        )
        await session.flush()

    permission = Permission(
        code=AdministrationPermission.COMPANY_ADMINISTER,
        name="Company Administration",
        resource="company",
        action="administer",
        status="active",
    )
    admin_permissions = (permission,) if administrator_has_permission else ()
    return ApiFixture(
        administrator_context=AuthorizationContext(
            user=administrator,
            company=company,
            membership=admin_membership,
            authorized_branches=(),
            active_branch=None,
            effective_roles=(),
            effective_permissions=admin_permissions,
            credential_version=1,
            authorization_version=1,
        ),
        target_context=AuthorizationContext(
            user=target,
            company=company,
            membership=target_membership,
            authorized_branches=(),
            active_branch=None,
            effective_roles=(),
            effective_permissions=(),
            credential_version=1,
            authorization_version=1,
        ),
        target_user=target,
    )


def create_test_app(
    factory: async_sessionmaker[AsyncSession],
    context: AuthorizationContext | None,
) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(self_service_router)
    test_app.include_router(administration_router)

    async def database_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    test_app.dependency_overrides[get_database_session] = database_override
    if context is not None:

        async def context_override() -> AuthorizationContext:
            return context

        test_app.dependency_overrides[get_authorization_context] = context_override
    return test_app


async def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_administrative_request_and_self_confirmation_success(
    identity_api_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_api_database
    fixture = await create_api_fixture(factory)
    proposed = f"api-changed-{uuid4().hex}@example.com"
    admin_app = create_test_app(factory, fixture.administrator_context)
    async with await client_for(admin_app) as client:
        availability = await client.post(
            f"/api/v1/identity-admin/users/{fixture.target_user.id}/email-availability",
            json={"email": proposed},
        )
        request = await client.post(
            f"/api/v1/identity-admin/users/{fixture.target_user.id}/email-change",
            json={"email": proposed.upper()},
        )
    assert availability.status_code == 200
    assert availability.json() == {"available": True}
    assert request.status_code == 201
    body = request.json()
    assert body["change"]["proposed_email"] == proposed
    assert body["change"]["status"] == "pending"
    assert body["development_token"] is not None

    target_app = create_test_app(factory, fixture.target_context)
    async with await client_for(target_app) as client:
        confirmation = await client.post(
            "/api/v1/identity/email-change/confirm",
            json={"token": body["development_token"]},
        )
        state = await client.get("/api/v1/identity/me")
    assert confirmation.status_code == 200
    assert confirmation.json()["normalized_email"] == proposed
    assert state.status_code == 200
    assert state.json()["normalized_email"] == proposed
    assert state.json()["pending_email_change"] is None


@pytest.mark.asyncio
async def test_authentication_permission_and_validation_fail_closed(
    identity_api_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_api_database
    fixture = await create_api_fixture(factory, administrator_has_permission=False)
    unauthenticated_app = create_test_app(factory, None)
    async with await client_for(unauthenticated_app) as client:
        unauthenticated = await client.get("/api/v1/identity/me")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["detail"] == "Authentication required."

    denied_app = create_test_app(factory, fixture.administrator_context)
    async with await client_for(denied_app) as client:
        denied = await client.post(
            f"/api/v1/identity-admin/users/{fixture.target_user.id}/email-availability",
            json={"email": "valid@example.com"},
        )
        invalid = await client.post(
            f"/api/v1/identity-admin/users/{fixture.target_user.id}/email-change",
            json={"email": "not-an-email", "unknown": True},
        )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Permission denied."
    assert invalid.status_code == 403

    allowed_fixture = await create_api_fixture(factory)
    allowed_app = create_test_app(factory, allowed_fixture.administrator_context)
    async with await client_for(allowed_app) as client:
        validation = await client.post(
            f"/api/v1/identity-admin/users/{allowed_fixture.target_user.id}/email-change",
            json={"email": "not-an-email", "unknown": True},
        )
    assert validation.status_code == 422


@pytest.mark.asyncio
async def test_company_isolation_and_self_service_target_restriction(
    identity_api_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_api_database
    first = await create_api_fixture(factory)
    second = await create_api_fixture(factory)
    app = create_test_app(factory, first.administrator_context)
    async with await client_for(app) as client:
        isolated = await client.get(
            f"/api/v1/identity-admin/users/{second.target_user.id}"
        )
        request = await client.post(
            f"/api/v1/identity-admin/users/{first.target_user.id}/email-change",
            json={"email": f"restricted-{uuid4().hex}@example.com"},
        )
    assert isolated.status_code == 404
    token = request.json()["development_token"]

    async with await client_for(app) as client:
        wrong_identity = await client.post(
            "/api/v1/identity/email-change/confirm",
            json={"token": token},
        )
    assert wrong_identity.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_revocation_and_confirmation_error_mapping(
    identity_api_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_api_database
    fixture = await create_api_fixture(factory)
    app = create_test_app(factory, fixture.administrator_context)
    proposed = f"duplicate-api-{uuid4().hex}@example.com"
    async with await client_for(app) as client:
        created = await client.post(
            f"/api/v1/identity-admin/users/{fixture.target_user.id}/email-change",
            json={"email": proposed},
        )
        duplicate = await client.post(
            f"/api/v1/identity-admin/users/{fixture.target_user.id}/email-change",
            json={"email": proposed},
        )
        change_id = created.json()["change"]["id"]
        revoked = await client.delete(
            f"/api/v1/identity-admin/email-changes/{change_id}"
        )
        repeated = await client.delete(
            f"/api/v1/identity-admin/email-changes/{change_id}"
        )
    assert duplicate.status_code == 409
    detail = duplicate.json()["detail"]
    assert detail["code"] == "resource_state_conflict"
    assert detail["message"] == "Identity operation conflicts with current state."
    assert detail["recovery"] == "RETRY_AFTER_REFRESH"
    assert revoked.status_code == 200
    assert revoked.json()["changed"] is True
    assert repeated.status_code == 200
    assert repeated.json()["changed"] is False

    target_app = create_test_app(factory, fixture.target_context)
    async with await client_for(target_app) as client:
        confirmation = await client.post(
            "/api/v1/identity/email-change/confirm",
            json={"token": created.json()["development_token"]},
        )
    assert confirmation.status_code == 409
    confirmation_detail = confirmation.json()["detail"]
    assert confirmation_detail["code"] == "resource_state_conflict"
    assert confirmation_detail["recovery"] == "RETRY_AFTER_REFRESH"

    async with await client_for(app) as client:
        expiring = await client.post(
            f"/api/v1/identity-admin/users/{fixture.target_user.id}/email-change",
            json={"email": f"expired-api-{uuid4().hex}@example.com"},
        )
    expiring_body = expiring.json()
    async with factory() as session, session.begin():
        record = await session.get(PendingEmailChange, expiring_body["change"]["id"])
        assert record is not None
        record.created_at = utc_now() - timedelta(hours=2)
        record.expires_at = utc_now() - timedelta(hours=1)
    async with await client_for(target_app) as client:
        expired = await client.post(
            "/api/v1/identity/email-change/confirm",
            json={"token": expiring_body["development_token"]},
        )
    assert expired.status_code == 409


@pytest.mark.asyncio
async def test_forced_reset_api_is_idempotent_and_clear_fails_before_change(
    identity_api_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = identity_api_database
    fixture = await create_api_fixture(factory)
    app = create_test_app(factory, fixture.administrator_context)
    path = (
        f"/api/v1/identity-admin/users/{fixture.target_user.id}/forced-password-reset"
    )
    async with await client_for(app) as client:
        required = await client.post(
            path, json={"reason_code": "administrator_required"}
        )
        repeated = await client.post(
            path, json={"reason_code": "administrator_required"}
        )
        premature_clear = await client.post(f"{path}/clear")
    assert required.status_code == 200
    assert required.json()["changed"] is True
    assert repeated.status_code == 200
    assert repeated.json()["changed"] is False
    assert premature_clear.status_code == 409

    async with factory() as session, session.begin():
        credential = await UserIdentityRepository.get_credential_for_update(
            session, fixture.target_user.id
        )
        assert credential is not None
        assert credential.password_change_required_at is not None
        credential.password_changed_at = (
            credential.password_change_required_at + timedelta(seconds=1)
        )
    async with await client_for(app) as client:
        cleared = await client.post(f"{path}/clear")
    assert cleared.status_code == 200
    assert cleared.json()["changed"] is True
    assert cleared.json()["required"] is False


def test_identity_openapi_contract_is_versioned_described_and_secured() -> None:
    test_app = FastAPI()
    test_app.include_router(self_service_router)
    test_app.include_router(administration_router)
    schema = test_app.openapi()
    paths = schema["paths"]
    required_paths = {
        "/api/v1/identity/me",
        "/api/v1/identity/email-change/confirm",
        "/api/v1/identity-admin/users/{user_id}",
        "/api/v1/identity-admin/users/{user_id}/email-availability",
        "/api/v1/identity-admin/users/{user_id}/email-change",
        "/api/v1/identity-admin/email-changes/{change_id}",
        "/api/v1/identity-admin/users/{user_id}/forced-password-reset",
        "/api/v1/identity-admin/users/{user_id}/forced-password-reset/clear",
    }
    assert required_paths <= set(paths)
    for path in required_paths:
        for operation in paths[path].values():
            assert operation["summary"]
            assert operation["security"] == [{"HTTPBearer": []}]
    request_schema = schema["components"]["schemas"]["AdministrativeEmailChangeRequest"]
    assert request_schema["additionalProperties"] is False
    assert request_schema["properties"]["email"]["description"]
    assert request_schema["properties"]["email"]["examples"]
