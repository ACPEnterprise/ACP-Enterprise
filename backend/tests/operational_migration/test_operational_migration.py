import csv
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.customer_migration.children import HousecallProCustomerChildrenMigration
from app.customer_migration.housecall_pro import HousecallProCustomerMigration
from app.customer_migration.models import (
    CustomerMigrationRun,
    CustomerSourceIdentity,
    ServiceLocationSourceIdentity,
)
from app.customers.schemas import CustomerCreate, ServiceLocationCreate
from app.customers.service import CustomerService
from app.events.models import BusinessEvent
from app.financials.models import (
    Estimate,
    EstimateLineItem,
    Invoice,
    InvoiceLineItem,
    Payment,
)
from app.financials.service import FinancialService, MigrateInvoice
from app.jobs.commands import MigrateJob
from app.jobs.models import Job, JobAppointmentLink
from app.jobs.service import JobService
from app.operational_migration.financial import (
    EstimateMigrationRecord,
    FinancialLineItemRecord,
    FinancialMigrationProgress,
    FinancialMigrationService,
    InvoiceMigrationRecord,
    PaymentMigrationRecord,
)
from app.operational_migration.models import (
    AppointmentSourceIdentity,
    EstimateLineItemSourceIdentity,
    EstimateSourceIdentity,
    InvoiceLineItemSourceIdentity,
    InvoiceSourceIdentity,
    JobSourceIdentity,
    OperationalMigrationException,
    OperationalMigrationProgress,
    OperationalMigrationRun,
    PaymentSourceIdentity,
)
from app.operational_migration.service import (
    AppointmentMigrationRecord,
    JobMigrationRecord,
    MigrationProgress,
    OperationalMigrationService,
)
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User
from app.scheduling.models import Appointment
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

