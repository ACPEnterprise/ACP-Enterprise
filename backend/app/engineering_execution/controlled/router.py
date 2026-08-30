from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    EngineeringCommandPermission,
    EngineeringExecutionPermission,
)
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

from .errors import ControlledExecutionError
from .schemas import (
    AdoptControlledResultRequest,
    AdoptControlledResultResponse,
    ControlledOfferResponse,
    PrepareControlledOfferRequest,
)
from .service import ControlledExecutionService

router = APIRouter(
    prefix="/api/v1/engineering-executions",
    tags=["Controlled Engineering Execution"],
)
Database = Annotated[AsyncSession, Depends(get_database_session)]
ExecutionContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringExecutionPermission.REQUEST)),
]
AdoptionContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringCommandPermission.APPROVE)),
]
service = ControlledExecutionService()


@router.post(
    "/{execution_id}/expired-result-adoptions",
    response_model=AdoptControlledResultResponse,
    summary="Adopt immutable published evidence after controlled lease expiry",
)
async def adopt_expired_result(
    execution_id: UUID,
    data: AdoptControlledResultRequest,
    context: AdoptionContext,
    database: Database,
) -> AdoptControlledResultResponse:
    try:
        result, review_id, adopted_at = await service.adopt_expired_result(
            database,
            context=context,
            execution_id=execution_id,
            **data.model_dump(),
        )
    except ControlledExecutionError as error:
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Controlled result adoption conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=failure.detail(),
        ) from error
    return AdoptControlledResultResponse(
        result_id=result.id,
        execution_id=result.execution_id,
        outcome=result.outcome.value,
        repository_mutated=result.repository_mutated,
        result_commit=str(result.output["commit_sha"]),
        provider_completed_at=result.completed_at,
        adopted_at=adopted_at,
        review_id=review_id,
    )


@router.post(
    "/{execution_id}/controlled-offers",
    response_model=ControlledOfferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Prepare one immutable read-only controlled execution offer",
)
async def prepare_controlled_offer(
    execution_id: UUID,
    data: PrepareControlledOfferRequest,
    context: ExecutionContext,
    database: Database,
) -> ControlledOfferResponse:
    try:
        offer = await service.prepare_offer(
            database,
            context=context,
            execution_id=execution_id,
            workspace_id=data.workspace_id,
            lease_seconds=data.lease_seconds,
        )
    except ControlledExecutionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "controlled_execution_ineligible"},
        ) from error
    return ControlledOfferResponse(
        id=offer.id,
        command_id=offer.command_id,
        execution_id=offer.execution_id,
        workspace_id=offer.workspace_id,
        command_type=offer.command_type.value,
        capability_required=offer.capability_required.value,
        state=offer.state.value,
        expires_at=offer.expires_at,
        lease_seconds=offer.lease_seconds,
        created_at=offer.created_at,
    )
