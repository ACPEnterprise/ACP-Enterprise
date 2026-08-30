from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    AccountsPayablePermission,
    PurchasingPermission,
)
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

from .errors import (
    ProcurementMatchingConflict,
    ProcurementMatchingError,
    ProcurementMatchingNotFound,
)
from .schemas import (
    EvaluateMatchCommand,
    MatchCandidateItem,
    MatchItem,
    ResolveMatchExceptionCommand,
    VendorPerformanceReport,
)
from .service import procurement_matching_service

router = APIRouter(prefix="/api/v1/procurement-matching", tags=["Procurement Matching"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Read = Annotated[
    AuthorizationContext, Depends(require_permission(AccountsPayablePermission.READ))
]
Review = Annotated[
    AuthorizationContext,
    Depends(require_permission(AccountsPayablePermission.MATCH_REVIEW)),
]
PurchasingRead = Annotated[
    AuthorizationContext, Depends(require_permission(PurchasingPermission.READ))
]


def http_error(error: ProcurementMatchingError) -> HTTPException:
    if isinstance(error, ProcurementMatchingNotFound):
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Procurement matching resource was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_404_NOT_FOUND, failure.detail())
    if isinstance(error, ProcurementMatchingConflict):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Procurement matching operation conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_409_CONFLICT, failure.detail())
    failure = SafeFailure(
        FailureCode.VALIDATION,
        "Procurement matching request requires correction.",
        ClientRecovery.USER_CORRECTION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, failure.detail())


@router.get("/candidates", response_model=tuple[MatchCandidateItem, ...])
async def match_candidates(
    context: Read, session: Session
) -> tuple[MatchCandidateItem, ...]:
    return await procurement_matching_service.candidates(
        session, context=context
    )


@router.post("/matches", response_model=MatchItem, status_code=status.HTTP_201_CREATED)
async def evaluate_match(
    payload: EvaluateMatchCommand, context: Review, session: Session
) -> MatchItem:
    try:
        return await procurement_matching_service.evaluate(
            session, context=context, payload=payload
        )
    except ProcurementMatchingError as error:
        raise http_error(error) from error


@router.get("/matches/{match_id}", response_model=MatchItem)
async def get_match(match_id: UUID, context: Read, session: Session) -> MatchItem:
    try:
        return await procurement_matching_service.get(
            session, context=context, match_id=match_id
        )
    except ProcurementMatchingError as error:
        raise http_error(error) from error


@router.post(
    "/matches/{match_id}/exceptions/{exception_id}/resolve", response_model=MatchItem
)
async def resolve_match_exception(
    match_id: UUID,
    exception_id: UUID,
    payload: ResolveMatchExceptionCommand,
    context: Review,
    session: Session,
) -> MatchItem:
    try:
        return await procurement_matching_service.resolve(
            session,
            context=context,
            match_id=match_id,
            exception_id=exception_id,
            payload=payload,
        )
    except ProcurementMatchingError as error:
        raise http_error(error) from error


@router.get("/vendor-performance", response_model=VendorPerformanceReport)
async def vendor_performance(
    evaluated_at: datetime,
    context: PurchasingRead,
    session: Session,
    branch_id: UUID | None = None,
) -> VendorPerformanceReport:
    try:
        return await procurement_matching_service.vendor_performance(
            session,
            context=context,
            evaluated_at=evaluated_at,
            branch_id=branch_id,
        )
    except ProcurementMatchingError as error:
        raise http_error(error) from error