NOW = datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc)


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
            normalized_email=f"phase3-{suffix}@example.test",
            first_name="Migration",
            last_name="Operator",
            display_name="Migration Operator",
            status="active",
        )
        company = Company(
            name="Phase 3 Synthetic Company",
            code=f"P3{suffix}".upper(),
            status="active",
            timezone="America/New_York",
        )
        session.add_all([user, company])
        await session.flush()
        branch = Branch(
            company_id=company.id,
            name="Phase 3 Branch",
            code="PHASE3",
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


async def seed_migrated_customer(
    factory: async_sessionmaker[AsyncSession],
    *,
    context: AuthorizationContext,
    tmp_path: Path,
) -> None:
    customers = tmp_path / "customers.csv"
    contacts = tmp_path / "contacts.csv"
    locations = tmp_path / "locations.csv"
    write_csv(
        customers,
        ["Customer ID", "Display Name", "Type"],
        [["customer-1", "Phase 3 Synthetic Customer", "homeowner"]],
    )
    write_csv(
        contacts,
        ["Contact ID", "Customer ID", "First Name", "Last Name"],
        [],
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
        [["location-1", "customer-1", "301 Test Ave", "Testville", "FL", "33755"]],
    )
    customer_report = await HousecallProCustomerMigration().run(
        factory, context=context, source_path=customers, dry_run=False
    )
    location_report = await HousecallProCustomerChildrenMigration().run(
        factory,
        context=context,
        contacts_path=contacts,
        service_locations_path=locations,
        dry_run=False,
    )
    assert customer_report.accepted == 1
    assert location_report.accepted == 1


async def seed_primary_location_without_source_identity(
    factory: async_sessionmaker[AsyncSession],
    *,
    context: AuthorizationContext,
) -> None:
    assert context.active_branch is not None
    async with factory() as session, session.begin():
        run = CustomerMigrationRun(
            company_id=context.company.id,
            branch_id=context.active_branch.id,
            initiated_by_user_id=context.user.id,
            source_system="housecall_pro",
            source_sha256="0" * 64,
            mode="import",
            status="completed",
            source_count=1,
            accepted_count=1,
        )
        session.add(run)
        await session.flush()
        customer = await CustomerService().stage_migrated_customer(
            session,
            context=context,
            customer_data=CustomerCreate(
                customer_type="residential",
                display_name="Primary Adapter Customer",
                status="active",
            ),
            contact_data=None,
            service_location_data=ServiceLocationCreate(
                nickname="Primary",
                address="10 Adapter Way",
                city="Testville",
                state="FL",
                postal_code="33755",
            ),
            billing_address_data=None,
        )
        session.add(
            CustomerSourceIdentity(
                company_id=context.company.id,
                branch_id=context.active_branch.id,
                customer_id=customer.id,
                source_system="housecall_pro",
                source_customer_id="adapter-customer-1",
                first_run_id=run.id,
            )
        )


@pytest.mark.asyncio
async def test_operational_import_repairs_single_primary_location_identity(
    migration_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = migration_database
    context = await seed_context(factory)
    await seed_primary_location_without_source_identity(factory, context=context)
    record = JobMigrationRecord(
        source_id="adapter-job-1",
        source_customer_id="adapter-customer-1",
        source_service_location_id=("adapter-customer-1::service-location::1"),
        status="draft",
    )

    validation = await OperationalMigrationService().run(
        factory,
        context=context,
        source_system="housecall_pro",
        jobs=[record],
        appointments=[],
        dry_run=True,
    )
    assert validation.accepted == 1
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ServiceLocationSourceIdentity)
                .where(
                    ServiceLocationSourceIdentity.source_location_id
                    == "adapter-customer-1::service-location::1"
                )
            )
            == 0
        )

    imported = await OperationalMigrationService().run(
        factory,
        context=context,
        source_system="housecall_pro",
        jobs=[record],
        appointments=[],
        dry_run=False,
    )
    assert imported.accepted == 1
    async with factory() as session:
        identity = await session.scalar(
            select(ServiceLocationSourceIdentity).where(
                ServiceLocationSourceIdentity.source_location_id
                == "adapter-customer-1::service-location::1"
            )
        )
        assert identity is not None
        assert identity.source_location_id == (
            "adapter-customer-1::service-location::1"
        )


@pytest.mark.asyncio
async def test_operational_manifest_reuse_preserves_native_targets(
    migration_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, factory = migration_database
    context = await seed_context(factory)
    await seed_migrated_customer(factory, context=context, tmp_path=tmp_path)
    jobs, appointments = records()
    jobs = jobs[:2]
    appointments = appointments[:2]
    legacy = await OperationalMigrationService().run(
        factory,
        context=context,
        source_system="housecall_pro",
        jobs=jobs,
        appointments=appointments,
        dry_run=False,
    )
    assert legacy.accepted == 4
    async with factory() as session, session.begin():
        customer = await session.scalar(
            select(CustomerSourceIdentity).where(
                CustomerSourceIdentity.source_system == "housecall_pro",
                CustomerSourceIdentity.company_id == context.company.id,
            )
        )
        location = await session.scalar(
            select(ServiceLocationSourceIdentity).where(
                ServiceLocationSourceIdentity.source_system == "housecall_pro",
                ServiceLocationSourceIdentity.company_id == context.company.id,
            )
        )
        assert customer is not None and location is not None
        successor_customer = CustomerSourceIdentity(
            company_id=customer.company_id,
            branch_id=customer.branch_id,
            customer_id=customer.customer_id,
            source_system="successor_test",
            source_customer_id=customer.source_customer_id,
            first_run_id=customer.first_run_id,
        )
        session.add(successor_customer)
        await session.flush()
        session.add(
            ServiceLocationSourceIdentity(
                company_id=location.company_id,
                customer_source_identity_id=successor_customer.id,
                service_location_id=location.service_location_id,
                customer_id=location.customer_id,
                source_system="successor_test",
                source_location_id=location.source_location_id,
                first_run_id=location.first_run_id,
            )
        )
        job_targets = {
            item.source_job_id: item.job_id
            for item in (
                await session.scalars(
                    select(JobSourceIdentity).where(
                        JobSourceIdentity.source_system == "housecall_pro",
                        JobSourceIdentity.company_id == context.company.id,
                    )
                )
            ).all()
        }
        appointment_targets = {
            item.source_appointment_id: item.appointment_id
            for item in (
                await session.scalars(
                    select(AppointmentSourceIdentity).where(
                        AppointmentSourceIdentity.source_system == "housecall_pro",
                        AppointmentSourceIdentity.company_id == context.company.id,
                    )
                )
            ).all()
        }

    report = await OperationalMigrationService().run(
        factory,
        context=context,
        source_system="successor_test",
        jobs=jobs,
        appointments=appointments,
        dry_run=False,
        reuse_targets={
            **{("job", key): value for key, value in job_targets.items()},
            **{
                ("appointment", key): value
                for key, value in appointment_targets.items()
            },
        },
    )
    assert report.accepted == 4
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.company_id == context.company.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(Appointment.company_id == context.company.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(JobSourceIdentity)
                .where(
                    JobSourceIdentity.source_system == "successor_test",
                    JobSourceIdentity.company_id == context.company.id,
                )
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AppointmentSourceIdentity)
                .where(
                    AppointmentSourceIdentity.source_system == "successor_test",
                    AppointmentSourceIdentity.company_id == context.company.id,
                )
            )
            == 2
        )


