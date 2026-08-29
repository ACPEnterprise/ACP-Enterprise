import hashlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
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
from app.customer_migration.adapter_import import (
    BOUNDARY_VERSION,
    ApprovedCustomerImportBoundary,
    CustomerAdapterImportError,
    CustomerAdapterImportService,
    ExpectedCustomerImportCounts,
    review_adapter_output,
)
from app.customer_migration.adapter_import_policy import customer_adapter_import_policy
from app.customer_migration.models import (
    CustomerMigrationCandidate,
    CustomerMigrationException,
    CustomerMigrationProgress,
    CustomerMigrationRun,
    CustomerMigrationSourceArtifact,
    CustomerMigrationSourceRow,
    CustomerSourceIdentity,
)
from app.customers.models import (
    Customer,
    CustomerBillingAddress,
    CustomerContact,
    ServiceLocation,
)
from app.customers.schemas import (
    ContactCreate,
    CustomerCreate,
    CustomerStatus,
    CustomerType,
    ServiceLocationCreate,
)
from app.customers.service import CustomerService
from app.events.models import BusinessEvent
from app.platform.audit.models import AuditRecord
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class MockRecord:
    row_number: int
    source_id: str
    schema_version: str
    source_row_sha256: str
    customer: CustomerCreate
    contact: ContactCreate | None
    service_locations: tuple[ServiceLocationCreate, ...]
    billing_address: ServiceLocationCreate | None


@dataclass(frozen=True)
class MockRejection:
    disposition: str
    source_id_sha256: str | None


@dataclass(frozen=True)
class MockChildException:
    source_id_sha256: str


@dataclass(frozen=True)
class MockOutput:
    source_sha256: str
    schema_version: str | None
    transformation_sha256: str
    source: int
    accepted: int
    rejected: int
    duplicate: int
    records: tuple[MockRecord, ...]
    rejections: tuple[MockRejection, ...] = ()
    child_exceptions: tuple[MockChildException, ...] = ()


