from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.commands import CreateJobFromAppointment, LinkAppointment
from app.jobs.errors import (
    JobInvalidTransitionError,
    JobNotFoundError,
    JobValidationError,
    JobVersionConflictError,
)
from app.jobs.models import Job
from app.jobs.repository import JobRepository
from app.jobs.service import JobService, job_service
from app.jobs.types import JobPriority, JobStatus
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.models import Appointment
from app.scheduling.service import (
    CreateAppointmentCommand,
    SchedulingService,
    scheduling_service,
)


@dataclass(frozen=True)
class LaunchWorkflowResult:
    request_id: UUID
    appointment: Appointment
    job: Job


class OperationsService:
    """Compose source-domain commands into the launch service workflow.

    Scheduling remains the Appointment owner and Jobs remains the Job owner. A
    stable request identity lets a retry resume after either domain transaction
    without creating a second Appointment or Job.
    """

    def __init__(
        self,
        *,
        scheduling: SchedulingService = scheduling_service,
        jobs: JobService = job_service,
        job_repository: type[JobRepository] = JobRepository,
    ) -> None:
        self._scheduling = scheduling
        self._jobs = jobs
        self._job_repository = job_repository

    async def accept_service_request(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        request_id: UUID,
        appointment: CreateAppointmentCommand,
        job_type_code: str | None,
        priority: JobPriority,
        customer_reported_problem: str | None,
        internal_description: str | None,
    ) -> LaunchWorkflowResult:
        if appointment.idempotency_key != request_id:
            raise ValueError("Appointment identity must match the service request.")
        scheduled = await self._scheduling.create_appointment(
            session, context=context, command=appointment
        )
        job = await self._jobs.create_job_from_appointment(
            session,
            context=context,
            command=CreateJobFromAppointment(
                appointment_id=scheduled.id,
                service_request_id=request_id,
                job_type_code=job_type_code,
                priority=priority,
                customer_reported_problem=customer_reported_problem,
                internal_description=internal_description,
            ),
        )
        return LaunchWorkflowResult(
            request_id=request_id, appointment=scheduled, job=job
        )

    async def schedule_existing_job(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        request_id: UUID,
        job_id: UUID,
        expected_job_version: int,
        appointment: CreateAppointmentCommand,
    ) -> LaunchWorkflowResult:
        """Schedule and link one existing Job through replay-safe domain commands."""
        if appointment.idempotency_key != request_id:
            raise ValueError("Appointment identity must match the schedule request.")
        async with session.begin():
            existing_job = await self._job_repository.get_job(
                session, company_id=context.company.id, job_id=job_id
            )
            if existing_job is None or not context.can_access_branch(
                existing_job.branch_id
            ):
                raise JobNotFoundError(job_id)
            if existing_job.concurrency_version != expected_job_version:
                raise JobVersionConflictError("Job version is stale.")
            if existing_job.status not in {
                JobStatus.DRAFT.value,
                JobStatus.READY.value,
                JobStatus.IN_PROGRESS.value,
                JobStatus.PAUSED.value,
            }:
                raise JobInvalidTransitionError("Job cannot be scheduled in this state.")
            if (
                existing_job.branch_id != appointment.branch_id
                or existing_job.customer_id != appointment.customer_id
                or existing_job.service_location_id != appointment.service_location_id
            ):
                raise JobValidationError(
                    "Schedule request does not match the current Job relationships."
                )
        scheduled = await self._scheduling.create_appointment(
            session, context=context, command=appointment
        )
        job = await self._jobs.link_appointment(
            session,
            context=context,
            command=LinkAppointment(
                job_id=job_id,
                appointment_id=scheduled.id,
                visit_sequence=1,
                expected_version=expected_job_version,
            ),
        )
        return LaunchWorkflowResult(
            request_id=request_id, appointment=scheduled, job=job
        )


operations_service = OperationsService()