@pytest.mark.asyncio
async def test_operational_resume_rejects_foreign_company_run(
    migration_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = migration_database
    foreign_context = await seed_context(factory)
    caller_context = await seed_context(factory)
    service = OperationalMigrationService()
    digest = service._digest("housecall_pro", [], [])
    assert foreign_context.active_branch is not None
    async with factory() as session, session.begin():
        foreign_run = OperationalMigrationRun(
            company_id=foreign_context.company.id,
            branch_id=foreign_context.active_branch.id,
            initiated_by_user_id=foreign_context.user.id,
            source_system="housecall_pro",
            source_digest=digest,
            mode="import",
            status="failed",
        )
        session.add(foreign_run)
        await session.flush()
        foreign_run_id = foreign_run.id

    with pytest.raises(ValueError, match="resume authority is contradictory"):
        await service.run(
            factory,
            context=caller_context,
            source_system="housecall_pro",
            jobs=[],
            appointments=[],
            dry_run=False,
            resume_run_id=foreign_run_id,
        )

    async with factory() as session:
        persisted = await session.get(OperationalMigrationRun, foreign_run_id)
        assert persisted is not None
        assert persisted.company_id == foreign_context.company.id
        assert persisted.status == "failed"


def records() -> tuple[list[JobMigrationRecord], list[AppointmentMigrationRecord]]:
    jobs = [
        JobMigrationRecord(
            source_id="job-1",
            source_customer_id="customer-1",
            source_service_location_id="location-1",
            source_job_number="HCP-1001",
            status="ready",
            activated_at=NOW,
            scheduled_start_at=NOW + timedelta(days=1),
            scheduled_end_at=NOW + timedelta(days=1, hours=2),
            summary="Synthetic diagnostic visit",
            priority="high",
            assigned_technician_source_ids=("technician-1",),
            external_metadata={"source_version": 1},
        ),
        JobMigrationRecord(
            source_id="job-2",
            source_customer_id="customer-1",
            source_service_location_id="location-1",
            source_job_number="HCP-1002",
            status="completed",
            activated_at=NOW,
            started_at=NOW + timedelta(hours=1),
            completed_at=NOW + timedelta(hours=2),
            summary="Synthetic completed visit",
        ),
        JobMigrationRecord(
            source_id="job-2",
            source_customer_id="customer-1",
            source_service_location_id="location-1",
            status="draft",
        ),
        JobMigrationRecord(
            source_id="job-3",
            source_customer_id="missing-customer",
            source_service_location_id="location-1",
            status="draft",
        ),
        JobMigrationRecord(
            source_id="job-4",
            source_customer_id="customer-1",
            source_service_location_id="location-1",
            status="draft",
            priority="not-a-priority",
        ),
        JobMigrationRecord(
            source_id="job-5",
            source_customer_id="customer-1",
            source_service_location_id="location-1",
            source_job_number="HCP-1001",
            status="ready",
            activated_at=NOW,
            scheduled_start_at=NOW + timedelta(days=1),
            summary="Synthetic diagnostic visit",
        ),
    ]
    appointments = [
        AppointmentMigrationRecord(
            source_id="appointment-1",
            source_job_id="job-1",
            source_customer_id="customer-1",
            source_service_location_id="location-1",
            status="scheduled",
            arrival_window_start_at=NOW + timedelta(days=1),
            arrival_window_end_at=NOW + timedelta(days=1, hours=2),
            duration_minutes=90,
            assigned_technician_source_ids=("technician-1",),
            notes="Synthetic appointment note",
        ),
        AppointmentMigrationRecord(
            source_id="appointment-2",
            source_job_id="job-2",
            source_customer_id="customer-1",
            source_service_location_id="location-1",
            status="completed",
            arrival_window_start_at=NOW + timedelta(hours=1),
            arrival_window_end_at=NOW + timedelta(hours=2),
            duration_minutes=60,
        ),
        AppointmentMigrationRecord(
            source_id="appointment-2",
            source_job_id="job-2",
            source_customer_id="customer-1",
            source_service_location_id="location-1",
            status="draft",
            arrival_window_start_at=None,
            arrival_window_end_at=None,
            duration_minutes=None,
        ),
        AppointmentMigrationRecord(
            source_id="appointment-3",
            source_job_id="missing-job",
            source_customer_id="customer-1",
            source_service_location_id="location-1",
            status="draft",
            arrival_window_start_at=None,
            arrival_window_end_at=None,
            duration_minutes=None,
        ),
        AppointmentMigrationRecord(
            source_id="appointment-4",
            source_job_id="job-1",
            source_customer_id="customer-1",
            source_service_location_id="location-1",
            status="scheduled",
            arrival_window_start_at=NOW + timedelta(days=2),
            arrival_window_end_at=NOW + timedelta(days=2, hours=1),
            duration_minutes=0,
        ),
        AppointmentMigrationRecord(
            source_id="appointment-5",
            source_job_id="job-1",
            source_customer_id="customer-1",
            source_service_location_id="location-1",
            status="scheduled",
            arrival_window_start_at=NOW + timedelta(days=1),
            arrival_window_end_at=NOW + timedelta(days=1, hours=2),
            duration_minutes=90,
        ),
    ]
    return jobs, appointments


@pytest.mark.asyncio
async def test_operational_dry_run_import_rerun_and_reconciliation(
    migration_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, factory = migration_database
    context = await seed_context(factory)
    await seed_migrated_customer(factory, context=context, tmp_path=tmp_path)
    jobs, appointments = records()
    updates: list[MigrationProgress] = []
    service = OperationalMigrationService()

    dry_run = await service.run(
        factory,
        context=context,
        source_system="housecall_pro",
        jobs=jobs,
        appointments=appointments,
        dry_run=True,
        progress_callback=updates.append,
    )
    assert (
        dry_run.source,
        dry_run.accepted,
        dry_run.rejected,
        dry_run.duplicate,
        dry_run.unresolved,
    ) == (12, 4, 2, 4, 2)
    assert len(updates) == 12
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(Appointment.company_id == context.company.id)
            )
            == 0
        )

    imported = await service.run(
        factory,
        context=context,
        source_system="housecall_pro",
        jobs=jobs,
        appointments=appointments,
        dry_run=False,
    )
    assert (
        imported.source,
        imported.accepted,
        imported.rejected,
        imported.duplicate,
        imported.unresolved,
    ) == (12, 4, 2, 4, 2)
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(JobSourceIdentity)
                .where(JobSourceIdentity.company_id == context.company.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AppointmentSourceIdentity)
                .where(AppointmentSourceIdentity.company_id == context.company.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(JobAppointmentLink)
                .where(JobAppointmentLink.company_id == context.company.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(
                    BusinessEvent.company_id == context.company.id,
                    BusinessEvent.event_type.in_(
                        {"job.migrated", "appointment.migrated"}
                    ),
                )
            )
            == 4
        )
        progress = list(
            (
                await session.scalars(
                    select(OperationalMigrationProgress).where(
                        OperationalMigrationProgress.run_id == imported.run_id
                    )
                )
            ).all()
        )
        assert len(progress) == 2
        assert all(item.source_count == item.processed_count == 6 for item in progress)
        job_identity = await session.scalar(
            select(JobSourceIdentity).where(JobSourceIdentity.source_job_id == "job-1")
        )
        assert job_identity is not None
        assert job_identity.source_job_number == "HCP-1001"
        assert job_identity.assigned_technician_source_ids == ["technician-1"]
        assert job_identity.external_metadata["source_version"] == 1

    rerun = await service.run(
        factory,
        context=context,
        source_system="housecall_pro",
        jobs=jobs,
        appointments=appointments,
        dry_run=False,
    )
    assert (
        rerun.source,
        rerun.accepted,
        rerun.rejected,
        rerun.duplicate,
        rerun.unresolved,
    ) == (12, 0, 2, 8, 2)