@pytest_asyncio.fixture
async def database() -> AsyncIterator[
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
            normalized_email=f"adapter-import-{suffix}@example.test",
            first_name="Synthetic",
            last_name="Owner",
            display_name="Synthetic Owner",
            status="active",
        )
        company = Company(
            name="Synthetic Adapter Import Company",
            code=f"AI{suffix}".upper(),
            status="active",
            timezone="America/New_York",
        )
        session.add_all([user, company])
        await session.flush()
        branch = Branch(
            company_id=company.id,
            name="Synthetic Adapter Import Branch",
            code="IMPORT",
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


def mock_output(count: int = 2) -> MockOutput:
    records = tuple(
        MockRecord(
            row_number=index + 2,
            source_id=f"synthetic-source-{index}",
            schema_version="synthetic-customer-v1",
            source_row_sha256=digest(f"synthetic-row-{index}"),
            customer=CustomerCreate(
                customer_type=CustomerType.RESIDENTIAL,
                display_name=f"Synthetic Customer {index}",
                status=CustomerStatus.ACTIVE,
            ),
            contact=(
                ContactCreate(
                    first_name="Synthetic",
                    last_name=f"Contact{index}",
                    email=f"contact-{index}@example.test",
                    is_preferred=True,
                )
                if index == 0
                else None
            ),
            service_locations=(
                ServiceLocationCreate(
                    address=f"{index + 1} Synthetic Way",
                    city="Example",
                    state="EX",
                    postal_code=f"0000{index}",
                    country="US",
                ),
            ),
            billing_address=(
                ServiceLocationCreate(
                    address=f"{index + 10} Synthetic Billing Way",
                    city="Example",
                    state="EX",
                    postal_code=f"1000{index}",
                    country="US",
                )
                if index == 0
                else None
            ),
        )
        for index in range(count)
    )
    return MockOutput(
        source_sha256=digest("synthetic-artifact"),
        schema_version="synthetic-customer-v1",
        transformation_sha256=digest("synthetic-transformation"),
        source=count,
        accepted=count,
        rejected=0,
        duplicate=0,
        records=records,
    )


def boundary(reviewed, *, identities=None, source_sha=None, schema=None):
    approved = tuple(
        identities
        or [aggregate.source_identity_sha256 for aggregate in reviewed.aggregates]
    )
    selected = tuple(
        item for item in reviewed.aggregates if item.source_identity_sha256 in approved
    )
    counts = customer_adapter_import_policy.expected_counts(selected)
    return ApprovedCustomerImportBoundary(
        boundary_version=BOUNDARY_VERSION,
        source_sha256=source_sha or reviewed.source_sha256,
        schema_version=schema or reviewed.schema_version,
        pilot_boundary_sha256=digest(json.dumps(approved, separators=(",", ":"))),
        approved_source_identities=approved,
        expected=ExpectedCustomerImportCounts(
            customers=counts.customers,
            contacts=counts.contacts,
            service_locations=counts.service_locations,
            billing_addresses=counts.billing_addresses,
            business_events=counts.business_events,
        ),
    )


async def stage_reviewed(
    factory: async_sessionmaker[AsyncSession],
    context: AuthorizationContext,
    reviewed,
) -> None:
    assert context.active_branch is not None
    async with factory() as session, session.begin():
        artifact = CustomerMigrationSourceArtifact(
            company_id=context.company.id,
            branch_id=context.active_branch.id,
            source_system=reviewed.source_system,
            source_sha256=reviewed.source_sha256,
            schema_version=reviewed.schema_version,
            transformation_sha256=reviewed.transformation_sha256,
            byte_size=0,
            row_count=reviewed.source_count,
        )
        session.add(artifact)
        await session.flush()
        for aggregate in reviewed.aggregates:
            source_row = CustomerMigrationSourceRow(
                artifact_id=artifact.id,
                row_number=aggregate.row_number,
                source_identity=aggregate.source_identity,
                source_id_sha256=aggregate.source_identity_sha256,
                source_row_sha256=aggregate.source_row_sha256,
                disposition="accepted",
            )
            session.add(source_row)
            await session.flush()
            payloads = [("customer", 0, aggregate.customer)]
            if aggregate.contact is not None:
                payloads.append(("contact", 0, aggregate.contact))
            payloads.extend(
                ("service_location", ordinal, location)
                for ordinal, location in enumerate(aggregate.service_locations)
            )
            if aggregate.billing_address is not None:
                payloads.append(("billing_address", 0, aggregate.billing_address))
            for entity_type, ordinal, model in payloads:
                payload = model.model_dump(mode="json")
                session.add(
                    CustomerMigrationCandidate(
                        source_row_id=source_row.id,
                        entity_type=entity_type,
                        ordinal=ordinal,
                        payload_sha256=hashlib.sha256(
                            json.dumps(payload, sort_keys=True).encode()
                        ).hexdigest(),
                        payload=payload,
                    )
                )


@pytest.mark.asyncio
async def test_imports_reviewed_output_and_replays_idempotently(database) -> None:
    _, factory = database
    context = await seed_context(factory)
    reviewed = review_adapter_output(mock_output(), source_system="synthetic")
    await stage_reviewed(factory, context, reviewed)
    approved = boundary(reviewed)
    service = CustomerAdapterImportService()

    first = await service.run(
        factory, context=context, reviewed=reviewed, boundary=approved
    )
    second = await service.run(
        factory, context=context, reviewed=reviewed, boundary=approved
    )

    assert (first.accepted, first.duplicate, first.rejected) == (2, 0, 0)
    assert (second.accepted, second.duplicate, second.rejected) == (0, 2, 0)
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.company_id == context.company.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerContact)
                .join(Customer, Customer.id == CustomerContact.customer_id)
                .where(Customer.company_id == context.company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ServiceLocation)
                .join(Customer, Customer.id == ServiceLocation.customer_id)
                .where(Customer.company_id == context.company.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerBillingAddress)
                .join(Customer, Customer.id == CustomerBillingAddress.customer_id)
                .where(Customer.company_id == context.company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(BusinessEvent.company_id == context.company.id)
            )
            == 6
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditRecord)
                .where(AuditRecord.company_id == context.company.id)
            )
            == 4
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerSourceIdentity)
                .where(CustomerSourceIdentity.company_id == context.company.id)
            )
            == 2
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("source", "source checksum mismatch"),
        ("schema", "schema-version mismatch"),
        ("boundary", "pilot boundary digest mismatch"),
        ("allowlist", "absent from reviewed output"),
        ("counts", "approved count boundary mismatch"),
    ],
)
async def test_fails_closed_on_approved_boundary_mismatch(
    database, mutation: str, message: str
) -> None:
    _, factory = database
    context = await seed_context(factory)
    reviewed = review_adapter_output(mock_output(), source_system="synthetic")
    await stage_reviewed(factory, context, reviewed)
    approved = boundary(reviewed)
    if mutation == "source":
        approved = boundary(reviewed, source_sha="0" * 64)
    elif mutation == "schema":
        approved = boundary(reviewed, schema="other-schema")
    elif mutation == "boundary":
        approved = ApprovedCustomerImportBoundary(
            **{**approved.__dict__, "pilot_boundary_sha256": "0" * 64}
        )
    elif mutation == "allowlist":
        approved = boundary(reviewed, identities=("1" * 64,))
    else:
        approved = ApprovedCustomerImportBoundary(
            **{
                **approved.__dict__,
                "expected": ExpectedCustomerImportCounts(0, 0, 0, 0, 0),
            }
        )
    with pytest.raises(CustomerAdapterImportError, match=message):
        await CustomerAdapterImportService().run(
            factory, context=context, reviewed=reviewed, boundary=approved
        )
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationRun)
                .where(CustomerMigrationRun.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.company_id == context.company.id)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_similarity_and_child_exceptions_do_not_block_parent_admission(database) -> None:
    _, factory = database
    context = await seed_context(factory)
    raw = mock_output()
    duplicate_record = MockRecord(
        **{
            **raw.records[1].__dict__,
            "contact": ContactCreate(
                first_name="Other",
                last_name="Synthetic",
                email="contact-0@example.test",
            ),
        }
    )
    duplicate_output = MockOutput(
        **{**raw.__dict__, "records": (raw.records[0], duplicate_record)}
    )
    reviewed_duplicate = review_adapter_output(
        duplicate_output, source_system="synthetic"
    )
    await stage_reviewed(factory, context, reviewed_duplicate)
    duplicate_report = await CustomerAdapterImportService().run(
        factory,
        context=context,
        reviewed=reviewed_duplicate,
        boundary=boundary(reviewed_duplicate),
    )
    assert duplicate_report.accepted == 2

    child_output = MockOutput(
        **{
            **raw.__dict__,
            "child_exceptions": (MockChildException(digest(raw.records[0].source_id)),),
        }
    )
    reviewed_child = review_adapter_output(child_output, source_system="child")
    await stage_reviewed(factory, context, reviewed_child)
    child_report = await CustomerAdapterImportService().run(
        factory,
        context=context,
        reviewed=reviewed_child,
        boundary=boundary(reviewed_child),
    )
    assert child_report.accepted == 2


