from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.field_service.errors import (
    FieldServiceConflict,
    FieldServiceError,
    FieldServiceNotFound,
)
from app.field_service.schemas import (
    ApprovalInput,
    FieldJobState,
    HandoffInput,
    Itinerary,
    NonBillableInput,
    NoteInput,
)
from app.field_service.service import field_service
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import JobPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/technician", tags=["Technician Field Service"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Read = Annotated[AuthorizationContext, Depends(require_permission(JobPermission.READ))]
Execute = Annotated[
    AuthorizationContext, Depends(require_permission(JobPermission.EXECUTE))
]
Manage = Annotated[
    AuthorizationContext, Depends(require_permission(JobPermission.MANAGE))
]


def field_error(error: FieldServiceError) -> HTTPException:
    if isinstance(error, FieldServiceNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, FieldServiceConflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


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
