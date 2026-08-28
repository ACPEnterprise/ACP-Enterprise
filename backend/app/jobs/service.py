import re
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.reference import (
    CustomerReferenceService,
    customer_reference_service,
)
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.jobs.commands import (
    UNSET,
    ActivateJob,
    CancelJob,
    CompleteJob,
    CreateJob,
    CreateJobFromAppointment,
    LinkAppointment,
    MigrateJob,
    PauseJob,
    ReopenJob,
    ResumeJob,
    StartJob,
    UnsetType,
    UpdateJob,
)
from app.jobs.errors import (
    AppointmentAlreadyLinkedError,
    AppointmentNotFoundError,
    JobInvalidTransitionError,
    JobNotFoundError,
    JobReferenceNotFoundError,
    JobValidationError,
    JobVersionConflictError,
)
from app.jobs.guards import (
    JobCancellationGuard,
    JobCompletionGuard,
    JobExecutionGuard,
    JobGuardContext,
    JobReopeningGuard,
)
from app.jobs.models import Job, JobAppointmentLink
from app.jobs.repository import JobRepository, job_repository
from app.jobs.types import JobPriority, JobStatus
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.reference import (
    SchedulingReferenceService,
    scheduling_reference_service,
)
from app.scheduling.types import AppointmentReference, AppointmentStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobService:
    """Sole transaction and mutation owner for the Job aggregate."""

    def __init__(
        self,
        repository: JobRepository = job_repository,
        *,
        scheduling_references: SchedulingReferenceService = scheduling_reference_service,
        customer_references: CustomerReferenceService = customer_reference_service,
        completion_guards: Sequence[JobCompletionGuard] = (),
        execution_guards: Sequence[JobExecutionGuard] = (),
        cancellation_guards: Sequence[JobCancellationGuard] = (),
        reopening_guards: Sequence[JobReopeningGuard] = (),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._scheduling_references = scheduling_references
        self._customer_references = customer_references
        self._completion_guards = tuple(completion_guards)
        self._execution_guards = tuple(execution_guards)
        self._cancellation_guards = tuple(cancellation_guards)
        self._reopening_guards = tuple(reopening_guards)
        self._clock = clock

    async def create_job(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: CreateJob,
    ) -> Job:
        self._require_branch(context, command.branch_id)
        metadata = self._validate_creation_metadata(command)
        occurred_at, correlation_id = self._operation_identity()
        async with session.begin():
            await self._require_customer_reference(
                session,
                context=context,
                customer_id=command.customer_id,
                service_location_id=command.service_location_id,
            )
            job = await self._create(
                session,
                context=context,
                branch_id=command.branch_id,
                customer_id=command.customer_id,
                service_location_id=command.service_location_id,
                metadata=metadata,
                occurred_at=occurred_at,
            )
            self._stage_event(
                session,
                context=context,
                job=job,
                event_type=EventType.JOB_CREATED,
                occurred_at=occurred_at,
                correlation_id=correlation_id,
                payload=self._created_payload(job),
            )
        return job

    async def stage_estimate_conversion_job(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        customer_id: UUID,
        service_location_id: UUID,
        actor_user_id: UUID,
        job_type_code: str | None,
        customer_reported_problem: str | None,
        internal_description: str | None,
        occurred_at: datetime,
    ) -> Job:
        """Stage a draft Job in the caller's atomic Estimate conversion."""
        metadata = self._validate_creation_metadata(
            CreateJob(
                branch_id=branch_id,
                customer_id=customer_id,
                service_location_id=service_location_id,
                job_type_code=job_type_code,
                customer_reported_problem=customer_reported_problem,
                internal_description=internal_description,
            )
        )
        job = Job(
            id=uuid4(),
            company_id=company_id,
            branch_id=branch_id,
            job_number=await self._repository.next_job_number(
                session, company_id=company_id
            ),
            customer_id=customer_id,
            service_location_id=service_location_id,
            status=JobStatus.DRAFT.value,
            concurrency_version=1,
            created_at=occurred_at,
            updated_at=occurred_at,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
            **metadata,
        )
        return await self._repository.create_job(session, job=job)

    async def stage_migrated_job(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: MigrateJob,
    ) -> Job:
        """Stage one validated historical Job in the caller's transaction."""
        self._require_branch(context, command.branch_id)
        try:
            status = JobStatus(command.status)
        except ValueError as error:
            raise JobValidationError("Migrated Job status is invalid.") from error
        if status in {JobStatus.PAUSED, JobStatus.CANCELLED}:
            raise JobValidationError(
                "Paused and cancelled Jobs require lifecycle details not supported "
                "by this migration phase."
            )
        if status is not JobStatus.DRAFT and command.activated_at is None:
            raise JobValidationError("Activated timestamp is required for this status.")
        if status in {JobStatus.IN_PROGRESS, JobStatus.COMPLETED} and (
            command.started_at is None
        ):
            raise JobValidationError("Started timestamp is required for this status.")
        if status is JobStatus.COMPLETED and command.completed_at is None:
            raise JobValidationError("Completion timestamp is required.")
        timestamps = [
            value
            for value in (
                command.activated_at,
                command.started_at,
                command.completed_at,
            )
            if value is not None
        ]
        if any(value.tzinfo is None for value in timestamps):
            raise JobValidationError("Migrated Job timestamps must be timezone-aware.")
        if timestamps != sorted(timestamps):
            raise JobValidationError("Migrated Job timestamps are out of order.")
        await self._require_customer_reference(
            session,
            context=context,
            customer_id=command.customer_id,
            service_location_id=command.service_location_id,
        )
        now = self._clock()
        metadata = self._validate_creation_metadata(
            CreateJob(
                branch_id=command.branch_id,
                customer_id=command.customer_id,
                service_location_id=command.service_location_id,
                priority=command.priority,
                customer_reported_problem=command.customer_reported_problem,
                internal_description=command.internal_description,
            )
        )
        number = await self._repository.next_job_number(
            session, company_id=context.company.id
        )
        job = Job(
            id=uuid4(),
            company_id=context.company.id,
            branch_id=command.branch_id,
            job_number=number,
            customer_id=command.customer_id,
            service_location_id=command.service_location_id,
            status=status.value,
            concurrency_version=1,
            activated_at=command.activated_at,
            started_at=command.started_at,
            completed_at=command.completed_at,
            completed_by_user_id=(
                context.user.id if status is JobStatus.COMPLETED else None
            ),
            created_at=command.activated_at or now,
            updated_at=command.completed_at
            or command.started_at
            or command.activated_at
            or now,
            created_by_user_id=context.user.id,
            updated_by_user_id=context.user.id,
            **metadata,
        )
        await self._repository.create_job(session, job=job)
        self._stage_event(
            session,
            context=context,
            job=job,
            event_type=EventType.JOB_MIGRATED,
            occurred_at=now,
            correlation_id=uuid4(),
            payload={
                "job_number": job.job_number,
                "status": job.status,
                "origin": "migration",
            },
        )
        return job

    async def stage_migrated_appointment_link(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job: Job,
        appointment: AppointmentReference,
        visit_sequence: int,
    ) -> None:
        """Stage a validated migrated Job/Appointment association."""
        self._require_branch(context, job.branch_id)
        self._require_matching_appointment(job, appointment)
        await self._link(
            session,
            context=context,
            job=job,
            appointment=appointment,
            visit_sequence=visit_sequence,
            occurred_at=self._clock(),
            increment_version=False,
        )

    async def create_job_from_appointment(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: CreateJobFromAppointment,
    ) -> Job:
        metadata = self._validate_creation_metadata(command)
        occurred_at, correlation_id = self._operation_identity()
        async with session.begin():
            appointment = await self._locked_appointment(
                session, context=context, appointment_id=command.appointment_id
            )
            self._validate_appointment_eligibility(appointment)
            links = await self._repository.get_links_for_appointment(
                session,
                company_id=context.company.id,
                appointment_id=appointment.id,
            )
            if links:
                linked_job = await self._repository.get_job_for_update(
                    session,
                    company_id=context.company.id,
                    job_id=links[0].job_id,
                )
                if (
                    linked_job is not None
                    and links[0].visit_sequence == 1
                    and self._matches_creation_retry(
                        linked_job, appointment=appointment, metadata=metadata
                    )
                ):
                    return linked_job
                raise AppointmentAlreadyLinkedError(
                    "Appointment is already linked under the current Job policy."
                )
            await self._require_customer_reference(
                session,
                context=context,
                customer_id=appointment.customer_id,
                service_location_id=appointment.service_location_id,
            )
            job = await self._create(
                session,
                context=context,
                branch_id=appointment.branch_id,
                customer_id=appointment.customer_id,
                service_location_id=appointment.service_location_id,
                metadata=metadata,
                occurred_at=occurred_at,
            )
            await self._link(
                session,
                context=context,
                job=job,
                appointment=appointment,
                visit_sequence=1,
                occurred_at=occurred_at,
                increment_version=False,
            )
            self._stage_event(
                session,
                context=context,
                job=job,
                event_type=EventType.JOB_CREATED,
                occurred_at=occurred_at,
                correlation_id=correlation_id,
                payload=self._created_payload(job),
            )
            self._stage_link_event(
                session,
                context=context,
                job=job,
                appointment_id=appointment.id,
                visit_sequence=1,
                occurred_at=occurred_at,
                correlation_id=correlation_id,
            )
            if command.service_request_id is not None:
                self._stage_event(
                    session,
                    context=context,
                    job=job,
                    event_type=EventType.OPERATIONS_SERVICE_REQUEST_ACCEPTED,
                    occurred_at=occurred_at,
                    correlation_id=command.service_request_id,
                    payload={
                        "service_request_id": str(command.service_request_id),
                        "customer_id": str(job.customer_id),
                        "service_location_id": str(job.service_location_id),
                        "appointment_id": str(appointment.id),
                        "job_id": str(job.id),
                        "status": "accepted",
                        "schema_version": 1,
                    },
                )
        return job

    async def update_job(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: UpdateJob,
    ) -> Job:
        occurred_at, correlation_id = self._operation_identity()
        async with session.begin():
            job = await self._locked_job(
                session, context=context, job_id=command.job_id
            )
            self._check_version(job, command.expected_version)
            changes = self._metadata_changes(command)
            reference_change = (
                "customer_id" in changes or "service_location_id" in changes
            )
            if reference_change:
                if (
                    job.status != JobStatus.DRAFT.value
                    or await self._repository.has_appointment_links(
                        session, company_id=context.company.id, job_id=job.id
                    )
                ):
                    raise JobInvalidTransitionError(
                        "Customer and Service Location cannot be changed in this state."
                    )
                customer_id = changes.get("customer_id", job.customer_id)
                location_id = changes.get(
                    "service_location_id", job.service_location_id
                )
                assert isinstance(customer_id, UUID)
                assert isinstance(location_id, UUID)
                await self._require_customer_reference(
                    session,
                    context=context,
                    customer_id=customer_id,
                    service_location_id=location_id,
                )
            if job.status not in {JobStatus.DRAFT.value, JobStatus.READY.value}:
                raise JobInvalidTransitionError(
                    "Job metadata cannot be changed in this state."
                )
            changed = self._repository.update_job_metadata(
                job,
                changes=changes,
                actor_user_id=context.user.id,
                updated_at=occurred_at,
            )
            if changed:
                self._stage_event(
                    session,
                    context=context,
                    job=job,
                    event_type=EventType.JOB_UPDATED,
                    occurred_at=occurred_at,
                    correlation_id=correlation_id,
                    payload={
                        "changed_fields": list(changed),
                        "version": job.concurrency_version,
                    },
                )
        return job

    async def activate_job(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ActivateJob,
    ) -> Job:
        return await self._transition(
            session,
            context=context,
            job_id=command.job_id,
            expected_version=command.expected_version,
            from_status=JobStatus.DRAFT,
            event_type=EventType.JOB_ACTIVATED,
            mutate=self._repository.activate_job,
        )

    async def link_appointment(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: LinkAppointment,
    ) -> Job:
        if command.visit_sequence < 1:
            raise JobValidationError("Visit sequence must be positive.")
        occurred_at, correlation_id = self._operation_identity()
        async with session.begin():
            appointment = await self._locked_appointment(
                session, context=context, appointment_id=command.appointment_id
            )
            self._validate_appointment_eligibility(appointment)
            job = await self._locked_job(
                session, context=context, job_id=command.job_id
            )
            links = await self._repository.get_links_for_appointment(
                session, company_id=context.company.id, appointment_id=appointment.id
            )
            if links:
                identical = any(
                    link.job_id == job.id
                    and link.visit_sequence == command.visit_sequence
                    for link in links
                )
                if identical:
                    return job
                raise AppointmentAlreadyLinkedError(
                    "Appointment is already linked under the current Job policy."
                )
            self._check_version(job, command.expected_version)
            if job.status not in {JobStatus.DRAFT.value, JobStatus.READY.value}:
                raise JobInvalidTransitionError(
                    "Appointment cannot be linked in this state."
                )
            self._require_matching_appointment(job, appointment)
            job_links = await self._repository.list_appointment_links(
                session, company_id=context.company.id, job_id=job.id
            )
            if any(link.visit_sequence == command.visit_sequence for link in job_links):
                raise JobValidationError("Visit sequence is already used by this Job.")
            await self._link(
                session,
                context=context,
                job=job,
                appointment=appointment,
                visit_sequence=command.visit_sequence,
                occurred_at=occurred_at,
                increment_version=True,
            )
            self._stage_link_event(
                session,
                context=context,
                job=job,
                appointment_id=appointment.id,
                visit_sequence=command.visit_sequence,
                occurred_at=occurred_at,
                correlation_id=correlation_id,
            )
        return job

    async def start_job(
        self, session: AsyncSession, *, context: AuthorizationContext, command: StartJob
    ) -> Job:
        return await self._transition(
            session,
            context=context,
            job_id=command.job_id,
            expected_version=command.expected_version,
            from_status=JobStatus.READY,
            event_type=EventType.JOB_STARTED,
            mutate=self._repository.start_job,
            action="start",
        )

    async def pause_job(
        self, session: AsyncSession, *, context: AuthorizationContext, command: PauseJob
    ) -> Job:
        occurred_at, correlation_id = self._operation_identity()
        async with session.begin():
            job = await self._locked_job(
                session, context=context, job_id=command.job_id
            )
            if job.status == JobStatus.PAUSED.value:
                if job.pause_reason_code == command.reason_code.value:
                    return job
                raise JobInvalidTransitionError("Job is paused for another reason.")
            self._check_version(job, command.expected_version)
            self._require_status(job, JobStatus.IN_PROGRESS)
            guard_context = self._guard_context(job)
            for guard in self._execution_guards:
                await guard.validate_execution(
                    session, context=context, job=guard_context, action="pause"
                )
            self._repository.pause_job(
                job,
                reason_code=command.reason_code.value,
                actor_user_id=context.user.id,
                occurred_at=occurred_at,
            )
            self._stage_transition_event(
                session,
                context=context,
                job=job,
                event_type=EventType.JOB_PAUSED,
                old_status=JobStatus.IN_PROGRESS.value,
                occurred_at=occurred_at,
                correlation_id=correlation_id,
                reason_code=command.reason_code.value,
            )
        return job

    async def resume_job(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ResumeJob,
    ) -> Job:
        return await self._transition(
            session,
            context=context,
            job_id=command.job_id,
            expected_version=command.expected_version,
            from_status=JobStatus.PAUSED,
            event_type=EventType.JOB_RESUMED,
            mutate=self._repository.resume_job,
            action="resume",
        )

    async def complete_job(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: CompleteJob,
    ) -> Job:
        occurred_at, correlation_id = self._operation_identity()
        async with session.begin():
            job = await self._locked_job(
                session, context=context, job_id=command.job_id
            )
            if job.status == JobStatus.COMPLETED.value:
                if job.completed_by_user_id == context.user.id:
                    return job
                raise JobInvalidTransitionError(
                    "Job was completed by another operation."
                )
            self._check_version(job, command.expected_version)
            self._require_status(job, JobStatus.IN_PROGRESS)
            guard_context = self._guard_context(job)
            for guard in self._completion_guards:
                await guard.validate_completion(
                    session,
                    context=context,
                    job=guard_context,
                    correlation_id=correlation_id,
                )
            self._repository.complete_job(
                job, actor_user_id=context.user.id, occurred_at=occurred_at
            )
            self._stage_transition_event(
                session,
                context=context,
                job=job,
                event_type=EventType.JOB_COMPLETED,
                old_status=JobStatus.IN_PROGRESS.value,
                occurred_at=occurred_at,
                correlation_id=correlation_id,
            )
        return job

    async def cancel_job(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: CancelJob,
    ) -> Job:
        occurred_at, correlation_id = self._operation_identity()
        async with session.begin():
            job = await self._locked_job(
                session, context=context, job_id=command.job_id
            )
            if job.status == JobStatus.CANCELLED.value:
                if job.cancellation_reason_code == command.reason_code.value:
                    return job
                raise JobInvalidTransitionError("Job was cancelled for another reason.")
            self._check_version(job, command.expected_version)
            if job.status not in {JobStatus.DRAFT.value, JobStatus.READY.value}:
                raise JobInvalidTransitionError(
                    "Job cannot be cancelled from this state."
                )
            old_status = job.status
            guard_context = self._guard_context(job)
            for guard in self._cancellation_guards:
                await guard.validate_cancellation(
                    session, context=context, job=guard_context
                )
            self._repository.cancel_job(
                job,
                reason_code=command.reason_code.value,
                actor_user_id=context.user.id,
                occurred_at=occurred_at,
            )
            self._stage_transition_event(
                session,
                context=context,
                job=job,
                event_type=EventType.JOB_CANCELLED,
                old_status=old_status,
                occurred_at=occurred_at,
                correlation_id=correlation_id,
                reason_code=command.reason_code.value,
            )
        return job

    async def reopen_job(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ReopenJob,
    ) -> Job:
        occurred_at, correlation_id = self._operation_identity()
        async with session.begin():
            job = await self._locked_job(
                session, context=context, job_id=command.job_id
            )
            self._check_version(job, command.expected_version)
            if job.status not in {JobStatus.COMPLETED.value, JobStatus.CANCELLED.value}:
                raise JobInvalidTransitionError(
                    "Job cannot be reopened from this state."
                )
            old_status = job.status
            guard_context = self._guard_context(job)
            for guard in self._reopening_guards:
                await guard.validate_reopening(
                    session, context=context, job=guard_context
                )
            self._repository.reopen_job(
                job, actor_user_id=context.user.id, occurred_at=occurred_at
            )
            self._stage_transition_event(
                session,
                context=context,
                job=job,
                event_type=EventType.JOB_REOPENED,
                old_status=old_status,
                occurred_at=occurred_at,
                correlation_id=correlation_id,
                reason_code=command.reason_code.value,
            )
        return job

    async def _transition(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        expected_version: int,
        from_status: JobStatus,
        event_type: EventType,
        mutate: Callable[..., None],
        action: str | None = None,
    ) -> Job:
        occurred_at, correlation_id = self._operation_identity()
        async with session.begin():
            job = await self._locked_job(session, context=context, job_id=job_id)
            self._check_version(job, expected_version)
            self._require_status(job, from_status)
            if action:
                guard_context = self._guard_context(job)
                for guard in self._execution_guards:
                    await guard.validate_execution(
                        session, context=context, job=guard_context, action=action
                    )
            mutate(job, actor_user_id=context.user.id, occurred_at=occurred_at)
            self._stage_transition_event(
                session,
                context=context,
                job=job,
                event_type=event_type,
                old_status=from_status.value,
                occurred_at=occurred_at,
                correlation_id=correlation_id,
            )
        return job

    async def _create(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID,
        customer_id: UUID,
        service_location_id: UUID,
        metadata: dict[str, object],
        occurred_at: datetime,
    ) -> Job:
        number = await self._repository.next_job_number(
            session, company_id=context.company.id
        )
        job = Job(
            id=uuid4(),
            company_id=context.company.id,
            branch_id=branch_id,
            job_number=number,
            customer_id=customer_id,
            service_location_id=service_location_id,
            status=JobStatus.DRAFT.value,
            concurrency_version=1,
            created_at=occurred_at,
            updated_at=occurred_at,
            created_by_user_id=context.user.id,
            updated_by_user_id=context.user.id,
            **metadata,
        )
        return await self._repository.create_job(session, job=job)

    async def _link(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job: Job,
        appointment: AppointmentReference,
        visit_sequence: int,
        occurred_at: datetime,
        increment_version: bool,
    ) -> None:
        await self._repository.create_appointment_link(
            session,
            link=JobAppointmentLink(
                company_id=context.company.id,
                branch_id=job.branch_id,
                job_id=job.id,
                appointment_id=appointment.id,
                visit_sequence=visit_sequence,
                linked_at=occurred_at,
                linked_by_user_id=context.user.id,
            ),
        )
        if increment_version:
            self._repository.mark_appointment_linked(
                job, actor_user_id=context.user.id, occurred_at=occurred_at
            )

    async def _locked_job(
        self, session: AsyncSession, *, context: AuthorizationContext, job_id: UUID
    ) -> Job:
        job = await self._repository.get_job_for_update(
            session, company_id=context.company.id, job_id=job_id
        )
        if job is None:
            raise JobNotFoundError(job_id)
        self._require_branch(context, job.branch_id)
        return job

    async def _locked_appointment(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        appointment_id: UUID,
    ) -> AppointmentReference:
        appointment = await self._scheduling_references.get_appointment_reference(
            session,
            company_id=context.company.id,
            appointment_id=appointment_id,
            for_update=True,
        )
        if appointment is None:
            raise AppointmentNotFoundError(appointment_id)
        self._require_branch(context, appointment.branch_id)
        return appointment

    async def _require_customer_reference(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
        service_location_id: UUID,
    ) -> None:
        reference = await self._customer_references.get_service_location_reference(
            session,
            company_id=context.company.id,
            customer_id=customer_id,
            service_location_id=service_location_id,
            for_update=True,
        )
        if reference is None:
            raise JobReferenceNotFoundError(
                "Customer or Service Location was not found."
            )

    @staticmethod
    def _require_branch(context: AuthorizationContext, branch_id: UUID) -> None:
        if not context.can_access_branch(branch_id):
            raise JobNotFoundError(branch_id)

    @staticmethod
    def _check_version(job: Job, expected_version: int) -> None:
        if expected_version < 1 or job.concurrency_version != expected_version:
            raise JobVersionConflictError("Job version is stale.")

    @staticmethod
    def _require_status(job: Job, status: JobStatus) -> None:
        if job.status != status.value:
            raise JobInvalidTransitionError(f"Job cannot transition from {job.status}.")

    @staticmethod
    def _validate_appointment_eligibility(appointment: AppointmentReference) -> None:
        if appointment.status not in {
            AppointmentStatus.DRAFT,
            AppointmentStatus.SCHEDULED,
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.COMPLETED,
        }:
            raise JobInvalidTransitionError(
                "Appointment is not eligible for Job linking."
            )

    @staticmethod
    def _require_matching_appointment(
        job: Job, appointment: AppointmentReference
    ) -> None:
        if (
            job.company_id != appointment.company_id
            or job.branch_id != appointment.branch_id
            or job.customer_id != appointment.customer_id
            or job.service_location_id != appointment.service_location_id
        ):
            raise JobReferenceNotFoundError("Appointment is not valid for this Job.")

    @staticmethod
    def _validate_creation_metadata(
        command: CreateJob | CreateJobFromAppointment,
    ) -> dict[str, object]:
        return {
            "job_type_code": JobService._validate_type_code(command.job_type_code),
            "priority": JobService._validate_priority(command.priority),
            "customer_reported_problem": JobService._validate_optional_text(
                command.customer_reported_problem
            ),
            "internal_description": JobService._validate_optional_text(
                command.internal_description
            ),
        }

    @staticmethod
    def _metadata_changes(command: UpdateJob) -> dict[str, object]:
        changes: dict[str, object] = {}
        for field in (
            "customer_id",
            "service_location_id",
            "job_type_code",
            "priority",
            "customer_reported_problem",
            "internal_description",
        ):
            value = getattr(command, field)
            if value is UNSET or isinstance(value, UnsetType):
                continue
            if field == "job_type_code":
                value = JobService._validate_type_code(value)
            elif field == "priority":
                value = JobService._validate_priority(value)
            elif field in {"customer_reported_problem", "internal_description"}:
                value = JobService._validate_optional_text(value)
            changes[field] = value
        return changes

    @staticmethod
    def _validate_type_code(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not re.fullmatch(
            r"[a-z][a-z0-9_]{0,63}", value
        ):
            raise JobValidationError("Job type code is invalid.")
        return value

    @staticmethod
    def _validate_priority(value: object) -> str:
        if not isinstance(value, (str, JobPriority)):
            raise JobValidationError("Job priority is invalid.")
        try:
            return JobPriority(value).value
        except (TypeError, ValueError) as error:
            raise JobValidationError("Job priority is invalid.") from error

    @staticmethod
    def _validate_optional_text(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise JobValidationError("Job text values cannot be blank.")
        return value.strip()

    @staticmethod
    def _matches_creation_retry(
        job: Job, *, appointment: AppointmentReference, metadata: dict[str, object]
    ) -> bool:
        return (
            job.branch_id == appointment.branch_id
            and job.customer_id == appointment.customer_id
            and job.service_location_id == appointment.service_location_id
            and all(getattr(job, field) == value for field, value in metadata.items())
        )

    @staticmethod
    def _guard_context(job: Job) -> JobGuardContext:
        return JobGuardContext(
            job_id=job.id,
            company_id=job.company_id,
            branch_id=job.branch_id,
            customer_id=job.customer_id,
            service_location_id=job.service_location_id,
            status=job.status,
            concurrency_version=job.concurrency_version,
        )

    def _operation_identity(self) -> tuple[datetime, UUID]:
        return self._clock(), uuid4()

    @staticmethod
    def _created_payload(job: Job) -> dict[str, object]:
        return {
            "job_number": job.job_number,
            "status": job.status,
            "priority": job.priority,
            "job_type_code": job.job_type_code,
            "version": job.concurrency_version,
            "schema_version": 1,
        }

    @staticmethod
    def _stage_event(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job: Job,
        event_type: EventType,
        occurred_at: datetime,
        correlation_id: UUID,
        payload: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="job",
                entity_id=job.id,
                company_id=context.company.id,
                branch_id=job.branch_id,
                user_id=context.user.id,
                payload=payload,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
            ),
        )

    def _stage_transition_event(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job: Job,
        event_type: EventType,
        old_status: str,
        occurred_at: datetime,
        correlation_id: UUID,
        reason_code: str | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "old_status": old_status,
            "new_status": job.status,
            "version": job.concurrency_version,
            "schema_version": 1,
        }
        if reason_code is not None:
            payload["reason_code"] = reason_code
        self._stage_event(
            session,
            context=context,
            job=job,
            event_type=event_type,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            payload=payload,
        )

    def _stage_link_event(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job: Job,
        appointment_id: UUID,
        visit_sequence: int,
        occurred_at: datetime,
        correlation_id: UUID,
    ) -> None:
        self._stage_event(
            session,
            context=context,
            job=job,
            event_type=EventType.JOB_APPOINTMENT_LINKED,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            payload={
                "appointment_id": str(appointment_id),
                "visit_sequence": visit_sequence,
                "version": job.concurrency_version,
                "schema_version": 1,
            },
        )


from app.field_service.guards import field_job_guard

job_service = JobService(
    completion_guards=(field_job_guard,), execution_guards=(field_job_guard,)
)
