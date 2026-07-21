from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import SchedulingPermission
from app.platform.permissions.dependencies import require_permission
from app.scheduling.errors import (
    SchedulingCapacityError,
    SchedulingConflictError,
    SchedulingError,
    SchedulingNotFoundError,
    SchedulingValidationError,
    SchedulingVersionConflictError,
)
from app.scheduling.models import Appointment
from app.scheduling.schemas import (
    AppointmentCancellationRequest,
    AppointmentCreateRequest,
    AppointmentResponse,
    AppointmentRescheduleRequest,
)
from app.scheduling.service import (
    CancelAppointmentCommand,
    CreateAppointmentCommand,
    RescheduleAppointmentCommand,
    scheduling_service,
)
from app.scheduling.types import AppointmentCancellationReason, AppointmentStatus


router = APIRouter(prefix="/api/v1/scheduling", tags=["Scheduling"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
SchedulingManageContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(SchedulingPermission.MANAGE)),
]


def translate_scheduling_error(error: SchedulingError) -> HTTPException:
    if isinstance(error, SchedulingNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduling resource was not found.",
        )
    if isinstance(error, SchedulingVersionConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Appointment version conflicts with the current state.",
        )
    if isinstance(error, SchedulingCapacityError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Requested scheduling capacity or availability is unavailable.",
        )
    if isinstance(error, SchedulingConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scheduling operation conflicts with the current state.",
        )
    if isinstance(error, SchedulingValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Scheduling request violates domain validation rules.",
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Scheduling operation could not be completed.",
    )


def appointment_response(appointment: Appointment) -> AppointmentResponse:
    reservation = appointment.capacity_reservation
    return AppointmentResponse(
        id=appointment.id,
        appointment_number=appointment.appointment_number,
        company_id=appointment.company_id,
        branch_id=appointment.branch_id,
        customer_id=appointment.customer_id,
        service_location_id=appointment.service_location_id,
        status=AppointmentStatus(appointment.status),
        arrival_window_start_at=appointment.arrival_window_start_at,
        arrival_window_end_at=appointment.arrival_window_end_at,
        expected_duration_minutes=appointment.expected_duration_minutes,
        capacity_units=reservation.capacity_units if reservation is not None else None,
        concurrency_version=appointment.concurrency_version,
        reschedule_count=appointment.reschedule_count,
        rescheduled_at=appointment.rescheduled_at,
        cancelled_at=appointment.cancelled_at,
        cancellation_reason_code=(
            AppointmentCancellationReason(appointment.cancellation_reason_code)
            if appointment.cancellation_reason_code is not None
            else None
        ),
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
    )


@router.post(
    "/appointments",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an Appointment",
    response_description="The scheduled Appointment and reserved Branch capacity.",
)
async def create_appointment(
    data: AppointmentCreateRequest,
    context: SchedulingManageContext,
    session: DatabaseSession,
) -> AppointmentResponse:
    try:
        appointment = await scheduling_service.create_appointment(
            session,
            context=context,
            command=CreateAppointmentCommand(
                branch_id=data.branch_id,
                customer_id=data.customer_id,
                service_location_id=data.service_location_id,
                arrival_window_start_at=data.arrival_window_start_at,
                arrival_window_end_at=data.arrival_window_end_at,
                expected_duration_minutes=data.expected_duration_minutes,
                capacity_units=data.capacity_units,
            ),
        )
    except SchedulingError as error:
        raise translate_scheduling_error(error) from error
    return appointment_response(appointment)


@router.post(
    "/appointments/{appointment_id}/cancel",
    response_model=AppointmentResponse,
    summary="Cancel an Appointment",
    response_description="The cancelled Appointment with released capacity.",
)
async def cancel_appointment(
    appointment_id: UUID,
    data: AppointmentCancellationRequest,
    context: SchedulingManageContext,
    session: DatabaseSession,
) -> AppointmentResponse:
    try:
        appointment = await scheduling_service.cancel_appointment(
            session,
            context=context,
            command=CancelAppointmentCommand(
                appointment_id=appointment_id,
                expected_version=data.expected_version,
                reason_code=data.reason_code,
            ),
        )
    except SchedulingError as error:
        raise translate_scheduling_error(error) from error
    return appointment_response(appointment)


@router.post(
    "/appointments/{appointment_id}/reschedule",
    response_model=AppointmentResponse,
    summary="Reschedule an Appointment",
    response_description="The rescheduled Appointment and moved capacity reservation.",
)
async def reschedule_appointment(
    appointment_id: UUID,
    data: AppointmentRescheduleRequest,
    context: SchedulingManageContext,
    session: DatabaseSession,
) -> AppointmentResponse:
    try:
        appointment = await scheduling_service.reschedule_appointment(
            session,
            context=context,
            command=RescheduleAppointmentCommand(
                appointment_id=appointment_id,
                expected_version=data.expected_version,
                arrival_window_start_at=data.arrival_window_start_at,
                arrival_window_end_at=data.arrival_window_end_at,
                expected_duration_minutes=data.expected_duration_minutes,
                capacity_units=data.capacity_units,
                reason_code=data.reason_code,
            ),
        )
    except SchedulingError as error:
        raise translate_scheduling_error(error) from error
    return appointment_response(appointment)
