import csv
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
from app.customer_migration.children import HousecallProCustomerChildrenMigration
from app.customer_migration.housecall_pro import HousecallProCustomerMigration
from app.events.models import BusinessEvent
from app.jobs.commands import MigrateJob
from app.jobs.models import Job, JobAppointmentLink
from app.jobs.service import JobService
from app.operational_migration.models import (
    AppointmentSourceIdentity,
    JobSourceIdentity,
    OperationalMigrationProgress,
    OperationalMigrationRun,
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
