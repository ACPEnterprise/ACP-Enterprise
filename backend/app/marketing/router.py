from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import MarketingPermission
from app.platform.permissions.dependencies import require_permission

from .contracts import AttributionTargetType
from .schemas import (
    AttributionResponse,
    CatalogResponse,
    EvidenceCoverageResponse,
    ManualAttributionConfirmation,
    ResolutionQueueResponse,
)
from .service import MarketingConflict, MarketingNotFound, marketing_service

router = APIRouter(prefix="/api/v1/marketing", tags=["Marketing"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(MarketingPermission.READ))
]
EvidenceContext = Annotated[
    AuthorizationContext, Depends(require_permission(MarketingPermission.EVIDENCE_READ))
]
ConfirmContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(MarketingPermission.ATTRIBUTION_CONFIRM)),
]


@router.get("/catalog", response_model=CatalogResponse)
async def catalog(context: ReadContext, session: DatabaseSession) -> CatalogResponse:
    return await marketing_service.catalog(session, context=context)


@router.get(
    "/attributions/{target_type}/{target_id}",
    response_model=tuple[AttributionResponse, ...],
)
async def attribution_history(
    target_type: AttributionTargetType,
    target_id: UUID,
    context: EvidenceContext,
    session: DatabaseSession,
) -> tuple[AttributionResponse, ...]:
    return await marketing_service.attribution_history(
        session, context=context, target_type=target_type, target_id=target_id
    )


@router.get("/resolution-queue", response_model=ResolutionQueueResponse)
async def resolution_queue(
    context: EvidenceContext,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ResolutionQueueResponse:
    return ResolutionQueueResponse(
        items=await marketing_service.resolution_queue(
            session, context=context, limit=limit
        )
    )


@router.get("/evidence-coverage", response_model=EvidenceCoverageResponse)
async def evidence_coverage(
    context: EvidenceContext, session: DatabaseSession
) -> EvidenceCoverageResponse:
    return await marketing_service.coverage(session, context=context)


@router.post(
    "/attributions/manual-confirmation",
    response_model=AttributionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def manual_confirmation(
    payload: ManualAttributionConfirmation,
    context: ConfirmContext,
    session: DatabaseSession,
) -> AttributionResponse:
    try:
        return await marketing_service.confirm_manual(
            session, context=context, data=payload
        )
    except MarketingConflict as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except MarketingNotFound as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Marketing evidence not found"
        ) from error
