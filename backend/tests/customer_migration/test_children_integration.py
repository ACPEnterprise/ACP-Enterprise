import csv
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

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
from app.customer_migration.children import (
    HousecallProCustomerChildrenMigration,
    MigrationProgress,
)
from app.customer_migration.housecall_pro import HousecallProCustomerMigration
from app.customer_migration.models import (
    CustomerContactSourceIdentity,
    CustomerMigrationProgress,
    CustomerMigrationRun,
    ServiceLocationSourceIdentity,
)
from app.customers.models import Customer, CustomerContact, ServiceLocation
from app.customers.schemas import ContactCreate
from app.customers.service import CustomerService
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User


@pytest_asyncio.fixture
async def migration_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


async def seed_context(
    factory: async_sessionmaker[AsyncSession],
) -> AuthorizationContext:
    suffix = uuid4().hex[:8]
    async with factory() as session, session.begin():
        user = User(
            normalized_email=f"phase2-{suffix}@example.test",
            first_name="Migration",
            last_name="Operator",
            display_name="Migration Operator",
            status="active",
        )
        company = Company(
            name="Phase 2 Synthetic Company",
            code=f"P2{suffix}".upper(),
            status="active",
            timezone="America/New_York",
        )
        session.add_all([user, company])
        await session.flush()
        branch = Branch(
            company_id=company.id,
            name="Phase 2 Branch",
            code="PHASE2",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        session.add(branch)
        await session.flush()
        membership = Membership(
            user_id=user.id,
            company_id=company.id,
            status="active",
            default_branch_id=branch.id,
            has_all_branch_access=True,
        )
        session.add(membership)
        await session.flush()
    return AuthorizationContext(
        user=user,
        company=company,
        membership=membership,
        authorized_branches=(branch,),
        active_branch=branch,
        effective_roles=(),
        effective_permissions=(),
        credential_version=1,
        authorization_version=1,
    )


def write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


async def seed_parent(
    factory: async_sessionmaker[AsyncSession],
    *,
    context: AuthorizationContext,
    path: Path,
) -> None:
    write_csv(
        path,
        ["Customer ID", "Display Name", "Type"],
        [["parent-1", "Phase 2 Synthetic Customer", "homeowner"]],
    )
    report = await HousecallProCustomerMigration().run(
        factory, context=context, source_path=path, dry_run=False
    )
    assert report.accepted == 1


def write_children(contacts: Path, locations: Path) -> None:
    write_csv(
        contacts,
        [
            "Contact ID",
            "Customer ID",
            "First Name",
            "Last Name",
            "Email",
        ],
        [
            ["contact-1", "parent-1", "Synthetic", "Primary", "one@example.test"],
            ["contact-2", "parent-1", "Synthetic", "Secondary", "two@example.test"],
            ["contact-2", "parent-1", "Synthetic", "Repeated", "three@example.test"],
            ["contact-3", "missing-parent", "Synthetic", "Orphan", ""],
            ["contact-4", "parent-1", "Synthetic", "", ""],
            ["contact-5", "parent-1", "Synthetic", "Primary", "one@example.test"],
        ],
    )
    write_csv(
        locations,
        [
            "Service Location ID",
            "Customer ID",
            "Address",
            "City",
            "State",
            "Postal Code",
        ],
        [
            ["location-1", "parent-1", "201 Test Ave", "Testville", "FL", "33755"],
            ["location-2", "parent-1", "202 Test Ave", "Testville", "FL", "33756"],
            ["location-2", "parent-1", "203 Test Ave", "Testville", "FL", "33757"],
            [
                "location-3",
                "missing-parent",
                "204 Test Ave",
                "Testville",
                "FL",
                "33758",
            ],
            ["location-4", "parent-1", "205 Test Ave", "", "FL", "33759"],
            ["location-5", "parent-1", "201 Test Ave", "Testville", "FL", "33755"],
        ],
    )


class FailingCustomerService(CustomerService):
    async def stage_migrated_contact(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
        data: ContactCreate,
    ) -> CustomerContact:
        await super().stage_migrated_contact(
            session,
            context=context,
            customer_id=customer_id,
            data=data,
        )
        raise RuntimeError("synthetic transaction failure")


@pytest.mark.asyncio
async def test_child_dry_run_import_rerun_and_progress_reconcile(
    migration_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, factory = migration_database
    context = await seed_context(factory)
    await seed_parent(factory, context=context, path=tmp_path / "customers.csv")
    contacts = tmp_path / "contacts.csv"
    locations = tmp_path / "locations.csv"
    write_children(contacts, locations)
    updates: list[MigrationProgress] = []
    migration = HousecallProCustomerChildrenMigration()

    dry_run = await migration.run(
        factory,
        context=context,
        contacts_path=contacts,
        service_locations_path=locations,
        dry_run=True,
        progress_callback=updates.append,
    )
    assert dry_run.as_dict() | {"run_id": None} == {
        "run_id": None,
        "mode": "dry_run",
        "source": 12,
        "accepted": 4,
        "rejected": 2,
        "duplicate": 4,
        "unresolved": 2,
    }
    assert len(updates) == 12
    assert updates[-1].entity_type == "service_location"
    assert updates[-1].processed == 6
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerContact)
                .join(Customer, Customer.id == CustomerContact.customer_id)
                .where(Customer.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ServiceLocation)
                .join(Customer, Customer.id == ServiceLocation.customer_id)
                .where(Customer.company_id == context.company.id)
            )
            == 0
        )

    imported = await migration.run(
        factory,
        context=context,
        contacts_path=contacts,
        service_locations_path=locations,
        dry_run=False,
    )
    assert (imported.source, imported.accepted, imported.rejected) == (12, 4, 2)
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerContactSourceIdentity)
                .where(CustomerContactSourceIdentity.company_id == context.company.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ServiceLocationSourceIdentity)
                .where(ServiceLocationSourceIdentity.company_id == context.company.id)
            )
            == 2
        )
        snapshots = list(
            (
                await session.scalars(
                    select(CustomerMigrationProgress).where(
                        CustomerMigrationProgress.run_id == UUID(imported.run_id)
                    )
                )
            ).all()
        )
        assert len(snapshots) == 2
        assert all(
            snapshot.processed_count == snapshot.source_count == 6
            for snapshot in snapshots
        )

    rerun = await migration.run(
        factory,
        context=context,
        contacts_path=contacts,
        service_locations_path=locations,
        dry_run=False,
    )
    assert rerun.as_dict() | {"run_id": None} == {
        "run_id": None,
        "mode": "import",
        "source": 12,
        "accepted": 0,
        "rejected": 2,
        "duplicate": 8,
        "unresolved": 2,
    }