class FailingJobService(JobService):
    async def stage_migrated_job(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: MigrateJob,
    ) -> Job:
        await super().stage_migrated_job(session, context=context, command=command)
        raise RuntimeError("synthetic operational transaction failure")


@pytest.mark.asyncio
async def test_operational_record_rolls_back_and_marks_run_failed(
    migration_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, factory = migration_database
    context = await seed_context(factory)
    await seed_migrated_customer(factory, context=context, tmp_path=tmp_path)
    job = JobMigrationRecord(
        source_id="atomic-job",
        source_customer_id="customer-1",
        source_service_location_id="location-1",
        status="draft",
    )
    service = OperationalMigrationService(job_service=FailingJobService())

    with pytest.raises(RuntimeError, match="synthetic operational transaction failure"):
        await service.run(
            factory,
            context=context,
            source_system="housecall_pro",
            jobs=[job],
            appointments=[],
            dry_run=False,
        )

    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(JobSourceIdentity)
                .where(JobSourceIdentity.company_id == context.company.id)
            )
            == 0
        )
        run = await session.scalar(
            select(OperationalMigrationRun)
            .where(OperationalMigrationRun.company_id == context.company.id)
            .order_by(OperationalMigrationRun.started_at.desc())
        )
        assert run is not None
        assert run.status == "failed"
        assert run.source_count == 0


