import secrets
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.platform.audit.models import AuditRecord
from app.platform.auth.errors import InvalidCredentialsError, SessionInvalidError
from app.platform.auth.services import (
    access_token_service,
    authentication_service,
    password_service,
    recovery_service,
)
from app.platform.permissions.authorization import (
    PermissionDeniedError,
    TenantAccessDeniedError,
    authorization_service,
)
from app.platform.permissions.codes import WorkerIdentityPermission
from app.platform.permissions.models import MembershipRole, Permission, RolePermission
from app.platform.service_principals.contracts import (
    AUTHENTICATION_METHOD,
    READ_PERMISSION_CODES,
)
from app.platform.service_principals.models import AcceptanceServicePrincipal
from app.platform.service_principals.service import (
    MAX_ACCESS_LIFETIME,
    AcceptanceServicePrincipalService,
)
from app.platform.users.models import UserCredential
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
    utc_now,
)


@pytest_asyncio.fixture
async def principal_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    async with factory() as session, session.begin():
        permission_codes = (*sorted(READ_PERMISSION_CODES), "COMPANY_WORKFORCE_MANAGE")
        for index, code in enumerate(permission_codes):
            if (
                await session.scalar(
                    select(Permission.id).where(Permission.code == code)
                )
                is None
            ):
                session.add(
                    Permission(
                        code=code,
                        name=code,
                        resource=f"acceptance_{index}",
                        action="read",
                        status="active",
                    )
                )
    try:
        yield fixture
    finally:
        await engine.dispose()


def platform_context(fixture: ServiceFixture):
    return context_with_permissions(
        fixture.context.user,
        fixture.context.company,
        fixture.context.membership,
        (WorkerIdentityPermission.MANAGE,),
    )


@pytest.mark.asyncio
async def test_representative_mutation_authority_is_denied(
    principal_database: ServiceFixture,
) -> None:
    context = context_with_permissions(
        principal_database.context.user,
        principal_database.context.company,
        principal_database.context.membership,
        tuple(sorted(READ_PERMISSION_CODES)),
    )
    mutation_permissions = (
        "COMPANY_WORKFORCE_MANAGE",
        "COMPANY_IDENTITY_ONBOARDING_MANAGE",
        "COMPANY_MEMBERSHIP_MANAGE",
        "COMPANY_PERMISSION_MANAGE",
        "COMPANY_PAYROLL_POLICY_MANAGE",
        "COMPANY_PAYROLL_COMPENSATION_MANAGE",
        "COMPANY_PAYROLL_RUN_ASSEMBLE",
        "COMPANY_PAYROLL_CALCULATION_EXECUTE",
        "COMPANY_PAYROLL_RUN_APPROVE",
        "COMPANY_PAYROLL_PAYMENT_EXECUTION_AUTHORIZE",
        "COMPANY_TIMEKEEPING_MANUAL_ENTRY",
        "COMPANY_TIMEKEEPING_CORRECT",
        "COMPANY_TIMEKEEPING_APPROVE",
    )
    for permission in mutation_permissions:
        with pytest.raises(PermissionDeniedError):
            authorization_service.require_permission(context, permission)


@pytest.mark.asyncio
async def test_provision_is_idempotent_and_grants_only_exact_read_permissions(
    principal_database: ServiceFixture,
) -> None:
    fixture = principal_database
    service = AcceptanceServicePrincipalService()
    async with fixture.factory() as session, session.begin():
        first = await service.provision(session, context=platform_context(fixture))
    async with fixture.factory() as session, session.begin():
        replay = await service.provision(session, context=platform_context(fixture))
        await service._assert_exact_permissions(session, first.membership_id)
    assert first.created is True
    assert replay.created is False
    assert replay.principal_id == first.principal_id
    assert READ_PERMISSION_CODES == {
        "COMPANY_WORKFORCE_READ",
        "COMPANY_PAYROLL_POLICY_READ",
        "COMPANY_PAYROLL_COMPENSATION_READ",
        "COMPANY_PAYROLL_RUN_READ",
        "COMPANY_PAYROLL_REPORTING_READ",
        "COMPANY_TIMEKEEPING_ADMIN_READ",
    }
    assert not any(
        "MANAGE" in code
        or "ASSEMBLE" in code
        or "CALCULATE" in code
        or "APPROVE" in code
        or "CLOSE" in code
        for code in READ_PERMISSION_CODES
    )
    read_context = context_with_permissions(
        fixture.context.user,
        fixture.context.company,
        fixture.context.membership,
        tuple(sorted(READ_PERMISSION_CODES)),
    )
    for permission in READ_PERMISSION_CODES:
        authorization_service.require_permission(read_context, permission)


