from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import CommunicationsPermission
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

from .catalog import OPERATIONAL_MESSAGE_CATALOG, catalog_fingerprint
from .contracts import CommunicationRequest
from .errors import (
    CommunicationAuthorizationError,
    CommunicationConflictError,
    CommunicationError,
    CommunicationNotFoundError,
    CommunicationValidationError,
)
from .readiness import configuration_from_settings, project_readiness
from .schemas import (
    CommunicationCreate,
    CommunicationItem,
    CommunicationOperationsSummary,
    CommunicationPage,
    CommunicationsReadinessItem,
    MessageCatalogItem,
)
from .service import communication_service

router = APIRouter(prefix="/api/v1/communications", tags=["Communications"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(CommunicationsPermission.READ))
]
ManageContext = Annotated[
    AuthorizationContext, Depends(require_permission(CommunicationsPermission.MANAGE))
]


def communication_http(error: CommunicationError) -> HTTPException:
    if isinstance(error, CommunicationAuthorizationError):
        failure = SafeFailure(
            FailureCode.FORBIDDEN,
            "Communication is not authorized by current policy or consent authority.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_403_FORBIDDEN, failure.detail())
    if isinstance(error, CommunicationNotFoundError):
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Communication source resource was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_404_NOT_FOUND, failure.detail())
    if isinstance(error, CommunicationConflictError):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Communication operation conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_409_CONFLICT, failure.detail())
    if isinstance(error, CommunicationValidationError):
        failure = SafeFailure(
            FailureCode.VALIDATION,
            "Communication request requires correction.",
            ClientRecovery.USER_CORRECTION_REQUIRED,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, failure.detail())
    failure = SafeFailure(
        FailureCode.INTERNAL_FAILURE,
        "Communication operation failed safely.",
        ClientRecovery.OWNER_ADMIN_ACTION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, failure.detail())


@router.post("/requests", response_model=CommunicationItem, status_code=201)
async def create_request(
    payload: CommunicationCreate,
    context: ManageContext,
    session: DatabaseSession,
) -> CommunicationItem:
    try:
        evidence = await communication_service.request(
            session,
            context=context,
            request=CommunicationRequest(**payload.model_dump()),
        )
        return CommunicationItem.model_validate(evidence)
    except CommunicationError as error:
        raise communication_http(error) from error


@router.get("/history", response_model=CommunicationPage)
async def history(
    context: ReadContext,
    session: DatabaseSession,
    branch_id: UUID | None = None,
    customer_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CommunicationPage:
    try:
        items = await communication_service.list(
            session,
            context=context,
            branch_id=branch_id,
            customer_id=customer_id,
            limit=limit,
        )
        return CommunicationPage(
            items=tuple(CommunicationItem.model_validate(item) for item in items)
        )
    except CommunicationError as error:
        raise communication_http(error) from error


@router.get("/summary", response_model=CommunicationOperationsSummary)
async def operations_summary(
    context: ReadContext,
    session: DatabaseSession,
    branch_id: UUID | None = None,
) -> CommunicationOperationsSummary:
    try:
        result = await communication_service.operations_summary(
            session,
            context=context,
            branch_id=branch_id,
        )
        return CommunicationOperationsSummary.model_validate(result)
    except CommunicationError as error:
        raise communication_http(error) from error


@router.get("/catalog", response_model=tuple[MessageCatalogItem, ...])
async def catalog(context: ReadContext) -> tuple[MessageCatalogItem, ...]:
    del context
    return tuple(
        MessageCatalogItem(
            message_class=policy.communication_type,
            owner_domain=policy.owner_domain,
            allowed_channels=tuple(
                sorted(policy.allowed_channels, key=lambda x: x.value)
            ),
            template_version=policy.template_identifier,
            purpose=policy.purpose,
            policy_required=policy.policy_required,
        )
        for policy in sorted(
            OPERATIONAL_MESSAGE_CATALOG.values(),
            key=lambda value: value.communication_type.value,
        )
    )


@router.get("/readiness", response_model=CommunicationsReadinessItem)
async def readiness(context: ReadContext) -> CommunicationsReadinessItem:
    del context
    # Real provider admission is intentionally configuration-gated. Synthetic
    # qualification must never be projected as delivery readiness.
    result = project_readiness(configuration_from_settings(settings))
    return CommunicationsReadinessItem(
        **result.__dict__, catalog_fingerprint=catalog_fingerprint()
    )
