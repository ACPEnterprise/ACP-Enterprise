from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import MarketingPermission
from app.platform.permissions.dependencies import require_permission

from .contracts import AttributionTargetType
from .provider_service import ProviderBindingError, marketing_provider_service
from .schemas import (
    AttributionResponse,
    CatalogResponse,
    EvidenceCoverageResponse,
    GoogleAdsAccountBindingCreate,
    GoogleAdsAccountBindingResponse,
    ManualAttributionConfirmation,
    ProviderCoverageResponse,
    ProviderSyncStatusResponse,
    ReconciliationFindingResponse,
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
ProviderAdminContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(MarketingPermission.PROVIDER_ADMIN)),
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


@router.post(
    "/google-ads/account-bindings",
    response_model=GoogleAdsAccountBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bind_google_ads_account(
    payload: GoogleAdsAccountBindingCreate,
    context: ProviderAdminContext,
    session: DatabaseSession,
) -> GoogleAdsAccountBindingResponse:
    try:
        return await marketing_provider_service.bind_google_ads_account(
            session, context=context, data=payload
        )
    except ProviderBindingError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Google Ads binding rejected"
        ) from error


@router.get(
    "/google-ads/sync-status", response_model=tuple[ProviderSyncStatusResponse, ...]
)
async def google_ads_sync_status(
    context: EvidenceContext, session: DatabaseSession
) -> tuple[ProviderSyncStatusResponse, ...]:
    return await marketing_provider_service.sync_status(session, context=context)


@router.get("/google-ads/coverage", response_model=tuple[ProviderCoverageResponse, ...])
async def google_ads_coverage(
    context: EvidenceContext, session: DatabaseSession
) -> tuple[ProviderCoverageResponse, ...]:
    return await marketing_provider_service.coverage(session, context=context)


@router.get(
    "/google-ads/reconciliation",
    response_model=tuple[ReconciliationFindingResponse, ...],
)
async def google_ads_reconciliation(
    context: EvidenceContext, session: DatabaseSession
) -> tuple[ReconciliationFindingResponse, ...]:
    return await marketing_provider_service.reconciliation(session, context=context)
