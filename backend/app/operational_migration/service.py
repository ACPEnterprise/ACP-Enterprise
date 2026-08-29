import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.models import (
    CustomerSourceIdentity,
    ServiceLocationSourceIdentity,
)
from app.jobs.commands import MigrateJob
from app.jobs.errors import JobError
from app.jobs.models import Job
from app.jobs.service import JobService
from app.jobs.types import JobPriority
from app.operational_migration.hcp_rehearsal_authority import (
    SOURCE4_SYSTEM,
    require_sanctioned_context,
)
from app.operational_migration.models import (
    AppointmentSourceIdentity,
    JobSourceIdentity,
    OperationalMigrationException,
    OperationalMigrationProgress,
    OperationalMigrationRun,
    utc_now,
)
from app.operational_migration.repository import (
    OperationalMigrationRepository,
    operational_migration_repository,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.errors import SchedulingError
from app.scheduling.service import (
    MigrateAppointmentCommand,
    SchedulingService,
)
from app.scheduling.types import AppointmentReference, AppointmentStatus

EntityType = Literal["job", "appointment"]
Disposition = Literal["accepted", "rejected", "duplicate", "unresolved"]


class MigrationRecordError(ValueError):
    pass


class ParentResolutionError(MigrationRecordError):
    pass


@dataclass(frozen=True)
class JobMigrationRecord:
    source_id: str
    source_customer_id: str
    source_service_location_id: str
    status: str
    source_job_number: str | None = None
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    activated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    summary: str | None = None
    description: str | None = None
    priority: str = "normal"
    assigned_technician_source_ids: tuple[str, ...] = ()
    external_metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class AppointmentMigrationRecord:
    source_id: str
    source_job_id: str
    source_customer_id: str
    source_service_location_id: str
    status: str
    arrival_window_start_at: datetime | None
    arrival_window_end_at: datetime | None
    duration_minutes: int | None
    assigned_technician_source_ids: tuple[str, ...] = ()
    notes: str | None = None
    external_metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class MigrationProgress:
    run_id: UUID
    entity_type: EntityType
    source: int
    processed: int
    accepted: int
    rejected: int
    duplicate: int
    unresolved: int


@dataclass(frozen=True)
class MigrationReport:
    run_id: UUID
    mode: str
    source: int
    accepted: int
    rejected: int
    duplicate: int
    unresolved: int


@dataclass
class _EntityCounts:
    source: int
    processed: int = 0
    accepted: int = 0
    rejected: int = 0
    duplicate: int = 0
    unresolved: int = 0

    def advance(self, disposition: Disposition) -> None:
        self.processed += 1
        setattr(self, disposition, getattr(self, disposition) + 1)


@dataclass(frozen=True)
class _ResolvedCustomer:
    customer_identity: CustomerSourceIdentity
    location_identity: ServiceLocationSourceIdentity


class OperationalMigrationService:
    """Provider-neutral Job and Appointment migration orchestration."""

    def __init__(
        self,
        *,
        job_service: JobService | None = None,
        scheduling_service: SchedulingService | None = None,
        repository: OperationalMigrationRepository = operational_migration_repository,
    ) -> None:
        self._jobs = job_service or JobService()
        self._scheduling = scheduling_service or SchedulingService()
        self._repository = repository

    @staticmethod
    def _validate_source_system(value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or len(normalized) > 80:
            raise ValueError("source_system must contain 1 to 80 characters")
        return normalized

    @staticmethod
    def _validate_record(
        record: JobMigrationRecord | AppointmentMigrationRecord,
    ) -> None:
        source_id = record.source_id
        if not isinstance(source_id, str) or not source_id.strip():
            raise MigrationRecordError("Source identifier is required.")
        if len(source_id) > 191:
            raise MigrationRecordError("Source identifier exceeds 191 characters.")
        metadata = record.external_metadata
        try:
            json.dumps(metadata or {}, sort_keys=True)
        except (TypeError, ValueError) as error:
            raise MigrationRecordError(
                "External metadata must be JSON serializable."
            ) from error
        technicians = record.assigned_technician_source_ids
        if any(not value.strip() for value in technicians):
            raise MigrationRecordError("Technician source identifiers cannot be blank.")
        if len(set(technicians)) != len(technicians):
            raise MigrationRecordError("Technician source identifiers must be unique.")

    @staticmethod
    def _digest(
        source_system: str,
        jobs: Sequence[JobMigrationRecord],
        appointments: Sequence[AppointmentMigrationRecord],
    ) -> str:
        payload = json.dumps(
            {
                "source_system": source_system,
                "jobs": [asdict(record) for record in jobs],
                "appointments": [asdict(record) for record in appointments],
            },
            sort_keys=True,
            default=lambda value: (
                value.isoformat() if isinstance(value, datetime) else str(value)
            ),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    async def _resolve_customer(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        source_system: str,
        source_customer_id: str,
        source_location_id: str,
        persist_location_identity: bool,
    ) -> _ResolvedCustomer:
        assert context.active_branch is not None
        customer = await self._repository.get_customer_identity(
            session,
            company_id=context.company.id,
            branch_id=context.active_branch.id,
            source_system=source_system,
            source_customer_id=source_customer_id,
        )
        if customer is None:
            raise ParentResolutionError("Migrated Customer parent was not found.")
        location = await self._repository.get_location_identity(
            session,
            company_id=context.company.id,
            customer_source_identity_id=customer.id,
            source_system=source_system,
            source_location_id=source_location_id,
        )
        expected_location_id = f"{source_customer_id}::service-location::1"
        if location is None and source_location_id == expected_location_id:
            target = await self._repository.get_only_customer_location(
                session,
                customer_id=customer.customer_id,
            )
            if target is not None:
                location = ServiceLocationSourceIdentity(
                    company_id=context.company.id,
                    customer_source_identity_id=customer.id,
                    service_location_id=target.id,
                    customer_id=customer.customer_id,
                    source_system=source_system,
                    source_location_id=source_location_id,
                    first_run_id=customer.first_run_id,
                )
                if persist_location_identity:
                    location = await self._repository.add_location_identity(
                        session, location
                    )
        if location is None:
            raise ParentResolutionError(
                "Migrated Service Location parent was not found."
            )
        return _ResolvedCustomer(customer, location)

    @staticmethod
    def _job_fingerprint(record: JobMigrationRecord) -> tuple[object, ...]:
        return (
            record.source_customer_id,
            record.source_service_location_id,
            record.source_job_number,
            record.summary,
            record.scheduled_start_at,
        )

    @staticmethod
    def _appointment_fingerprint(
        record: AppointmentMigrationRecord,
    ) -> tuple[object, ...]:
        return (
            record.source_job_id,
            record.arrival_window_start_at,
            record.arrival_window_end_at,
        )

    async def run(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        source_system: str,
        jobs: Sequence[JobMigrationRecord],
        appointments: Sequence[AppointmentMigrationRecord],
        dry_run: bool,
        master_run_id: UUID | None = None,
        repair_of_run_id: UUID | None = None,
        repair_generation: int = 0,
        resume_run_id: UUID | None = None,
        progress_callback: Callable[[MigrationProgress], None] | None = None,
    ) -> MigrationReport:
        source_system = self._validate_source_system(source_system)
        if source_system == SOURCE4_SYSTEM and master_run_id is None:
            raise ValueError("SOURCE.4 operational import requires a master run")
        if source_system == SOURCE4_SYSTEM:
            require_sanctioned_context(context)
        if context.active_branch is None or not context.can_access_branch(
            context.active_branch.id
        ):
            raise ValueError("An authorized active Branch is required.")
        digest = self._digest(source_system, jobs, appointments)
        async with factory() as session, session.begin():
            run = (
                await self._repository.get_run_for_update(session, resume_run_id)
                if resume_run_id is not None
                else None
            )
            if run is not None:
                if (
                    run.source_digest != digest
                    or run.master_run_id != master_run_id
                    or run.repair_of_run_id != repair_of_run_id
                    or run.repair_generation != repair_generation
                    or run.status not in {"running", "failed"}
                ):
                    raise ValueError("operational resume authority is contradictory")
                run.status = "running"
                run.completed_at = None
            elif resume_run_id is not None:
                raise ValueError("operational resume run is missing")
            else:
                run = OperationalMigrationRun(
                    company_id=context.company.id,
                    branch_id=context.active_branch.id,
                    initiated_by_user_id=context.user.id,
                    master_run_id=master_run_id,
                    master_domain="operational" if master_run_id is not None else None,
                    repair_of_run_id=repair_of_run_id,
                    repair_generation=repair_generation,
                    source_system=source_system,
                    source_digest=digest,
                    mode="dry_run" if dry_run else "import",
                    status="running",
                )
                await self._repository.create_run(session, run)
            run_id = run.id

        counts = {
            "job": _EntityCounts(len(jobs)),
            "appointment": _EntityCounts(len(appointments)),
        }
        exceptions: list[tuple[EntityType, int, str | None, Disposition, str, str]] = []
        planned_jobs: dict[str, Job] = {}
        seen_ids: dict[EntityType, set[str]] = {"job": set(), "appointment": set()}
        seen_fingerprints: dict[EntityType, set[tuple[object, ...]]] = {
            "job": set(),
            "appointment": set(),
        }
        try:
            if dry_run:
                async with factory() as session:
                    transaction = await session.begin()
                    await self._process_jobs(
                        session,
                        context=context,
                        run_id=run_id,
                        source_system=source_system,
                        records=jobs,
                        counts=counts["job"],
                        exceptions=exceptions,
                        planned_jobs=planned_jobs,
                        seen_ids=seen_ids["job"],
                        seen_fingerprints=seen_fingerprints["job"],
                        persist_identity=False,
                        progress_callback=progress_callback,
                    )
                    await self._process_appointments(
                        session,
                        context=context,
                        run_id=run_id,
                        source_system=source_system,
                        records=appointments,
                        counts=counts["appointment"],
                        exceptions=exceptions,
                        planned_jobs=planned_jobs,
                        seen_ids=seen_ids["appointment"],
                        seen_fingerprints=seen_fingerprints["appointment"],
                        persist_identity=False,
                        progress_callback=progress_callback,
                    )
                    await transaction.rollback()
            else:
                for index, job_record in enumerate(jobs, start=1):
                    async with factory() as session, session.begin():
                        await self._process_job(
                            session,
                            context=context,
                            run_id=run_id,
                            source_system=source_system,
                            record=job_record,
                            index=index,
                            counts=counts["job"],
                            exceptions=exceptions,
                            planned_jobs=planned_jobs,
                            seen_ids=seen_ids["job"],
                            seen_fingerprints=seen_fingerprints["job"],
                            persist_identity=True,
                            progress_callback=progress_callback,
                            resume_run_id=resume_run_id,
                        )
                for index, appointment_record in enumerate(appointments, start=1):
                    async with factory() as session, session.begin():
                        await self._process_appointment(
                            session,
                            context=context,
                            run_id=run_id,
                            source_system=source_system,
                            record=appointment_record,
                            index=index,
                            counts=counts["appointment"],
                            exceptions=exceptions,
                            planned_jobs=planned_jobs,
                            seen_ids=seen_ids["appointment"],
                            seen_fingerprints=seen_fingerprints["appointment"],
                            persist_identity=True,
                            progress_callback=progress_callback,
                            resume_run_id=resume_run_id,
                        )
        except Exception:
            await self._finalize(
                factory,
                run_id=run_id,
                counts=counts,
                exceptions=exceptions,
                status="failed",
            )
            raise
        return await self._finalize(
            factory,
            run_id=run_id,
            counts=counts,
            exceptions=exceptions,
            status="completed",
        )

    async def _process_jobs(self, session: AsyncSession, **kwargs: object) -> None:
        records = kwargs.pop("records")
        assert isinstance(records, Sequence)
        for index, record in enumerate(records, start=1):
            assert isinstance(record, JobMigrationRecord)
            async with session.begin_nested():
                await self._process_job(
                    session,
                    record=record,
                    index=index,
                    **kwargs,  # type: ignore[arg-type]
                )

    async def _process_appointments(
        self, session: AsyncSession, **kwargs: object
    ) -> None:
        records = kwargs.pop("records")
        assert isinstance(records, Sequence)
        for index, record in enumerate(records, start=1):
            assert isinstance(record, AppointmentMigrationRecord)
            async with session.begin_nested():
                await self._process_appointment(
                    session,
                    record=record,
                    index=index,
                    **kwargs,  # type: ignore[arg-type]
                )

    async def _process_job(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        run_id: UUID,
        source_system: str,
        record: JobMigrationRecord,
        index: int,
        counts: _EntityCounts,
        exceptions: list[tuple[EntityType, int, str | None, Disposition, str, str]],
        planned_jobs: dict[str, Job],
        seen_ids: set[str],
        seen_fingerprints: set[tuple[object, ...]],
        persist_identity: bool,
        progress_callback: Callable[[MigrationProgress], None] | None,
        resume_run_id: UUID | None = None,
    ) -> None:
        assert context.active_branch is not None
        disposition: Disposition = "accepted"
        reason = detail = ""
        try:
            self._validate_record(record)
            fingerprint = self._job_fingerprint(record)
            if record.source_id in seen_ids:
                disposition, reason, detail = (
                    "duplicate",
                    "duplicate_source_id_in_input",
                    "Job source identifier occurs more than once.",
                )
            elif fingerprint in seen_fingerprints:
                disposition, reason, detail = (
                    "duplicate",
                    "duplicate_identity_in_input",
                    "Another Job has the same normalized migration identity.",
                )
            else:
                seen_ids.add(record.source_id)
                seen_fingerprints.add(fingerprint)
                existing = await self._repository.get_job_identity(
                    session,
                    company_id=context.company.id,
                    source_system=source_system,
                    source_job_id=record.source_id,
                )
                number_match = (
                    await self._repository.count_source_job_number(
                        session,
                        company_id=context.company.id,
                        source_system=source_system,
                        source_job_number=record.source_job_number,
                    )
                    if record.source_job_number
                    else 0
                )
                if existing and existing.first_run_id == resume_run_id:
                    disposition = "accepted"
                elif existing:
                    disposition, reason, detail = (
                        "duplicate",
                        "source_identity_exists",
                        "Job source identity already exists.",
                    )
                elif number_match:
                    disposition, reason, detail = (
                        "unresolved",
                        "source_job_number_match",
                        "An existing migrated Job has this source job number.",
                    )
                else:
                    parents = await self._resolve_customer(
                        session,
                        context=context,
                        source_system=source_system,
                        source_customer_id=record.source_customer_id,
                        source_location_id=record.source_service_location_id,
                        persist_location_identity=persist_identity,
                    )
                    try:
                        priority = JobPriority(record.priority)
                    except ValueError as error:
                        raise MigrationRecordError(
                            "Job priority is invalid."
                        ) from error
                    job = await self._jobs.stage_migrated_job(
                        session,
                        context=context,
                        command=MigrateJob(
                            branch_id=context.active_branch.id,
                            customer_id=parents.customer_identity.customer_id,
                            service_location_id=parents.location_identity.service_location_id,
                            status=record.status,
                            priority=priority,
                            customer_reported_problem=record.summary,
                            internal_description=record.description,
                            activated_at=record.activated_at,
                            started_at=record.started_at,
                            completed_at=record.completed_at,
                        ),
                    )
                    planned_jobs[record.source_id] = job
                    if persist_identity:
                        metadata = dict(record.external_metadata or {})
                        metadata["scheduled_start_at"] = (
                            record.scheduled_start_at.isoformat()
                            if record.scheduled_start_at
                            else None
                        )
                        metadata["scheduled_end_at"] = (
                            record.scheduled_end_at.isoformat()
                            if record.scheduled_end_at
                            else None
                        )
                        self._repository.add_job_identity(
                            session,
                            JobSourceIdentity(
                                company_id=context.company.id,
                                branch_id=context.active_branch.id,
                                job_id=job.id,
                                customer_id=job.customer_id,
                                service_location_id=job.service_location_id,
                                customer_source_identity_id=parents.customer_identity.id,
                                service_location_source_identity_id=parents.location_identity.id,
                                source_system=source_system,
                                source_job_id=record.source_id,
                                source_job_number=record.source_job_number,
                                source_status=record.status,
                                assigned_technician_source_ids=list(
                                    record.assigned_technician_source_ids
                                ),
                                external_metadata=metadata,
                                first_run_id=run_id,
                            ),
                        )
        except ParentResolutionError as error:
            disposition, reason, detail = (
                "unresolved",
                "parent_unresolved",
                str(error),
            )
        except (JobError, MigrationRecordError, ValueError) as error:
            disposition, reason, detail = (
                "rejected",
                "validation_failed",
                str(error),
            )
        self._record_result(
            run_id,
            "job",
            index,
            record.source_id,
            disposition,
            reason,
            detail,
            counts,
            exceptions,
            progress_callback,
        )

    async def _process_appointment(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        run_id: UUID,
        source_system: str,
        record: AppointmentMigrationRecord,
        index: int,
        counts: _EntityCounts,
        exceptions: list[tuple[EntityType, int, str | None, Disposition, str, str]],
        planned_jobs: dict[str, Job],
        seen_ids: set[str],
        seen_fingerprints: set[tuple[object, ...]],
        persist_identity: bool,
        progress_callback: Callable[[MigrationProgress], None] | None,
        resume_run_id: UUID | None = None,
    ) -> None:
        assert context.active_branch is not None
        disposition: Disposition = "accepted"
        reason = detail = ""
        try:
            self._validate_record(record)
            fingerprint = self._appointment_fingerprint(record)
            if record.source_id in seen_ids:
                disposition, reason, detail = (
                    "duplicate",
                    "duplicate_source_id_in_input",
                    "Appointment source identifier occurs more than once.",
                )
            elif fingerprint in seen_fingerprints:
                disposition, reason, detail = (
                    "duplicate",
                    "duplicate_identity_in_input",
                    "Another Appointment has the same parent and arrival window.",
                )
            else:
                seen_ids.add(record.source_id)
                seen_fingerprints.add(fingerprint)
                existing = await self._repository.get_appointment_identity(
                    session,
                    company_id=context.company.id,
                    source_system=source_system,
                    source_appointment_id=record.source_id,
                )
                if existing and existing.first_run_id == resume_run_id:
                    disposition = "accepted"
                elif existing:
                    disposition, reason, detail = (
                        "duplicate",
                        "source_identity_exists",
                        "Appointment source identity already exists.",
                    )
                else:
                    parents = await self._resolve_customer(
                        session,
                        context=context,
                        source_system=source_system,
                        source_customer_id=record.source_customer_id,
                        source_location_id=record.source_service_location_id,
                        persist_location_identity=persist_identity,
                    )
                    job_identity = await self._repository.get_job_identity(
                        session,
                        company_id=context.company.id,
                        source_system=source_system,
                        source_job_id=record.source_job_id,
                    )
                    job = planned_jobs.get(record.source_job_id)
                    if job is None and job_identity is not None:
                        job = await self._repository.get_job(
                            session, job_identity.job_id
                        )
                    if job is None:
                        raise ParentResolutionError(
                            "Migrated parent Job was not found."
                        )
                    if (
                        job.customer_id != parents.customer_identity.customer_id
                        or job.service_location_id
                        != parents.location_identity.service_location_id
                    ):
                        raise ParentResolutionError(
                            "Appointment parents do not match its migrated Job."
                        )
                    try:
                        status = AppointmentStatus(record.status)
                    except ValueError as error:
                        raise MigrationRecordError(
                            "Appointment status is invalid."
                        ) from error
                    appointment = await self._scheduling.stage_migrated_appointment(
                        session,
                        context=context,
                        command=MigrateAppointmentCommand(
                            branch_id=context.active_branch.id,
                            customer_id=job.customer_id,
                            service_location_id=job.service_location_id,
                            status=status,
                            arrival_window_start_at=record.arrival_window_start_at,
                            arrival_window_end_at=record.arrival_window_end_at,
                            expected_duration_minutes=record.duration_minutes,
                        ),
                    )
                    reference = AppointmentReference(
                        id=appointment.id,
                        company_id=appointment.company_id,
                        branch_id=appointment.branch_id,
                        customer_id=appointment.customer_id,
                        service_location_id=appointment.service_location_id,
                        status=status,
                    )
                    migration_metadata = record.external_metadata or {}
                    visit_sequence = migration_metadata.get("visit_sequence")
                    if migration_metadata.get("repair_contract") and not isinstance(
                        visit_sequence, int
                    ):
                        raise MigrationRecordError(
                            "Appointment visit sequence is absent from the repair plan."
                        )
                    await self._jobs.stage_migrated_appointment_link(
                        session,
                        context=context,
                        job=job,
                        appointment=reference,
                        visit_sequence=(
                            visit_sequence if isinstance(visit_sequence, int) else 1
                        ),
                    )
                    if persist_identity:
                        assert job_identity is not None
                        metadata = dict(record.external_metadata or {})
                        metadata["notes"] = record.notes
                        self._repository.add_appointment_identity(
                            session,
                            AppointmentSourceIdentity(
                                company_id=context.company.id,
                                branch_id=context.active_branch.id,
                                appointment_id=appointment.id,
                                job_source_identity_id=job_identity.id,
                                job_id=job.id,
                                customer_id=job.customer_id,
                                service_location_id=job.service_location_id,
                                source_system=source_system,
                                source_appointment_id=record.source_id,
                                source_status=record.status,
                                assigned_technician_source_ids=list(
                                    record.assigned_technician_source_ids
                                ),
                                external_metadata=metadata,
                                first_run_id=run_id,
                            ),
                        )
        except ParentResolutionError as error:
            disposition, reason, detail = (
                "unresolved",
                "parent_unresolved",
                str(error),
            )
        except (JobError, MigrationRecordError, SchedulingError, ValueError) as error:
            disposition, reason, detail = (
                "rejected",
                "validation_failed",
                str(error),
            )
        self._record_result(
            run_id,
            "appointment",
            index,
            record.source_id,
            disposition,
            reason,
            detail,
            counts,
            exceptions,
            progress_callback,
        )

    @staticmethod
    def _record_result(
        run_id: UUID,
        entity_type: EntityType,
        index: int,
        source_id: str | None,
        disposition: Disposition,
        reason: str,
        detail: str,
        counts: _EntityCounts,
        exceptions: list[tuple[EntityType, int, str | None, Disposition, str, str]],
        callback: Callable[[MigrationProgress], None] | None,
    ) -> None:
        counts.advance(disposition)
        if disposition != "accepted":
            exceptions.append(
                (entity_type, index, source_id, disposition, reason, detail)
            )
        if callback:
            callback(
                MigrationProgress(
                    run_id=run_id,
                    entity_type=entity_type,
                    source=counts.source,
                    processed=counts.processed,
                    accepted=counts.accepted,
                    rejected=counts.rejected,
                    duplicate=counts.duplicate,
                    unresolved=counts.unresolved,
                )
            )

    async def _finalize(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        run_id: UUID,
        counts: dict[str, _EntityCounts],
        exceptions: list[tuple[EntityType, int, str | None, Disposition, str, str]],
        status: str,
    ) -> MigrationReport:
        total = _EntityCounts(sum(value.source for value in counts.values()))
        for value in counts.values():
            total.processed += value.processed
            total.accepted += value.accepted
            total.rejected += value.rejected
            total.duplicate += value.duplicate
            total.unresolved += value.unresolved
        async with factory() as session, session.begin():
            run = await self._repository.get_run_for_update(session, run_id)
            if run is None:
                raise RuntimeError("Operational migration run disappeared.")
            run.source_count = total.processed
            run.accepted_count = total.accepted
            run.rejected_count = total.rejected
            run.duplicate_count = total.duplicate
            run.unresolved_count = total.unresolved
            run.status = status
            run.completed_at = utc_now()
            for entity_type, value in counts.items():
                progress = await session.scalar(
                    select(OperationalMigrationProgress).where(
                        OperationalMigrationProgress.run_id == run_id,
                        OperationalMigrationProgress.entity_type == entity_type,
                    )
                )
                if progress is None:
                    progress = OperationalMigrationProgress(
                        run_id=run_id,
                        entity_type=entity_type,
                        source_count=value.source,
                        processed_count=value.processed,
                        accepted_count=value.accepted,
                        rejected_count=value.rejected,
                        duplicate_count=value.duplicate,
                        unresolved_count=value.unresolved,
                    )
                    self._repository.add_progress(session, progress)
                else:
                    progress.source_count = value.source
                    progress.processed_count = value.processed
                    progress.accepted_count = value.accepted
                    progress.rejected_count = value.rejected
                    progress.duplicate_count = value.duplicate
                    progress.unresolved_count = value.unresolved
            for (
                entity_type,
                index,
                source_id,
                disposition,
                reason,
                detail,
            ) in exceptions:
                existing_exception = await session.scalar(
                    select(OperationalMigrationException.id).where(
                        OperationalMigrationException.run_id == run_id,
                        OperationalMigrationException.entity_type == entity_type,
                        OperationalMigrationException.record_index == index,
                        OperationalMigrationException.disposition == disposition,
                        OperationalMigrationException.reason_code == reason,
                    )
                )
                if existing_exception is None:
                    self._repository.add_exception(
                        session,
                        OperationalMigrationException(
                            run_id=run_id,
                            entity_type=entity_type,
                            record_index=index,
                            source_id_sha256=(
                                hashlib.sha256(source_id.encode()).hexdigest()
                                if source_id
                                else None
                            ),
                            disposition=disposition,
                            reason_code=reason,
                            detail=detail,
                        ),
                    )
        return MigrationReport(
            run_id=run_id,
            mode=run.mode,
            source=total.processed,
            accepted=total.accepted,
            rejected=total.rejected,
            duplicate=total.duplicate,
            unresolved=total.unresolved,
        )
