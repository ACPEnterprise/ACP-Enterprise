from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
import pytest

from app.platform.company.membership_models import Membership
from app.platform.company.admin_service import (
    AccessPolicyNotFoundError,
    CompanyAdministrationService,
)
from app.platform.permissions.catalog import JOB_DEFINITIONS, permission_catalog
from app.platform.permissions.catalog_sync import PermissionCatalogSyncService
from app.platform.permissions.codes import JobPermission
from app.platform.permissions.models import Permission, Role, RolePermission
from tests.jobs.test_jobs_persistence import JobsFixture
from tests.platform.test_company_administration import seed_admin_fixture

pytest_plugins = ("tests.jobs.test_jobs_persistence",)


def test_jobs_permission_catalog_contract_is_explicit_and_unique() -> None:
    permission_catalog.validate()
    assert {item.code for item in JOB_DEFINITIONS} == set(JobPermission.ALL)
    assert len({item.code for item in permission_catalog.definitions}) == len(
        permission_catalog.definitions
    )
    assert {
        item.code: (item.name, item.resource, item.action) for item in JOB_DEFINITIONS
    } == {
        JobPermission.READ: ("Company Job Read", "job", "read"),
        JobPermission.MANAGE: ("Company Job Manage", "job", "manage"),
        JobPermission.EXECUTE: ("Company Job Execute", "job", "execute"),
    }


@pytest.mark.asyncio
async def test_jobs_permission_catalog_sync_is_idempotent_and_grant_free(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, _ = jobs_database
    async with factory() as session:
        before_roles = await session.scalar(select(func.count()).select_from(Role))
        before_memberships = await session.scalar(
            select(func.count()).select_from(Membership)
        )
        before_grants = await session.scalar(
            select(func.count()).select_from(RolePermission)
        )
    async with factory() as session:
        first = await PermissionCatalogSyncService().synchronize(session)
        ids = {
            item.code: item.id
            for item in (*first.created, *first.existing)
            if item.code in JobPermission.ALL
        }
        second = await PermissionCatalogSyncService().synchronize(session)
    async with factory() as session:
        records = tuple(
            (
                await session.scalars(
                    select(Permission)
                    .where(Permission.code.in_(JobPermission.ALL))
                    .order_by(Permission.code)
                )
            ).all()
        )
        assert len(records) == 3
        assert {record.code: record.id for record in records} == ids
        assert JobPermission.ALL.issubset(second.existing_codes)
        assert not JobPermission.ALL.intersection(second.created_codes)
        assert (
            await session.scalar(select(func.count()).select_from(Role)) == before_roles
        )
        assert (
            await session.scalar(select(func.count()).select_from(Membership))
            == before_memberships
        )
        assert (
            await session.scalar(select(func.count()).select_from(RolePermission))
            == before_grants
        )


@pytest.mark.asyncio
async def test_company_administration_assigns_each_jobs_permission_and_conceals_cross_company_role(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, _ = jobs_database
    fixture = await seed_admin_fixture(factory, "JOBSPERMISSION")
    async with factory() as session:
        await PermissionCatalogSyncService().synchronize(session)
    async with factory() as session:
        permissions = tuple(
            (
                await session.scalars(
                    select(Permission)
                    .where(Permission.code.in_(JobPermission.ALL))
                    .order_by(Permission.code)
                )
            ).all()
        )
    service = CompanyAdministrationService()
    for permission in permissions:
        async with factory() as session:
            assignment = await service.assign_permission(
                session,
                context=fixture.context,
                role_id=fixture.company_role_id,
                permission_id=permission.id,
            )
            assert assignment.permission_id == permission.id
    async with factory() as session:
        with pytest.raises(AccessPolicyNotFoundError):
            await service.assign_permission(
                session,
                context=fixture.context,
                role_id=fixture.other_role_id,
                permission_id=permissions[0].id,
            )
