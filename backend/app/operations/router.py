from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.jobs.errors import JobError
from app.jobs.router import translate_job_error
from app.jobs.schemas import JobMutationResponse
from app.operations.schemas import ServiceRequestCreate, ServiceRequestResponse
from app.operations.service import operations_service
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import JobPermission, SchedulingPermission
from app.platform.permissions.dependencies import require_permission
from app.scheduling.errors import SchedulingError
from app.scheduling.router import appointment_response, translate_scheduling_error
from app.scheduling.service import CreateAppointmentCommand

router = APIRouter(prefix="/api/v1/operations", tags=["Operations"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
SchedulingManageContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(SchedulingPermission.MANAGE)),
]
JobsManageContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(JobPermission.MANAGE)),
]


@router.post(
    "/service-requests",
    response_model=ServiceRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Accept a launch service request",
)
async def accept_service_request(
    data: ServiceRequestCreate,
    scheduling_context: SchedulingManageContext,
    jobs_context: JobsManageContext,
    session: DatabaseSession,
) -> ServiceRequestResponse:
    # Both dependencies resolve the same tenant context while independently
    # enforcing the two source-domain permissions required by the workflow.
    context = scheduling_context
    assert context.company.id == jobs_context.company.id
    try:
        result = await operations_service.accept_service_request(
            session,
            context=context,
            request_id=data.request_id,
            appointment=CreateAppointmentCommand(
                idempotency_key=data.request_id,
                branch_id=data.branch_id,
                customer_id=data.customer_id,
                service_location_id=data.service_location_id,
                arrival_window_start_at=data.arrival_window_start_at,
                arrival_window_end_at=data.arrival_window_end_at,
                expected_duration_minutes=data.expected_duration_minutes,
                capacity_units=data.capacity_units,
            ),
            job_type_code=data.job_type_code,
            priority=data.priority,
            customer_reported_problem=data.customer_reported_problem,
            internal_description=data.internal_description,
        )
    except SchedulingError as error:
        raise translate_scheduling_error(error) from error
    except JobError as error:
        raise translate_job_error(error) from error
    return ServiceRequestResponse(
        request_id=result.request_id,
        appointment=appointment_response(result.appointment),
        job=JobMutationResponse.model_validate(result.job),
    )
