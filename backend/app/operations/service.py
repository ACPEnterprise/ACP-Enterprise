from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.commands import CreateJobFromAppointment
from app.jobs.models import Job
from app.jobs.service import JobService, job_service
from app.jobs.types import JobPriority
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
    ) -> None:
        self._scheduling = scheduling
        self._jobs = jobs

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


operations_service = OperationsService()
