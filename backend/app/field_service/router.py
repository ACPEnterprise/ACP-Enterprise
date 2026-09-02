from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.field_service.errors import (
    FieldServiceConflict,
    FieldServiceError,
    FieldServiceNotFound,
)
from app.field_service.mobile_context import mobile_field_context
from app.field_service.schemas import (
    ApprovalInput,
    FieldEquipmentProjection,
    FieldEstimatePresentation,
    FieldHistoryProjection,
    FieldJobState,
    FieldReadinessProjection,
    HandoffInput,
    Itinerary,
    NonBillableInput,
    NoteInput,
)
from app.field_service.service import field_service
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    AssetPermission,
    EstimatePermission,
    JobPermission,
)
from app.platform.permissions.dependencies import (
    require_all_permissions,
    require_permission,
)
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

router = APIRouter(prefix="/api/v1/technician", tags=["Technician Field Service"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Read = Annotated[AuthorizationContext, Depends(require_permission(JobPermission.READ))]
Execute = Annotated[
    AuthorizationContext, Depends(require_permission(JobPermission.EXECUTE))
]
Manage = Annotated[
    AuthorizationContext, Depends(require_permission(JobPermission.MANAGE))
]
AssetRead = Annotated[
    AuthorizationContext,
    Depends(require_all_permissions(JobPermission.READ, AssetPermission.READ)),
]
EstimateRead = Annotated[
    AuthorizationContext,
    Depends(require_all_permissions(JobPermission.READ, EstimatePermission.READ)),
]


def field_error(error: FieldServiceError) -> HTTPException:
    if isinstance(error, FieldServiceNotFound):
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Field Service resource was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_404_NOT_FOUND, failure.detail())
    if isinstance(error, FieldServiceConflict):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Field Service operation conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_409_CONFLICT, failure.detail())
    failure = SafeFailure(
        FailureCode.VALIDATION,
        "Field Service request requires correction.",
        ClientRecovery.USER_CORRECTION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, failure.detail())


@router.get("/itinerary", response_model=Itinerary)
async def itinerary(service_date: date, context: Read, session: Session) -> Itinerary:
    try:
        return await field_service.itinerary(
            session, context=context, service_date=service_date
        )
    except FieldServiceError as error:
        raise field_error(error) from error


@router.get("/jobs/{job_id}", response_model=FieldJobState)
async def job_state(job_id: UUID, context: Read, session: Session) -> FieldJobState:
    try:
        return await field_service.state(session, context=context, job_id=job_id)
    except FieldServiceError as error:
        raise field_error(error) from error


@router.get("/jobs/{job_id}/equipment", response_model=FieldEquipmentProjection)
async def job_equipment(
    job_id: UUID, context: AssetRead, session: Session
) -> FieldEquipmentProjection:
    try:
        return await mobile_field_context.equipment(
            session, context=context, job_id=job_id
        )
    except FieldServiceError as error:
        raise field_error(error) from error


@router.get("/jobs/{job_id}/estimate", response_model=FieldEstimatePresentation)
async def job_estimate(
    job_id: UUID, context: EstimateRead, session: Session
) -> FieldEstimatePresentation:
    try:
        return await mobile_field_context.estimate(
            session, context=context, job_id=job_id
        )
    except FieldServiceError as error:
        raise field_error(error) from error


@router.get("/history", response_model=FieldHistoryProjection)
async def completed_history(
    context: Read,
    session: Session,
    days: Annotated[int, Query(ge=1, le=90)] = 30,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> FieldHistoryProjection:
    # Bounds are enforced here so no client can turn this into Company history.
    try:
        return await mobile_field_context.history(
            session,
            context=context,
            days=days,
            limit=limit,
        )
    except FieldServiceError as error:
        raise field_error(error) from error


@router.get("/readiness", response_model=FieldReadinessProjection)
async def technician_readiness(
    context: AssetRead, session: Session
) -> FieldReadinessProjection:
    try:
        return await mobile_field_context.readiness(session, context=context)
    except FieldServiceError as error:
        raise field_error(error) from error


@router.post("/jobs/{job_id}/notes", response_model=FieldJobState)
async def add_note(
    job_id: UUID, payload: NoteInput, context: Execute, session: Session
) -> FieldJobState:
    try:
        return await field_service.note(
            session, context=context, job_id=job_id, payload=payload
        )
    except FieldServiceError as error:
        raise field_error(error) from error


@router.post("/jobs/{job_id}/customer-approval", response_model=FieldJobState)
async def record_approval(
    job_id: UUID, payload: ApprovalInput, context: Execute, session: Session
) -> FieldJobState:
    try:
        return await field_service.approval(
            session, context=context, job_id=job_id, payload=payload
        )
    except FieldServiceError as error:
        raise field_error(error) from error


@router.post("/jobs/{job_id}/non-billable", response_model=FieldJobState)
async def authorize_non_billable(
    job_id: UUID, payload: NonBillableInput, context: Manage, session: Session
) -> FieldJobState:
    try:
        return await field_service.non_billable(
            session, context=context, job_id=job_id, payload=payload
        )
    except FieldServiceError as error:
        raise field_error(error) from error


@router.post("/jobs/{job_id}/invoice-handoff", response_model=FieldJobState)
async def refresh_invoice_handoff(
    job_id: UUID, payload: HandoffInput, context: Execute, session: Session
) -> FieldJobState:
    try:
        return await field_service.refresh_handoff(
            session, context=context, job_id=job_id, payload=payload
        )
    except FieldServiceError as error:
        raise field_error(error) from error
