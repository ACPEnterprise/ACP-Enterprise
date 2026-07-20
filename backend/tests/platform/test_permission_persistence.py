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
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def permission_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(settings.database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


async def create_company(engine: AsyncEngine, code: str) -> UUID:
    company_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(Company).values(
                id=company_id,
                name=f"{code} Company",
                code=code,
                status="active",
                timezone="America/New_York",
            )
        )
    return company_id


async def create_user_membership(
    engine: AsyncEngine,
    *,
    company_id: UUID,
    email: str,
) -> tuple[UUID, UUID]:
    user_id = uuid4()
    membership_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(User).values(
                id=user_id,
                normalized_email=email,
                first_name="Role",
                last_name="Tester",
                display_name="Role Tester",
                status="active",
            )
        )
        await connection.execute(
            insert(Membership).values(
                id=membership_id,
                user_id=user_id,
                company_id=company_id,
                status="active",
                has_all_branch_access=False,
            )
        )
    return user_id, membership_id


async def create_role(engine: AsyncEngine, company_id: UUID, code: str) -> UUID:
    role_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(Role).values(
                id=role_id,
                company_id=company_id,
                code=code,
                name=f"{code} Role",
                status="active",
                is_system=False,
            )
        )
    return role_id


async def create_permission(engine: AsyncEngine, code: str) -> UUID:
    permission_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(Permission).values(
                id=permission_id,
                code=code,
                name=code.replace("_", " ").title(),
                resource="customer",
                action="view",
                status="active",
            )
        )
    return permission_id


@pytest.mark.asyncio
async def test_permission_code_status_and_retirement_constraints(
    permission_engine: AsyncEngine,
) -> None:
    await create_permission(permission_engine, "CUSTOMER_VIEW")

    with pytest.raises(IntegrityError):
        async with permission_engine.begin() as connection:
            await connection.execute(
                insert(Permission).values(
                    code="CUSTOMER_VIEW",
                    name="Duplicate",
                    resource="customer",
                    action="view",
                    status="active",
                )
            )

    invalid_permissions: tuple[dict[str, object], ...] = (
        {"status": "unknown", "retired_at": None},
        {"status": "active", "retired_at": utc_now()},
        {"status": "retired", "retired_at": None},
    )
    for index, invalid in enumerate(invalid_permissions):
        with pytest.raises(IntegrityError):
            async with permission_engine.begin() as connection:
                await connection.execute(
                    insert(Permission).values(
                        code=f"INVALID_PERMISSION_{index}",
                        name="Invalid Permission",
                        resource="customer",
                        action="invalid",
                        **invalid,
                    )
                )


@pytest.mark.asyncio
async def test_company_role_code_status_and_archival_constraints(
    permission_engine: AsyncEngine,
) -> None:
    company_id = await create_company(permission_engine, "ROLEA")
    other_company_id = await create_company(permission_engine, "ROLEB")
    role_id = await create_role(permission_engine, company_id, "DISPATCHER")
    await create_role(permission_engine, other_company_id, "DISPATCHER")

    with pytest.raises(IntegrityError):
        async with permission_engine.begin() as connection:
            await connection.execute(
                insert(Role).values(
                    company_id=company_id,
                    code="DISPATCHER",
                    name="Duplicate Dispatcher",
                    status="active",
                    is_system=False,
                )
            )

    for status, archived_at in (
        ("unknown", None),
        ("active", utc_now()),
        ("archived", None),
    ):
        with pytest.raises(IntegrityError):
            async with permission_engine.begin() as connection:
                await connection.execute(
                    insert(Role).values(
                        company_id=company_id,
                        code=f"INVALID_{status}_{archived_at is not None}",
                        name="Invalid Role",
                        status=status,
                        archived_at=archived_at,
                        is_system=False,
                    )
                )

    async with permission_engine.begin() as connection:
        await connection.execute(
            update(Role)
            .where(Role.id == role_id)
            .values(status="archived", archived_at=utc_now())
        )
    await create_role(permission_engine, company_id, "DISPATCHER")