async def seed_migrated_job(
    factory: async_sessionmaker[AsyncSession],
    *,
    context: AuthorizationContext,
) -> None:
    report = await OperationalMigrationService().run(
        factory,
        context=context,
        source_system="housecall_pro",
        jobs=[
            JobMigrationRecord(
                source_id="financial-job-1",
                source_customer_id="customer-1",
                source_service_location_id="location-1",
                status="ready",
                activated_at=NOW,
            )
        ],
        appointments=[],
        dry_run=False,
    )
    assert report.accepted == 1


def financial_records() -> tuple[
    list[EstimateMigrationRecord],
    list[InvoiceMigrationRecord],
    list[PaymentMigrationRecord],
]:
    item = FinancialLineItemRecord(
        source_id="line-1",
        description="Synthetic diagnostic service",
        quantity=Decimal("2.000"),
        unit_price=Decimal("50.00"),
        total_amount=Decimal("100.00"),
    )
    estimates = [
        EstimateMigrationRecord(
            source_id="estimate-1",
            source_job_id="financial-job-1",
            status="presented",
            currency="USD",
            subtotal_amount=Decimal("100.00"),
            tax_amount=Decimal("7.00"),
            total_amount=Decimal("107.00"),
            line_items=(item,),
            presented_at=NOW,
            expires_on=date(2026, 2, 15),
            external_metadata={"synthetic_version": 1},
        ),
        EstimateMigrationRecord(
            source_id="estimate-1",
            source_job_id="financial-job-1",
            status="draft",
            currency="USD",
            subtotal_amount=Decimal("100.00"),
            tax_amount=Decimal("7.00"),
            total_amount=Decimal("107.00"),
            line_items=(item,),
        ),
        EstimateMigrationRecord(
            source_id="estimate-missing-job",
            source_job_id="missing-job",
            status="draft",
            currency="USD",
            subtotal_amount=Decimal("100.00"),
            tax_amount=Decimal("7.00"),
            total_amount=Decimal("107.00"),
            line_items=(item,),
        ),
    ]
    invoices = [
        InvoiceMigrationRecord(
            source_id="invoice-1",
            source_job_id="financial-job-1",
            status="issued",
            currency="USD",
            subtotal_amount=Decimal("100.00"),
            tax_amount=Decimal("7.00"),
            total_amount=Decimal("107.00"),
            line_items=(
                FinancialLineItemRecord(
                    source_id="invoice-line-1",
                    description="Synthetic diagnostic service",
                    quantity=Decimal("2.000"),
                    unit_price=Decimal("50.00"),
                    total_amount=Decimal("100.00"),
                ),
            ),
            issued_at=NOW,
            due_on=date(2026, 2, 15),
        ),
        InvoiceMigrationRecord(
            source_id="invoice-1",
            source_job_id="financial-job-1",
            status="draft",
            currency="USD",
            subtotal_amount=Decimal("100.00"),
            tax_amount=Decimal("7.00"),
            total_amount=Decimal("107.00"),
            line_items=(item,),
        ),
        InvoiceMigrationRecord(
            source_id="invoice-invalid-lines",
            source_job_id="financial-job-1",
            status="draft",
            currency="USD",
            subtotal_amount=Decimal("90.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("90.00"),
            line_items=(item,),
        ),
    ]
    payments = [
        PaymentMigrationRecord(
            source_id="payment-1",
            source_invoice_id="invoice-1",
            status="succeeded",
            currency="USD",
            amount=Decimal("107.00"),
            paid_at=NOW + timedelta(hours=1),
            method="synthetic_card",
            reference="synthetic-reference",
        ),
        PaymentMigrationRecord(
            source_id="payment-1",
            source_invoice_id="invoice-1",
            status="succeeded",
            currency="USD",
            amount=Decimal("107.00"),
        ),
        PaymentMigrationRecord(
            source_id="payment-missing-invoice",
            source_invoice_id="missing-invoice",
            status="pending",
            currency="USD",
            amount=Decimal("25.00"),
        ),
    ]
    return estimates, invoices, payments


@pytest.mark.asyncio
async def test_financial_dry_run_import_rerun_and_reconciliation(
    migration_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, factory = migration_database
    context = await seed_context(factory)
    await seed_migrated_customer(factory, context=context, tmp_path=tmp_path)
    await seed_migrated_job(factory, context=context)
    estimates, invoices, payments = financial_records()
    updates: list[FinancialMigrationProgress] = []
    service = FinancialMigrationService()

    dry_run = await service.run(
        factory,
        context=context,
        source_system="housecall_pro",
        estimates=estimates,
        invoices=invoices,
        payments=payments,
        dry_run=True,
        progress_callback=updates.append,
    )
    assert (
        dry_run.source,
        dry_run.accepted,
        dry_run.rejected,
        dry_run.duplicate,
        dry_run.unresolved,
    ) == (9, 3, 1, 3, 2)
    assert len(updates) == 9
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Estimate)) == 0
        assert await session.scalar(select(func.count()).select_from(Invoice)) == 0
        assert await session.scalar(select(func.count()).select_from(Payment)) == 0

    imported = await service.run(
        factory,
        context=context,
        source_system="housecall_pro",
        estimates=estimates,
        invoices=invoices,
        payments=payments,
        dry_run=False,
    )
    assert (
        imported.source,
        imported.accepted,
        imported.rejected,
        imported.duplicate,
        imported.unresolved,
    ) == (9, 3, 1, 3, 2)
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Estimate)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(EstimateLineItem))
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(Invoice)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(InvoiceLineItem)) == 1
        )
        assert await session.scalar(select(func.count()).select_from(Payment)) == 1
        assert (
            await session.scalar(
                select(func.count()).select_from(EstimateSourceIdentity)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(EstimateLineItemSourceIdentity)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(InvoiceSourceIdentity)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(InvoiceLineItemSourceIdentity)
            )
            == 1
        )
        payment_identity = await session.scalar(select(PaymentSourceIdentity))
        assert payment_identity is not None
        payment = await session.get(Payment, payment_identity.payment_id)
        assert payment is not None
        assert payment.invoice_id == payment_identity.invoice_id
        progress = list(
            (
                await session.scalars(
                    select(OperationalMigrationProgress).where(
                        OperationalMigrationProgress.run_id == imported.run_id
                    )
                )
            ).all()
        )
        assert len(progress) == 3
        assert all(item.source_count == item.processed_count == 3 for item in progress)
        migration_exceptions = list(
            (
                await session.scalars(
                    select(OperationalMigrationException).where(
                        OperationalMigrationException.run_id == imported.run_id
                    )
                )
            ).all()
        )
        assert all(
            item.detail == "Required parent authority could not be resolved."
            for item in migration_exceptions
            if item.reason_code == "missing_parent"
        )
        assert all(
            item.detail == "Financial migration record failed validation."
            for item in migration_exceptions
            if item.reason_code == "validation_failed"
        )
        assert all(
            "missing-" not in item.detail and "synthetic-reference" not in item.detail
            for item in migration_exceptions
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(
                    BusinessEvent.company_id == context.company.id,
                    BusinessEvent.event_type.in_(
                        {
                            "estimate.migrated",
                            "invoice.migrated",
                            "payment.migrated",
                        }
                    ),
                )
            )
            == 3
        )

    rerun = await service.run(
        factory,
        context=context,
        source_system="housecall_pro",
        estimates=estimates,
        invoices=invoices,
        payments=payments,
        dry_run=False,
    )
    assert (
        rerun.source,
        rerun.accepted,
        rerun.rejected,
        rerun.duplicate,
        rerun.unresolved,
    ) == (9, 0, 1, 6, 2)


