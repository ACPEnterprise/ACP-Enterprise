from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EconomicsPolicyPermission
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

from .workspace import EconomicsWorkspaceService

router = APIRouter(prefix="/api/v1/business-economics", tags=["Business Economics"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Reader = Annotated[
    AuthorizationContext,
    Depends(require_permission(EconomicsPolicyPermission.MEASUREMENT_READ)),
]


@router.get("/workspace", response_model=dict[str, object])
async def economics_workspace(
    session: Session,
    context: Reader,
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
) -> dict[str, object]:
    try:
        return await EconomicsWorkspaceService().overview(
            session, context=context, period_start=start, period_end=end
        )
    except ValueError as error:
        failure = SafeFailure(
            FailureCode.VALIDATION,
            "Business Economics request requires correction.",
            ClientRecovery.USER_CORRECTION_REQUIRED,
            current_correlation_id(),
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, failure.detail()
        ) from error


@router.get("/results/{result_id}", response_model=dict[str, object])
async def economics_result(
    result_id: UUID, session: Session, context: Reader
) -> dict[str, object]:
    try:
        return await EconomicsWorkspaceService().detail(
            session, context=context, result_id=result_id
        )
    except LookupError as error:
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Business Economics result was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, failure.detail()) from error
