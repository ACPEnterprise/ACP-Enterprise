from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCommandPermission
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

from .contracts import EngineeringReviewState
from .errors import (
    EngineeringReviewConflictError,
    EngineeringReviewDigestMismatchError,
    EngineeringReviewIneligibleError,
    EngineeringReviewNotFoundError,
)
from .records import DecideEngineeringReview
from .schemas import (
    EngineeringReviewDecisionRequest,
    EngineeringReviewListResponse,
    EngineeringReviewPackageResponse,
    EngineeringReviewSummary,
)
from .service import engineering_review_service

router = APIRouter(
    prefix="/api/v1/engineering/reviews",
    tags=["Engineering Owner Review"],
)
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringCommandPermission.READ)),
]
ApproveContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringCommandPermission.APPROVE)),
]


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, EngineeringReviewNotFoundError):
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Engineering review was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_404_NOT_FOUND, failure.detail())
    if isinstance(
        error, (EngineeringReviewConflictError, EngineeringReviewDigestMismatchError)
    ):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Engineering review conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_409_CONFLICT, failure.detail())
    failure = SafeFailure(
        FailureCode.VALIDATION,
        "Engineering review request requires correction.",
        ClientRecovery.USER_CORRECTION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, failure.detail())


@router.post(
    "/commands/{command_id}",
    response_model=EngineeringReviewPackageResponse,
    summary="Prepare an immutable owner-review package",
)
async def prepare_review(
    command_id: UUID,
    context: ApproveContext,
    session: DatabaseSession,
) -> EngineeringReviewPackageResponse:
    try:
        package = await engineering_review_service.prepare(
            session,
            context=context,
            command_id=command_id,
        )
    except (
        EngineeringReviewNotFoundError,
        EngineeringReviewConflictError,
        EngineeringReviewDigestMismatchError,
        EngineeringReviewIneligibleError,
    ) as error:
        raise _http_error(error) from error
    return EngineeringReviewPackageResponse.model_validate(package)


@router.get("", response_model=EngineeringReviewListResponse)
async def list_reviews(
    context: ReadContext,
    session: DatabaseSession,
    state_filter: Annotated[EngineeringReviewState | None, Query(alias="state")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EngineeringReviewListResponse:
    try:
        records = await engineering_review_service.list(
            session,
            context=context,
            state=state_filter,
            limit=limit,
        )
    except (EngineeringReviewNotFoundError, EngineeringReviewIneligibleError) as error:
        raise _http_error(error) from error
    return EngineeringReviewListResponse(
        items=tuple(EngineeringReviewSummary.model_validate(item) for item in records)
    )


@router.get("/{review_id}", response_model=EngineeringReviewPackageResponse)
async def get_review(
    review_id: UUID,
    context: ReadContext,
    session: DatabaseSession,
) -> EngineeringReviewPackageResponse:
    try:
        package = await engineering_review_service.get(
            session,
            context=context,
            review_id=review_id,
        )
    except (
        EngineeringReviewNotFoundError,
        EngineeringReviewDigestMismatchError,
    ) as error:
        raise _http_error(error) from error
    return EngineeringReviewPackageResponse.model_validate(package)


@router.post(
    "/{review_id}/decision",
    response_model=EngineeringReviewPackageResponse,
    summary="Record an exact-evidence owner decision",
    description=(
        "Records owner acceptance or rejection of the result package only. "
        "It does not commit, deploy, or create another Engineering Command."
    ),
)
async def decide_review(
    review_id: UUID,
    data: EngineeringReviewDecisionRequest,
    context: ApproveContext,
    session: DatabaseSession,
) -> EngineeringReviewPackageResponse:
    try:
        package = await engineering_review_service.decide(
            session,
            context=context,
            command=DecideEngineeringReview(
                review_id=review_id,
                **data.model_dump(),
            ),
        )
    except (
        EngineeringReviewNotFoundError,
        EngineeringReviewConflictError,
        EngineeringReviewDigestMismatchError,
        EngineeringReviewIneligibleError,
    ) as error:
        raise _http_error(error) from error
    return EngineeringReviewPackageResponse.model_validate(package)