@pytest.mark.asyncio
async def test_financial_manifest_reuse_preserves_native_truth_and_binds_items(
    migration_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, factory = migration_database
    context = await seed_context(factory)
    await seed_migrated_customer(factory, context=context, tmp_path=tmp_path)
    await seed_migrated_job(factory, context=context)
    estimates, invoices, payments = financial_records()
    estimates, invoices, payments = estimates[:1], invoices[:1], payments[:1]
    first = await FinancialMigrationService().run(
        factory,
        context=context,
        source_system="housecall_pro",
        estimates=estimates,
        invoices=invoices,
        payments=payments,
        dry_run=False,
    )
    assert first.accepted == 3
    async with factory() as session, session.begin():
        legacy_job = await session.scalar(
            select(JobSourceIdentity).where(
                JobSourceIdentity.source_system == "housecall_pro",
                JobSourceIdentity.company_id == context.company.id,
            )
        )
        assert legacy_job is not None
        session.add(
            JobSourceIdentity(
                company_id=legacy_job.company_id,
                branch_id=legacy_job.branch_id,
                job_id=legacy_job.job_id,
                customer_id=legacy_job.customer_id,
                service_location_id=legacy_job.service_location_id,
                customer_source_identity_id=legacy_job.customer_source_identity_id,
                service_location_source_identity_id=(
                    legacy_job.service_location_source_identity_id
                ),
                source_system="successor_test",
                source_job_id=legacy_job.source_job_id,
                source_job_number=legacy_job.source_job_number,
                source_status=legacy_job.source_status,
                assigned_technician_source_ids=[],
                external_metadata={},
                first_run_id=legacy_job.first_run_id,
            )
        )
        estimate = await session.scalar(
            select(Estimate).where(Estimate.company_id == context.company.id)
        )
        invoice = await session.scalar(
            select(Invoice).where(Invoice.company_id == context.company.id)
        )
        payment = await session.scalar(
            select(Payment).where(Payment.company_id == context.company.id)
        )
        assert estimate is not None and invoice is not None and payment is not None
        targets = {
            ("estimate", estimates[0].source_id): estimate.id,
            ("invoice", invoices[0].source_id): invoice.id,
            ("payment", payments[0].source_id): payment.id,
        }

    report = await FinancialMigrationService().run(
        factory,
        context=context,
        source_system="successor_test",
        estimates=estimates,
        invoices=invoices,
        payments=payments,
        dry_run=False,
        reuse_targets=targets,
    )
    assert report.accepted == 3
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Estimate)
                .where(Estimate.company_id == context.company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Invoice)
                .where(Invoice.company_id == context.company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Payment)
                .where(Payment.company_id == context.company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(EstimateLineItemSourceIdentity)
                .where(
                    EstimateLineItemSourceIdentity.source_system == "successor_test",
                    EstimateLineItemSourceIdentity.company_id == context.company.id,
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(InvoiceLineItemSourceIdentity)
                .where(
                    InvoiceLineItemSourceIdentity.source_system == "successor_test",
                    InvoiceLineItemSourceIdentity.company_id == context.company.id,
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PaymentSourceIdentity)
                .where(
                    PaymentSourceIdentity.source_system == "successor_test",
                    PaymentSourceIdentity.company_id == context.company.id,
                )
            )
            == 1
        )