@pytest.mark.asyncio
async def test_short_lived_session_uses_canonical_auth_and_is_company_scoped(
    principal_database: ServiceFixture,
) -> None:
    fixture = principal_database
    service = AcceptanceServicePrincipalService()
    now = utc_now()
    async with fixture.factory() as session, session.begin():
        principal = await service.provision(
            session, context=platform_context(fixture), now=now
        )
        issued = await service.issue_session(
            session,
            context=platform_context(fixture),
            principal_id=principal.principal_id,
            lifetime=MAX_ACCESS_LIFETIME,
            now=now,
        )
    claims = access_token_service.decode(issued.access_token)
    async with fixture.factory() as session:
        authenticated = await authentication_service.validate_access_context(
            session, claims
        )
        assert (
            authenticated.authentication_session.authentication_method
            == AUTHENTICATION_METHOD
        )
        context = await authorization_service.resolve(
            session,
            authenticated=authenticated,
            company_id=fixture.context.company.id,
            branch_id=None,
        )
        assert context.permission_codes == READ_PERMISSION_CODES
        with pytest.raises(TenantAccessDeniedError):
            await authorization_service.resolve(
                session,
                authenticated=authenticated,
                company_id=fixture.other_context.company.id,
                branch_id=None,
            )
        await session.rollback()
    assert issued.expires_at <= now + MAX_ACCESS_LIFETIME
    async with fixture.factory() as session, session.begin():
        role_id = await session.scalar(
            select(MembershipRole.role_id).where(
                MembershipRole.membership_id == principal.membership_id
            )
        )
        mutation_permission_id = await session.scalar(
            select(Permission.id).where(Permission.code == "COMPANY_WORKFORCE_MANAGE")
        )
        assert role_id is not None and mutation_permission_id is not None
        session.add(
            RolePermission(
                role_id=role_id,
                permission_id=mutation_permission_id,
                assigned_by_user_id=fixture.context.user.id,
            )
        )
    async with fixture.factory() as session:
        authenticated = await authentication_service.validate_access_context(
            session, claims
        )
        with pytest.raises(TenantAccessDeniedError):
            await authorization_service.resolve(
                session,
                authenticated=authenticated,
                company_id=fixture.context.company.id,
                branch_id=None,
            )


@pytest.mark.asyncio
async def test_environment_mismatch_and_revocation_invalidate_session(
    principal_database: ServiceFixture,
) -> None:
    fixture = principal_database
    service = AcceptanceServicePrincipalService()
    now = utc_now()
    async with fixture.factory() as session, session.begin():
        principal = await service.provision(
            session, context=platform_context(fixture), now=now
        )
        issued = await service.issue_session(
            session,
            context=platform_context(fixture),
            principal_id=principal.principal_id,
            lifetime=timedelta(minutes=30),
            now=now,
        )
    claims = access_token_service.decode(issued.access_token)
    mismatched_auth = type(authentication_service)(
        authentication_service.password_service,
        authentication_service.token_service,
        authentication_service.access_token_service,
        settings.model_copy(update={"environment": "production"}),
    )
    async with fixture.factory() as session:
        with pytest.raises(SessionInvalidError):
            await mismatched_auth.validate_access_context(session, claims)
    async with fixture.factory() as session, session.begin():
        await service.revoke(
            session,
            context=platform_context(fixture),
            principal_id=principal.principal_id,
            now=now + timedelta(minutes=1),
        )
    async with fixture.factory() as session:
        with pytest.raises(SessionInvalidError):
            await authentication_service.validate_access_context(session, claims)
        record = await session.get(AcceptanceServicePrincipal, principal.principal_id)
        credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == principal.user_id)
        )
        audit_count = await session.scalar(
            select(func.count(AuditRecord.id)).where(
                AuditRecord.company_id == fixture.context.company.id,
                AuditRecord.action.in_(
                    {
                        "platform.acceptance_service_principal_provisioned",
                        "platform.acceptance_service_session_issued",
                        "platform.acceptance_service_principal_revoked",
                    }
                ),
            )
        )
    assert record is not None and record.state == "revoked" and record.version == 2
    assert credential is not None and credential.credential_version == 2
    assert audit_count == 3


@pytest.mark.asyncio
async def test_permission_drift_and_unauthorized_provisioning_fail_closed(
    principal_database: ServiceFixture,
) -> None:
    fixture = principal_database
    service = AcceptanceServicePrincipalService()
    denied = replace(platform_context(fixture), effective_permissions=())
    async with fixture.factory() as session, session.begin():
        with pytest.raises(PermissionError):
            await service.provision(session, context=denied)


@pytest.mark.asyncio
async def test_non_human_identity_cannot_use_password_or_recovery(
    principal_database: ServiceFixture,
) -> None:
    fixture = principal_database
    service = AcceptanceServicePrincipalService()
    known_password = f"Test-{secrets.token_urlsafe(24)}-42!"
    async with fixture.factory() as session, session.begin():
        principal = await service.provision(session, context=platform_context(fixture))
        credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == principal.user_id)
        )
        assert credential is not None
        credential.password_hash = password_service.hash_password(known_password)
    async with fixture.factory() as session:
        with pytest.raises(InvalidCredentialsError):
            await authentication_service.authenticate(
                session,
                email=f"acceptance+{fixture.context.company.id}@service.twelve-hats.invalid",
                password=known_password,
            )
    async with fixture.factory() as session:
        delivery = await recovery_service.request_password_reset(
            session,
            email=f"acceptance+{fixture.context.company.id}@service.twelve-hats.invalid",
        )
    assert delivery.plaintext_token is None
