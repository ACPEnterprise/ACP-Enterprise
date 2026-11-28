import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.core.config import settings
from app.demo.models import DemoEnvironment, DemoScenario
from app.demo.service import (
    DEMO_PERMISSION_CODES,
    PRESERVED_DEMO_COMPANY_ID,
    SalesDemoService,
)
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.onboarding.service import OnboardingConflictError
from app.platform.permissions.catalog_sync import permission_catalog_sync_service
from app.platform.permissions.codes import (
    AccountsPayablePermission,
    AdministrationPermission,
    PaymentPermission,
)
from app.platform.permissions.models import Permission, Role, RolePermission
from app.platform.users.models import User, UserCredential
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def configuration(**changes: object):
    values = {
        "environment": "test",
        "sales_demo_enabled": True,
        "qbo_production_enabled": False,
        "communications_delivery_enabled": False,
        "identity_outbox_worker_enabled": False,
        "google_ads_live_access_enabled": False,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def context(user_id):
    return SimpleNamespace(user=SimpleNamespace(id=user_id))


@pytest.mark.parametrize(
    "change",
    [
        {"environment": "production"},
        {"sales_demo_enabled": False},
        {"qbo_production_enabled": True},
        {"communications_delivery_enabled": True},
        {"identity_outbox_worker_enabled": True},
        {"google_ads_live_access_enabled": True},
    ],
)
def test_demo_provisioning_fails_closed_for_unsafe_runtime(change):
    with pytest.raises(Exception, match="Sales Demo"):
        SalesDemoService(configuration=configuration(**change))._guard()


def test_sales_demo_profile_excludes_real_money_payroll_tax_and_administration():
    forbidden = {
        AdministrationPermission.COMPANY_ADMINISTER,
        PaymentPermission.REFUND,
        PaymentPermission.DEPOSIT_MANAGE,
        PaymentPermission.RECONCILE,
        PaymentPermission.FINANCE_APPROVE,
        AccountsPayablePermission.DISBURSEMENT_RECORD,
    }
    assert DEMO_PERMISSION_CODES.isdisjoint(forbidden)
    assert not any("PAYROLL" in code or "TAX" in code for code in DEMO_PERMISSION_CODES)


@pytest.mark.asyncio
async def test_per_rep_tenant_seed_reset_isolation_and_scenarios():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = SalesDemoService(configuration=configuration())
    async with factory() as session:
        await permission_catalog_sync_service.synchronize(session)

    user_ids = (uuid4(), uuid4())
    async with factory() as session:
        session.add_all(
            [
                User(
                    id=user_id,
                    normalized_email=f"demo-rep-{user_id}@example.invalid",
                    first_name="Demo",
                    last_name="Representative",
                    display_name="Demo Representative",
                    status="active",
                    authorization_version=1,
                )
                for user_id in user_ids
            ]
        )
        await session.commit()

    async with factory() as session:
        first = await service.provision(session, context=context(user_ids[0]))
        await session.commit()
    assert first.counts == {
        "customers": 18,
        "locations": 21,
        "employees": 8,
        "jobs": 12,
        "estimates": 6,
        "invoices": 5,
        "price_book_items": 14,
        "inventory_items": 8,
        "accounting_periods": 3,
    }

    async with factory() as session:
        reused = await service.provision(session, context=context(user_ids[0]))
        second_rep = await service.provision(session, context=context(user_ids[1]))
        await session.commit()
    assert reused.action == "reused" and reused.company_id == first.company_id
    assert second_rep.company_id != first.company_id

    async with factory() as session:
        reset = await service.provision(
            session, context=context(user_ids[0]), reset=True
        )
        await session.commit()
    assert reset.generation == 2 and reset.company_id != first.company_id
    assert reset.counts == first.counts

    async with factory() as session:
        environment = await session.scalar(
            select(DemoEnvironment).where(DemoEnvironment.owner_user_id == user_ids[0])
        )
        old_company = await session.get(Company, first.company_id)
        scenarios = (
            await session.scalars(
                select(DemoScenario)
                .where(DemoScenario.company_id == reset.company_id)
                .order_by(DemoScenario.position)
            )
        ).all()
        role = await session.scalar(
            select(Role).where(
                Role.company_id == reset.company_id, Role.code == "SALES_DEMO"
            )
        )
        granted = set(
            (
                await session.scalars(
                    select(Permission.code)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .where(RolePermission.role_id == role.id)
                )
            ).all()
        )
    assert environment.active_company_id == reset.company_id
    assert old_company.status == "inactive"
    assert [item.position for item in scenarios] == list(range(1, 9))
    assert all(item.condition and item.record_refs is not None for item in scenarios)
    scenarios_by_code = {item.code: item for item in scenarios}
    assert scenarios_by_code["water_heater_estimate"].record_refs["estimate_id"]
    assert scenarios_by_code["overdue_ar"].record_refs["invoice_id"]
    assert scenarios_by_code["margin_problem"].record_refs["job_id"]
    assert granted == DEMO_PERMISSION_CODES

    burst_user_id = uuid4()
    async with factory() as session:
        session.add(
            User(
                id=burst_user_id,
                normalized_email=f"demo-rep-{burst_user_id}@example.invalid",
                first_name="Burst",
                last_name="Representative",
                display_name="Burst Representative",
                status="active",
                authorization_version=1,
            )
        )
        await session.commit()

    async def concurrent_provision():
        async with factory() as session:
            result = await service.provision(session, context=context(burst_user_id))
            await session.commit()
            return result

    left, right = await asyncio.gather(concurrent_provision(), concurrent_provision())
    assert left.company_id == right.company_id
    assert {left.action, right.action} == {"created", "reused"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_preserved_demo_restoration_keeps_credential_and_refuses_real_access():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = SalesDemoService(configuration=configuration())
    owner_id = uuid4()
    password_hash = "$argon2id$synthetic-preserved-hash"
    async with factory() as session:
        await permission_catalog_sync_service.synchronize(session)
        session.add(
            User(
                id=owner_id,
                normalized_email=f"preserved-demo-{owner_id}@example.invalid",
                first_name="Demo",
                last_name="Representative",
                display_name="Demo Representative",
                status="active",
                authorization_version=1,
            )
        )
        session.add(
            UserCredential(
                user_id=owner_id,
                password_hash=password_hash,
                credential_version=7,
            )
        )
        await session.commit()

    async with factory() as session:
        restored = await service.restore_preserved_company(
            session, context=context(owner_id)
        )
        await session.commit()
    assert restored.action == "restored"
    assert restored.company_id == PRESERVED_DEMO_COMPANY_ID

    async with factory() as session:
        credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == owner_id)
        )
        memberships = (
            await session.scalars(
                select(Membership).where(Membership.user_id == owner_id)
            )
        ).all()
        replay = await service.restore_preserved_company(
            session, context=context(owner_id)
        )
        await session.commit()
    assert credential.password_hash == password_hash
    assert credential.credential_version == 7
    assert replay.action == "reused"
    assert [(row.company_id, row.status) for row in memberships] == [
        (PRESERVED_DEMO_COMPANY_ID, "active")
    ]

    real_company_id, real_branch_id = uuid4(), uuid4()
    async with factory() as session:
        session.add(
            Company(
                id=real_company_id,
                name="Real Company Boundary",
                code=f"REAL_{real_company_id.hex[:8]}",
                status="active",
                timezone="America/New_York",
            )
        )
        session.add(
            Branch(
                id=real_branch_id,
                company_id=real_company_id,
                name="Real Branch",
                code="REAL",
                status="active",
                timezone="America/New_York",
                is_primary=True,
            )
        )
        await session.flush()
        session.add(
            Membership(
                user_id=owner_id,
                company_id=real_company_id,
                status="active",
                default_branch_id=real_branch_id,
                has_all_branch_access=True,
            )
        )
        await session.commit()

    async with factory() as session:
        with pytest.raises(OnboardingConflictError, match="non-Demo company access"):
            await service.restore_preserved_company(
                session, context=context(owner_id)
            )
        await session.rollback()
    await engine.dispose()