@pytest.mark.asyncio
async def test_child_and_identity_roll_back_together_on_failure(
    migration_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, factory = migration_database
    context = await seed_context(factory)
    await seed_parent(factory, context=context, path=tmp_path / "customers.csv")
    contacts = tmp_path / "contacts.csv"
    locations = tmp_path / "locations.csv"
    write_csv(
        contacts,
        ["Contact ID", "Customer ID", "First Name", "Last Name"],
        [["atomic-contact", "parent-1", "Synthetic", "Atomic"]],
    )
    write_csv(
        locations,
        [
            "Service Location ID",
            "Customer ID",
            "Address",
            "City",
            "State",
            "Postal Code",
        ],
        [],
    )

    migration = HousecallProCustomerChildrenMigration(FailingCustomerService())
    with pytest.raises(RuntimeError, match="synthetic transaction failure"):
        await migration.run(
            factory,
            context=context,
            contacts_path=contacts,
            service_locations_path=locations,
            dry_run=False,
        )

    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerContact)
                .join(Customer, Customer.id == CustomerContact.customer_id)
                .where(Customer.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerContactSourceIdentity)
                .where(CustomerContactSourceIdentity.company_id == context.company.id)
            )
            == 0
        )
        failed_run = await session.scalar(
            select(CustomerMigrationRun)
            .where(CustomerMigrationRun.mode == "import")
            .order_by(CustomerMigrationRun.started_at.desc())
        )
        assert failed_run is not None
        assert failed_run.status == "failed"
        assert failed_run.source_count == 0
