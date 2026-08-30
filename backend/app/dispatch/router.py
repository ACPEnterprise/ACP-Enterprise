from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.dispatch.errors import (
    DispatchConflict,
    DispatchError,
    DispatchNotFound,
    DispatchValidation,
)
from app.dispatch.schemas import (
    ArrivalStateRequest,
    AssignmentItem,
    AssignmentReasonRequest,
    AssignPrimaryRequest,
    CrewMutationRequest,
    DispatchBoardPage,
    DispatchExceptionRequest,
    ReconcileRequest,
    TechnicianEligibilityItem,
)
from app.dispatch.service import dispatch_service
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import DispatchPermission, JobPermission
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

router = APIRouter(prefix="/api/v1/dispatch", tags=["Dispatch"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(DispatchPermission.READ))
]
ManageContext = Annotated[
    AuthorizationContext, Depends(require_permission(DispatchPermission.MANAGE))
]
ExecuteContext = Annotated[
    AuthorizationContext, Depends(require_permission(JobPermission.EXECUTE))
]


def dispatch_http(error: DispatchError) -> HTTPException:
    if isinstance(error, DispatchNotFound):
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Dispatch resource was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_404_NOT_FOUND, failure.detail())
    if isinstance(error, DispatchConflict):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Dispatch operation conflicts with the current state.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_409_CONFLICT, failure.detail())
    if isinstance(error, DispatchValidation):
        failure = SafeFailure(
            FailureCode.VALIDATION,
            "Dispatch request violates domain validation rules.",
            ClientRecovery.USER_CORRECTION_REQUIRED,
            current_correlation_id(),
        )
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, failure.detail()
        )
    failure = SafeFailure(
        FailureCode.INTERNAL_FAILURE,
        "Dispatch operation could not be completed.",
        ClientRecovery.TERMINAL_FAILURE,
        current_correlation_id(),
    )
    return HTTPException(
        status.HTTP_400_BAD_REQUEST, failure.detail()
    )


@router.get("/board", response_model=DispatchBoardPage)
async def board(
    context: ReadContext,
    session: DatabaseSession,
    start_at: Annotated[AwareDatetime, Query()],
    end_at: Annotated[AwareDatetime, Query()],
    branch_id: UUID | None = None,
) -> DispatchBoardPage:
    try:
        return await dispatch_service.board(
            session,
            context=context,
            start_at=start_at,
            end_at=end_at,
            branch_id=branch_id,
        )
    except DispatchError as error:
        raise dispatch_http(error) from error


@router.get(
    "/appointments/{appointment_id}/eligible-technicians",
    response_model=tuple[TechnicianEligibilityItem, ...],
)
async def eligible(
    appointment_id: UUID, context: ReadContext, session: DatabaseSession
) -> tuple[TechnicianEligibilityItem, ...]:
    try:
        return tuple(
            TechnicianEligibilityItem.model_validate(item)
            for item in await dispatch_service.eligible(
                session, context=context, appointment_id=appointment_id
            )
        )
    except (DispatchError, ValueError) as error:
        raise dispatch_http(
            error
            if isinstance(error, DispatchError)
            else DispatchValidation(str(error))
        ) from error


@router.get("/appointments/{appointment_id}/assignment", response_model=AssignmentItem)
async def detail(
    appointment_id: UUID, context: ReadContext, session: DatabaseSession
) -> AssignmentItem:
    try:
        return await dispatch_service.detail(
            session, context=context, appointment_id=appointment_id
        )
    except DispatchError as error:
        raise dispatch_http(error) from error


@router.post("/appointments/{appointment_id}/assignment", response_model=AssignmentItem)
async def assign(
    appointment_id: UUID,
    request: AssignPrimaryRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> AssignmentItem:
    try:
        return await dispatch_service.assign(
            session,
            context=context,
            appointment_id=appointment_id,
            **request.model_dump(),
        )
    except DispatchError as error:
        raise dispatch_http(error) from error


@router.put(
    "/appointments/{appointment_id}/assignment/primary", response_model=AssignmentItem
)
async def replace(
    appointment_id: UUID,
    request: AssignPrimaryRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> AssignmentItem:
    if request.expected_version is None:
        raise dispatch_http(
            DispatchValidation("Expected version is required for replacement.")
        )
    try:
        return await dispatch_service.replace(
            session,
            context=context,
            appointment_id=appointment_id,
            employee_id=request.employee_id,
            reason=request.reason,
            idempotency_key=request.idempotency_key,
            expected_version=request.expected_version,
        )
    except DispatchError as error:
        raise dispatch_http(error) from error


@router.delete(
    "/appointments/{appointment_id}/assignment/primary", response_model=AssignmentItem
)
async def release(
    appointment_id: UUID,
    request: AssignmentReasonRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> AssignmentItem:
    try:
        return await dispatch_service.release(
            session,
            context=context,
            appointment_id=appointment_id,
            **request.model_dump(),
        )
    except DispatchError as error:
        raise dispatch_http(error) from error


@router.post(
    "/appointments/{appointment_id}/assignment/crew", response_model=AssignmentItem
)
async def add_crew(
    appointment_id: UUID,
    request: CrewMutationRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> AssignmentItem:
    try:
        return await dispatch_service.crew(
            session,
            context=context,
            appointment_id=appointment_id,
            **request.model_dump(),
        )
    except DispatchError as error:
        raise dispatch_http(error) from error


@router.delete(
    "/appointments/{appointment_id}/assignment/crew", response_model=AssignmentItem
)
async def remove_crew(
    appointment_id: UUID,
    request: CrewMutationRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> AssignmentItem:
    try:
        return await dispatch_service.crew(
            session,
            context=context,
            appointment_id=appointment_id,
            remove=True,
            **request.model_dump(),
        )
    except DispatchError as error:
        raise dispatch_http(error) from error


@router.post(
    "/appointments/{appointment_id}/assignment/reconciliation-required",
    response_model=AssignmentItem,
)
async def require_reconciliation(
    appointment_id: UUID,
    request: AssignmentReasonRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> AssignmentItem:
    try:
        return await dispatch_service.reconcile(
            session,
            context=context,
            appointment_id=appointment_id,
            **request.model_dump(),
        )
    except DispatchError as error:
        raise dispatch_http(error) from error


@router.post(
    "/appointments/{appointment_id}/assignment/reconcile", response_model=AssignmentItem
)
async def resolve_reconciliation(
    appointment_id: UUID,
    request: ReconcileRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> AssignmentItem:
    try:
        return await dispatch_service.reconcile(
            session,
            context=context,
            appointment_id=appointment_id,
            **request.model_dump(),
        )
    except DispatchError as error:
        raise dispatch_http(error) from error


@router.post(
    "/appointments/{appointment_id}/assignment/exceptions",
    response_model=AssignmentItem,
)
async def report_exception(
    appointment_id: UUID,
    request: DispatchExceptionRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> AssignmentItem:
    try:
        return await dispatch_service.report_exception(
            session,
            context=context,
            appointment_id=appointment_id,
            **request.model_dump(),
        )
    except DispatchError as error:
        raise dispatch_http(error) from error


@router.post(
    "/appointments/{appointment_id}/assignment/arrival",
    response_model=AssignmentItem,
)
async def record_arrival(
    appointment_id: UUID,
    request: ArrivalStateRequest,
    context: ExecuteContext,
    session: DatabaseSession,
) -> AssignmentItem:
    try:
        return await dispatch_service.record_arrival(
            session,
            context=context,
            appointment_id=appointment_id,
            **request.model_dump(),
        )
    except DispatchError as error:
        raise dispatch_http(error) from error