@pytest.mark.asyncio
async def test_rejects_tampered_review_and_staging_candidate(database) -> None:
    _, factory = database
    context = await seed_context(factory)
    reviewed = review_adapter_output(mock_output(), source_system="synthetic")
    await stage_reviewed(factory, context, reviewed)

    with pytest.raises(CustomerAdapterImportError, match="reviewed output digest"):
        await CustomerAdapterImportService().run(
            factory,
            context=context,
            reviewed=replace(reviewed, review_sha256="0" * 64),
            boundary=boundary(reviewed),
        )

    async with factory() as session, session.begin():
        candidate = await session.scalar(
            select(CustomerMigrationCandidate)
            .join(CustomerMigrationSourceRow)
            .join(CustomerMigrationSourceArtifact)
            .where(CustomerMigrationSourceArtifact.company_id == context.company.id)
            .limit(1)
        )
        assert candidate is not None
        candidate.payload_sha256 = "0" * 64
    with pytest.raises(CustomerAdapterImportError, match="staged candidates"):
        await CustomerAdapterImportService().run(
            factory,
            context=context,
            reviewed=reviewed,
            boundary=boundary(reviewed),
        )


@pytest.mark.asyncio
async def test_name_only_operational_match_does_not_merge_native_identity(database) -> None:
    _, factory = database
    context = await seed_context(factory)
    reviewed = review_adapter_output(mock_output(), source_system="synthetic")
    await stage_reviewed(factory, context, reviewed)
    async with factory() as session:
        await CustomerService().create_customer(
            session,
            context=context,
            data=reviewed.aggregates[0].customer,
        )

    report = await CustomerAdapterImportService().run(
        factory,
        context=context,
        reviewed=reviewed,
        boundary=boundary(reviewed),
    )
    assert report.accepted == 2

    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.company_id == context.company.id)
            )
            == 3
        )
        run = await session.scalar(
            select(CustomerMigrationRun)
            .where(CustomerMigrationRun.company_id == context.company.id)
            .order_by(CustomerMigrationRun.started_at.desc())
        )
        assert run is not None and run.status == "completed"
        assert (run.source_count, run.accepted_count, run.rejected_count) == (2, 2, 0)


class FailingSecondCustomerService(CustomerService):
    def __init__(self) -> None:
        self.calls = 0

    async def stage_migrated_customer(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("synthetic aggregate failure")
        return await super().stage_migrated_customer(*args, **kwargs)


@pytest.mark.asyncio
async def test_uses_one_transaction_per_aggregate_and_preserves_failure(
    database,
) -> None:
    _, factory = database
    context = await seed_context(factory)
    reviewed = review_adapter_output(mock_output(), source_system="synthetic")
    await stage_reviewed(factory, context, reviewed)
    service = CustomerAdapterImportService(
        customer_service=FailingSecondCustomerService()
    )

    with pytest.raises(
        CustomerAdapterImportError, match="aggregate_transaction_failed"
    ):
        await service.run(
            factory,
            context=context,
            reviewed=reviewed,
            boundary=boundary(reviewed),
        )

    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.company_id == context.company.id)
            )
            == 1
        )
        run = await session.scalar(
            select(CustomerMigrationRun)
            .where(CustomerMigrationRun.company_id == context.company.id)
            .order_by(CustomerMigrationRun.started_at.desc())
        )
        assert run is not None
        assert run.status == "failed"
        assert (run.source_count, run.accepted_count, run.rejected_count) == (2, 1, 1)
        progress = await session.scalar(
            select(CustomerMigrationProgress).where(
                CustomerMigrationProgress.run_id == run.id
            )
        )
        assert progress is not None and progress.processed_count == 2
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationException)
                .join(CustomerMigrationRun)
                .where(CustomerMigrationRun.company_id == context.company.id)
            )
            == 1
        )