class FailingFinancialService(FinancialService):
    async def stage_migrated_invoice(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: MigrateInvoice,
    ) -> tuple[Invoice, tuple[InvoiceLineItem, ...]]:
        await super().stage_migrated_invoice(session, context=context, command=command)
        raise RuntimeError("synthetic financial transaction failure")


@pytest.mark.asyncio
async def test_financial_record_rolls_back_and_marks_run_failed(
    migration_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, factory = migration_database
    context = await seed_context(factory)
    await seed_migrated_customer(factory, context=context, tmp_path=tmp_path)
    await seed_migrated_job(factory, context=context)
    _, invoices, _ = financial_records()
    service = FinancialMigrationService(financial_service=FailingFinancialService())

    with pytest.raises(RuntimeError, match="synthetic financial transaction failure"):
        await service.run(
            factory,
            context=context,
            source_system="housecall_pro",
            estimates=[],
            invoices=[invoices[0]],
            payments=[],
            dry_run=False,
        )

    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Invoice)
                .where(Invoice.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(InvoiceSourceIdentity)
                .where(InvoiceSourceIdentity.company_id == context.company.id)
            )
            == 0
        )
        run = await session.scalar(
            select(OperationalMigrationRun)
            .where(OperationalMigrationRun.company_id == context.company.id)
            .order_by(OperationalMigrationRun.started_at.desc())
        )
        assert run is not None
        assert run.status == "failed"
        assert run.source_count == 0
