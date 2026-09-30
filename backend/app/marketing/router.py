from datetime import datetime, timezone
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.auth.dependencies import AuthenticatedIdentity
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import MarketingPermission
from app.platform.permissions.dependencies import require_permission
from app.platform.provider_connections.models import ProviderConnectionBinding
from app.platform.secrets import SecretProviderError

from .contracts import AttributionTargetType
from .google_ads import GOOGLE_ADS_SCOPE
from .oauth import GoogleAdsOAuthError, build_google_ads_oauth_runtime
from .provider_service import ProviderBindingError, marketing_provider_service
from .schemas import (
    AttributionResponse,
    CatalogResponse,
    EvidenceCoverageResponse,
    GoogleAdsAccountBindingCreate,
    GoogleAdsAccountBindingResponse,
    GoogleAdsAccountBindingSummary,
    GoogleAdsConnectionReadinessResponse,
    GoogleAdsOAuthStartResponse,
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
OAUTH_COOKIE = "th_google_ads_oauth_nonce"


@router.post("/google-ads/oauth/authorize", response_model=GoogleAdsOAuthStartResponse)
async def google_ads_oauth_authorize(
    context: ProviderAdminContext,
    identity: AuthenticatedIdentity,
) -> JSONResponse:
    try:
        authorization_url, nonce = build_google_ads_oauth_runtime().begin(
            company_id=context.company.id,
            user_id=context.user.id,
            session_id=identity.authentication_session.id,
        )
    except (GoogleAdsOAuthError, SecretProviderError, OSError, ValueError) as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Google Ads connection is unavailable"
        ) from error
    response = JSONResponse({"authorization_url": authorization_url})
    response.set_cookie(
        OAUTH_COOKIE,
        nonce,
        max_age=600,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/api/v1/marketing/google-ads/oauth/callback",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/google-ads/oauth/callback", include_in_schema=False)
async def google_ads_oauth_callback(
    session: DatabaseSession,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    provider_error: Annotated[str | None, Query(alias="error")] = None,
    nonce: Annotated[str | None, Cookie(alias=OAUTH_COOKIE)] = None,
) -> RedirectResponse:
    destination = "/marketing/provider-connections/google-ads"
    if provider_error or not code or not state or not nonce:
        return RedirectResponse(f"{destination}?connection=denied", status_code=303)
    try:
        runtime = build_google_ads_oauth_runtime()
        pending, generation, expires_at = await runtime.complete(
            code=code, state=state, nonce=nonce
        )
        existing = await session.scalar(
            select(ProviderConnectionBinding).where(
                ProviderConnectionBinding.company_id == pending.company_id,
                ProviderConnectionBinding.environment == pending.environment,
                ProviderConnectionBinding.provider_family == "google_ads",
                ProviderConnectionBinding.state == "active",
            )
        )
        if existing is not None:
            existing.state = "revoked"
            existing.revoked_at = datetime.now(timezone.utc)
        connection = ProviderConnectionBinding(
            company_id=pending.company_id,
            environment=pending.environment,
            provider_family="google_ads",
            client_credential_reference=runtime.client_reference,
            account_token_reference=pending.token_reference,
            granted_scopes=[GOOGLE_ADS_SCOPE],
            consent_actor_user_id=pending.user_id,
            consented_at=datetime.now(timezone.utc),
            token_fingerprint=sha256(pending.token_reference.encode()).hexdigest(),
            token_generation=generation,
            token_expires_at=expires_at,
            callback_identity=runtime.redirect_uri,
            state="active",
        )
        session.add(connection)
        await session.flush()
        audit_service.stage(
            session,
            AuditEntry(
                action="marketing.google_ads.oauth.connected",
                resource_type="platform_provider_connection_binding",
                actor_user_id=pending.user_id,
                company_id=pending.company_id,
                resource_id=connection.id,
                reason_code="owner_oauth_consent",
                details={"environment": pending.environment, "scope": GOOGLE_ADS_SCOPE},
            ),
        )
        await session.commit()
    except (GoogleAdsOAuthError, SecretProviderError, OSError, ValueError):
        await session.rollback()
        return RedirectResponse(f"{destination}?connection=invalid", status_code=303)
    except Exception:  # noqa: BLE001 - callback boundary never returns internals
        await session.rollback()
        return RedirectResponse(f"{destination}?connection=failed", status_code=303)
    response = RedirectResponse(f"{destination}?connection=connected", status_code=303)
    response.delete_cookie(
        OAUTH_COOKIE, path="/api/v1/marketing/google-ads/oauth/callback"
    )
    response.headers.update(
        {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    )
    return response


@router.get(
    "/google-ads/connection-readiness",
    response_model=GoogleAdsConnectionReadinessResponse,
)
async def google_ads_connection_readiness(
    context: ProviderAdminContext, session: DatabaseSession
) -> GoogleAdsConnectionReadinessResponse:
    return await marketing_provider_service.google_ads_connection_readiness(
        session, context=context
    )


@router.get(
    "/google-ads/account-bindings",
    response_model=tuple[GoogleAdsAccountBindingSummary, ...],
)
async def google_ads_account_bindings(
    context: ProviderAdminContext, session: DatabaseSession
) -> tuple[GoogleAdsAccountBindingSummary, ...]:
    return await marketing_provider_service.google_ads_account_bindings(
        session, context=context
    )


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
