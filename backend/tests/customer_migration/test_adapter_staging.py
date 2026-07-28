import csv
import hashlib
import io
from collections.abc import AsyncIterator
from uuid import uuid4

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
from app.customer_migration.housecall_pro_adapter import (
    HOUSECALL_PRO_CUSTOMER_EXPORT_CONTRACTS,
)
from app.customer_migration.models import (
    CustomerMigrationCandidate,
    CustomerMigrationChildException,
    CustomerMigrationEvidence,
    CustomerMigrationRun,
    CustomerMigrationSourceArtifact,
    CustomerMigrationSourceRow,
    CustomerMigrationStagingRun,
)
from app.customer_migration.repository import CustomerMigrationStagingRepository
from app.customer_migration.staging import (
    CustomerAdapterDryRunService,
    CustomerDryRunReadinessError,
)
from app.customers.models import Customer, CustomerContact, ServiceLocation
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User


@pytest_asyncio.fixture
async def staging_database() -> AsyncIterator[
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
            normalized_email=f"adapter-staging-{suffix}@example.test",
            first_name="Synthetic",
            last_name="Operator",
            display_name="Synthetic Operator",
            status="active",
        )
        company = Company(
            name="Synthetic Adapter Staging Company",
            code=f"AS{suffix}".upper(),
            status="active",
            timezone="America/New_York",
        )
        session.add_all([user, company])
        await session.flush()
        branch = Branch(
            company_id=company.id,
            name="Synthetic Adapter Staging Branch",
            code="ADAPTER",
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


def source_bytes(rows: list[dict[str, str]]) -> bytes:
    contract = HOUSECALL_PRO_CUSTOMER_EXPORT_CONTRACTS[1]
    headers = sorted(contract.headers, reverse=True)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow({header: row.get(header, "") for header in headers})
    return output.getvalue().encode()


def accepted_row() -> dict[str, str]:
    return {
        "ID": "synthetic-source-1",
        "Customer Type": "homeowner",
        "Display Name": "Synthetic Candidate",
        "First Name": "Synthetic",
        "Last Name": "Candidate",
        "Tags": "synthetic-unmapped-tag",
        "Address_2 Street Line 1": "2 Synthetic Way",
        "Address_2 City": "Example",
        "Address_2 State": "EX",
        "Address_2 Postal Code": "00002",
        "Address_3 Street Line 1": "3 Synthetic Way",
        "Address_3 City": "Example",
        "Address_3 State": "EX",
        "Address_3 Postal Code": "00003",
        "Address_3 Billing?": "true",
        "Address_4 Street Line 1": "4 Synthetic Way",
        "Address_4 State": "EX",
    }


@pytest.mark.asyncio
async def test_dry_run_persists_candidates_evidence_and_exact_reconciliation(
    staging_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = staging_database
    context = await seed_context(factory)
    accepted = accepted_row()
    rejected = {
        "ID": "synthetic-source-2",
        "Customer Type": "unsupported",
        "Display Name": "Rejected Synthetic Candidate",
    }
    raw = source_bytes([accepted, accepted, rejected])
    checksum = hashlib.sha256(raw).hexdigest()

    first = await CustomerAdapterDryRunService().run(
        factory,
        context=context,
        source_bytes=raw,
        expected_source_sha256=checksum,
    )

    assert first.as_dict() | {"run_id": None, "artifact_id": None} == {
        "run_id": None,
        "artifact_id": None,
        "schema_version": "housecall_pro_customer_451_v1",
        "reused_staging": False,
        "rows_discovered": 3,
        "rows_accepted": 1,
        "rows_rejected": 1,
        "customers_proposed": 1,
        "contacts_proposed": 1,
        "service_locations_proposed": 1,
        "billing_addresses_proposed": 1,
        "child_exceptions": 1,
        "duplicate_identities": 1,
        "unmapped_fields": 1,
    }
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationSourceArtifact)
                .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationSourceRow)
                .join(CustomerMigrationSourceArtifact)
                .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            )
            == 3
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationCandidate)
                .join(CustomerMigrationSourceRow)
                .join(CustomerMigrationSourceArtifact)
                .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            )
            == 4
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationEvidence)
                .join(CustomerMigrationSourceRow)
                .join(CustomerMigrationSourceArtifact)
                .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationChildException)
                .join(CustomerMigrationSourceRow)
                .join(CustomerMigrationSourceArtifact)
                .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationStagingRun)
                .join(CustomerMigrationRun)
                .where(CustomerMigrationRun.company_id == context.company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.company_id == context.company.id)
            )
            == 0
        )
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

    second = await CustomerAdapterDryRunService().run(
        factory,
        context=context,
        source_bytes=raw,
        expected_source_sha256=checksum,
    )

    assert second.reused_staging is True
    assert second.artifact_id == first.artifact_id
    assert second.run_id != first.run_id
    assert (
        second.as_dict()
        | {
            "run_id": first.run_id,
            "reused_staging": False,
        }
        == first.as_dict()
    )
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationSourceArtifact)
                .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationSourceRow)
                .join(CustomerMigrationSourceArtifact)
                .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            )
            == 3
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationCandidate)
                .join(CustomerMigrationSourceRow)
                .join(CustomerMigrationSourceArtifact)
                .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            )
            == 4
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationEvidence)
                .join(CustomerMigrationSourceRow)
                .join(CustomerMigrationSourceArtifact)
                .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationRun)
                .where(CustomerMigrationRun.company_id == context.company.id)
            )
            == 2
        )


class FailingRepository(CustomerMigrationStagingRepository):
    @staticmethod
    def add_candidate(
        session: AsyncSession, candidate: CustomerMigrationCandidate
    ) -> None:
        CustomerMigrationStagingRepository.add_candidate(session, candidate)
        raise RuntimeError("synthetic staging failure")


@pytest.mark.asyncio
async def test_staging_failure_rolls_back_artifact_rows_and_candidates(
    staging_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = staging_database
    context = await seed_context(factory)
    raw = source_bytes([accepted_row()])

    with pytest.raises(RuntimeError, match="synthetic staging failure"):
        await CustomerAdapterDryRunService(repository=FailingRepository()).run(
            factory,
            context=context,
            source_bytes=raw,
            expected_source_sha256=hashlib.sha256(raw).hexdigest(),
        )

    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationSourceArtifact)
                .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationSourceRow)
                .join(CustomerMigrationSourceArtifact)
                .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationCandidate)
                .join(CustomerMigrationSourceRow)
                .join(CustomerMigrationSourceArtifact)
                .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationRun)
                .where(CustomerMigrationRun.company_id == context.company.id)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_checksum_or_schema_failure_is_not_persisted(
    staging_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = staging_database
    context = await seed_context(factory)
    raw = source_bytes([accepted_row()])

    with pytest.raises(CustomerDryRunReadinessError, match="failed closed"):
        await CustomerAdapterDryRunService().run(
            factory,
            context=context,
            source_bytes=raw,
            expected_source_sha256="0" * 64,
        )

    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationSourceArtifact)
                .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            )
            == 0
        )