@pytest.mark.asyncio
async def test_role_permission_is_unique_and_restrictive(
    permission_engine: AsyncEngine,
) -> None:
    company_id = await create_company(permission_engine, "ROLEPERM")
    role_id = await create_role(permission_engine, company_id, "CSR")
    permission_id = await create_permission(permission_engine, "CUSTOMER_CREATE")

    async with permission_engine.begin() as connection:
        await connection.execute(
            insert(RolePermission).values(
                role_id=role_id,
                permission_id=permission_id,
            )
        )

    with pytest.raises(IntegrityError):
        async with permission_engine.begin() as connection:
            await connection.execute(
                insert(RolePermission).values(
                    role_id=role_id,
                    permission_id=permission_id,
                )
            )

    with pytest.raises(IntegrityError):
        async with permission_engine.begin() as connection:
            await connection.execute(
                delete(Permission).where(Permission.id == permission_id)
            )


@pytest.mark.asyncio
async def test_membership_role_company_boundary_and_historical_reassignment(
    permission_engine: AsyncEngine,
) -> None:
    company_id = await create_company(permission_engine, "ASSIGNA")
    other_company_id = await create_company(permission_engine, "ASSIGNB")
    _, membership_id = await create_user_membership(
        permission_engine,
        company_id=company_id,
        email="role-assignment@example.com",
    )
    role_id = await create_role(permission_engine, company_id, "MANAGER")
    other_role_id = await create_role(permission_engine, other_company_id, "MANAGER")

    with pytest.raises(IntegrityError):
        async with permission_engine.begin() as connection:
            await connection.execute(
                insert(MembershipRole).values(
                    company_id=company_id,
                    membership_id=membership_id,
                    role_id=other_role_id,
                )
            )

    assignment_id = uuid4()
    assigned_at = utc_now()
    async with permission_engine.begin() as connection:
        await connection.execute(
            insert(MembershipRole).values(
                id=assignment_id,
                company_id=company_id,
                membership_id=membership_id,
                role_id=role_id,
                assigned_at=assigned_at,
            )
        )

    with pytest.raises(IntegrityError):
        async with permission_engine.begin() as connection:
            await connection.execute(
                insert(MembershipRole).values(
                    company_id=company_id,
                    membership_id=membership_id,
                    role_id=role_id,
                )
            )

    with pytest.raises(IntegrityError):
        async with permission_engine.begin() as connection:
            await connection.execute(
                update(MembershipRole)
                .where(MembershipRole.id == assignment_id)
                .values(revoked_at=assigned_at - timedelta(seconds=1))
            )

    async with permission_engine.begin() as connection:
        await connection.execute(
            update(MembershipRole)
            .where(MembershipRole.id == assignment_id)
            .values(revoked_at=assigned_at + timedelta(seconds=1))
        )
        await connection.execute(
            insert(MembershipRole).values(
                company_id=company_id,
                membership_id=membership_id,
                role_id=role_id,
            )
        )


@pytest.mark.asyncio
async def test_empty_assignments_and_roles_do_not_change_branch_access(
    permission_engine: AsyncEngine,
) -> None:
    company_id = await create_company(permission_engine, "EMPTYAUTH")
    _, membership_id = await create_user_membership(
        permission_engine,
        company_id=company_id,
        email="empty-auth@example.com",
    )
    role_id = await create_role(permission_engine, company_id, "EMPTY_ROLE")

    async with permission_engine.connect() as connection:
        membership_role_count = await connection.scalar(
            select(func.count())
            .select_from(MembershipRole)
            .where(MembershipRole.membership_id == membership_id)
        )
        role_permission_count = await connection.scalar(
            select(func.count())
            .select_from(RolePermission)
            .where(RolePermission.role_id == role_id)
        )
        branch_state = (
            await connection.execute(
                select(
                    Membership.has_all_branch_access,
                    Membership.default_branch_id,
                ).where(Membership.id == membership_id)
            )
        ).one()

    assert membership_role_count == 0
    assert role_permission_count == 0
    assert branch_state.has_all_branch_access is False
    assert branch_state.default_branch_id is None


def test_orm_mapper_configuration_has_no_warnings() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        configure_mappers()
