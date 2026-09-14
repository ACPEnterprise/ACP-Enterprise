from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.customer_migration.models import CustomerSourceIdentity
from app.customers.models import Customer
from app.operational_migration.hcp_current_overlay import (
    OverlayAssertion,
    OverlayRecord,
)
from app.operational_migration.hcp_current_overlay_lineage import (
    CurrentOverlayLineageBootstrap,
)
from app.operational_migration.hcp_source4_native_binding import (
    BindingDisposition,
    HcpSource4NativeBindingBootstrap,
)
from app.operational_migration.models import HcpSource4NativeBindingEvidence
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.tests.operational_migration.test_hcp_current_overlay_lineage import (
    _bootstrap,
    _manifest,
    _scope,
)


@pytest_asyncio.fixture
async def binding_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_async_engine(settings.database_url)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _lineage_and_legacy(factory: async_sessionmaker[AsyncSession]):
    company, branch, user = await _scope(factory)
    lineage: CurrentOverlayLineageBootstrap = _bootstrap(
        company, branch, user, _manifest(company, branch)
    )
    source_id = f"cus_{uuid4().hex}"
    record = OverlayRecord(
        "customer",
        source_id,
        OverlayAssertion.UPDATE,
        "d" * 64,
        "2026-09-12T17:00:00+00:00",
        {},
        prior_source_digest="c" * 64,
    )
    async with factory() as session, session.begin():
        await lineage.establish(session)
        assert lineage.customer_run is not None
        customer = Customer(
            company_id=company.id,
            customer_number=f"CUS-{uuid4().int % 900000 + 100000}",
            status="active",
            customer_type="residential",
            display_name="Exact Legacy Successor",
            normalized_name="exact legacy successor",
            preferred_contact_method="phone",
        )
        session.add(customer)
        await session.flush()
        legacy = CustomerSourceIdentity(
            company_id=company.id,
            branch_id=branch.id,
            customer_id=customer.id,
            source_system="housecall_pro",
            source_customer_id=source_id,
            first_run_id=lineage.customer_run.id,
        )
        session.add(legacy)
        await session.flush()
    assert lineage.customer_run is not None and lineage.operational_run is not None
    service = HcpSource4NativeBindingBootstrap(
        company_id=company.id,
        branch_id=branch.id,
        master_run_id=lineage.binding.master_run_id,
        customer_run_id=lineage.customer_run.id,
        operational_run_id=lineage.operational_run.id,
        package_digest=lineage.binding.base_source4_digest,
    )
    return company, branch, lineage, customer, legacy, record, service


@pytest.mark.asyncio
async def test_provable_binding_and_exact_replay(
    binding_database: async_sessionmaker[AsyncSession],
) -> None:
    company, _, _, customer, legacy, record, service = await _lineage_and_legacy(
        binding_database
    )
    async with binding_database() as session, session.begin():
        inventory = await service.inventory(session, (record,))
        assert inventory == {
            "customer": {BindingDisposition.PROVABLE_NATIVE_SUCCESSOR_BINDING: 1}
        }
        await service.bind_for_update(session, record)
    async with binding_database() as session:
        identity = await session.scalar(
            select(CustomerSourceIdentity).where(
                CustomerSourceIdentity.company_id == company.id,
                CustomerSourceIdentity.source_system == "housecall_pro_source4",
                CustomerSourceIdentity.source_customer_id == record.source_id,
            )
        )
        assert identity is not None and identity.customer_id == customer.id
        evidence = await session.scalar(
            select(HcpSource4NativeBindingEvidence).where(
                HcpSource4NativeBindingEvidence.source4_source_id == record.source_id
            )
        )
        assert evidence is not None and evidence.legacy_source_identity_id == legacy.id
    replay = HcpSource4NativeBindingBootstrap(
        company_id=service.company_id,
        branch_id=service.branch_id,
        master_run_id=service.master_run_id,
        customer_run_id=service.customer_run_id,
        operational_run_id=service.operational_run_id,
        package_digest=service.package_digest,
    )
    async with binding_database() as session, session.begin():
        assert await replay.inventory(session, (record,)) == {
            "customer": {BindingDisposition.BINDING_ALREADY_PRESENT: 1}
        }
    async with binding_database() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerSourceIdentity)
                .where(
                    CustomerSourceIdentity.company_id == company.id,
                    CustomerSourceIdentity.source_system == "housecall_pro_source4",
                    CustomerSourceIdentity.source_customer_id == record.source_id,
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_missing_and_conflicting_successors_fail_closed(
    binding_database: async_sessionmaker[AsyncSession],
) -> None:
    company, branch, lineage, _, _, record, service = await _lineage_and_legacy(
        binding_database
    )
    missing = OverlayRecord(
        "customer",
        f"cus_{uuid4().hex}",
        OverlayAssertion.UPDATE,
        "d" * 64,
        record.acquired_at,
        {},
        prior_source_digest="c" * 64,
    )
    async with binding_database() as session:
        with pytest.raises(ValueError, match="NATIVE_SUCCESSOR_MISSING"):
            await service.inventory(session, (missing,))
    assert lineage.customer_run is not None
    async with binding_database() as session, session.begin():
        other = Customer(
            company_id=company.id,
            customer_number=f"CUS-{uuid4().int % 900000 + 100000}",
            status="active",
            customer_type="residential",
            display_name="Conflict",
            normalized_name="conflict",
            preferred_contact_method="phone",
        )
        session.add(other)
        await session.flush()
        session.add(
            CustomerSourceIdentity(
                company_id=company.id,
                branch_id=branch.id,
                customer_id=other.id,
                source_system="housecall_pro_source4",
                source_customer_id=record.source_id,
                first_run_id=lineage.customer_run.id,
            )
        )
    conflict = HcpSource4NativeBindingBootstrap(
        company_id=service.company_id,
        branch_id=service.branch_id,
        master_run_id=service.master_run_id,
        customer_run_id=service.customer_run_id,
        operational_run_id=service.operational_run_id,
        package_digest=service.package_digest,
    )
    async with binding_database() as session:
        with pytest.raises(ValueError, match="CONFLICTING_BINDING"):
            await conflict.inventory(session, (record,))


@pytest.mark.asyncio
async def test_binding_rolls_back_with_downstream_failure(
    binding_database: async_sessionmaker[AsyncSession],
) -> None:
    company, _, _, _, _, record, service = await _lineage_and_legacy(binding_database)
    with pytest.raises(RuntimeError, match="downstream"):
        async with binding_database() as session, session.begin():
            await service.inventory(session, (record,))
            await service.bind_for_update(session, record)
            raise RuntimeError("downstream overlay failure")
    async with binding_database() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerSourceIdentity)
                .where(
                    CustomerSourceIdentity.company_id == company.id,
                    CustomerSourceIdentity.source_system == "housecall_pro_source4",
                    CustomerSourceIdentity.source_customer_id == record.source_id,
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HcpSource4NativeBindingEvidence)
                .where(
                    HcpSource4NativeBindingEvidence.source4_source_id
                    == record.source_id
                )
            )
            == 0
        )
