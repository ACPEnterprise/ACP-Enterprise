from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCommandPermission
from app.platform.permissions.dependencies import require_permission

from .contracts import RepositoryAuthorizationState
from .errors import (
    RepositoryAuthorizationConflictError,
    RepositoryAuthorizationEvidenceMismatchError,
    RepositoryAuthorizationIneligibleError,
    RepositoryAuthorizationNotFoundError,
)
from .records import (
    RequestRepositoryAuthorization,
    RevokeRepositoryAuthorization,
    ValidateRepositoryAuthorization,
)
from .schemas import (
    RepositoryAuthorizationDetail,
    RepositoryAuthorizationEligibilityResponse,
    RepositoryAuthorizationList,
    RepositoryAuthorizationRequest,
    RepositoryAuthorizationRevokeRequest,
    RepositoryAuthorizationSummary,
    RepositoryAuthorizationValidationRequest,
)
from .service import engineering_repository_authorization_service

router = APIRouter(
    prefix="/api/v1/engineering/repository-authorizations",
    tags=["Engineering Repository Authorization"],
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
    if isinstance(error, RepositoryAuthorizationNotFoundError):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Repository authorization not found.",
        )
    if isinstance(
        error,
        (
            RepositoryAuthorizationConflictError,
            RepositoryAuthorizationEvidenceMismatchError,
        ),
    ):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error))


def _detail(record) -> RepositoryAuthorizationDetail:
    now = datetime.now(timezone.utc)
    values = {
        field: getattr(record, field)
        for field in RepositoryAuthorizationDetail.model_fields
        if field != "authorization_eligible"
    }
    return RepositoryAuthorizationDetail.model_validate(
        {
            **values,
            "authorization_eligible": (
                record.state is RepositoryAuthorizationState.AUTHORIZED
                and record.expires_at > now
            ),
        }
    )


@router.post("", response_model=RepositoryAuthorizationDetail)
async def request_authorization(
    data: RepositoryAuthorizationRequest,
    context: ApproveContext,
    session: DatabaseSession,
) -> RepositoryAuthorizationDetail:
    try:
        record = await engineering_repository_authorization_service.request(
            session,
            context=context,
            command=RequestRepositoryAuthorization(**data.model_dump()),
        )
    except (
        RepositoryAuthorizationNotFoundError,
        RepositoryAuthorizationConflictError,
        RepositoryAuthorizationEvidenceMismatchError,
        RepositoryAuthorizationIneligibleError,
    ) as error:
        raise _http_error(error) from error
    return _detail(record)


@router.get("", response_model=RepositoryAuthorizationList)
async def list_authorizations(
    context: ReadContext,
    session: DatabaseSession,
    state_filter: Annotated[
        RepositoryAuthorizationState | None,
        Query(alias="state"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RepositoryAuthorizationList:
    try:
        records = await engineering_repository_authorization_service.list(
            session,
            context=context,
            state=state_filter,
            limit=limit,
        )
    except (
        RepositoryAuthorizationNotFoundError,
        RepositoryAuthorizationIneligibleError,
    ) as error:
        raise _http_error(error) from error
    return RepositoryAuthorizationList(
        items=tuple(
            RepositoryAuthorizationSummary.model_validate(record) for record in records
        )
    )


@router.get("/{authorization_id}", response_model=RepositoryAuthorizationDetail)
async def get_authorization(
    authorization_id: UUID,
    context: ReadContext,
    session: DatabaseSession,
) -> RepositoryAuthorizationDetail:
    try:
        record = await engineering_repository_authorization_service.get(
            session,
            context=context,
            authorization_id=authorization_id,
        )
    except RepositoryAuthorizationNotFoundError as error:
        raise _http_error(error) from error
    return _detail(record)


@router.post(
    "/{authorization_id}/eligibility",
    response_model=RepositoryAuthorizationEligibilityResponse,
    summary="Inspect capability eligibility without consuming it",
)
async def inspect_eligibility(
    authorization_id: UUID,
    data: RepositoryAuthorizationValidationRequest,
    context: ApproveContext,
    session: DatabaseSession,
) -> RepositoryAuthorizationEligibilityResponse:
    result = await engineering_repository_authorization_service.eligibility(
        session,
        context=context,
        command=ValidateRepositoryAuthorization(
            authorization_id=authorization_id,
            **data.model_dump(),
        ),
    )
    return RepositoryAuthorizationEligibilityResponse(
        eligible=result.eligible,
        reason_code=result.reason_code,
        review_id=result.review_id if result.review_id.int else None,
        operation_type=result.operation_type,
    )


@router.post(
    "/{authorization_id}/revoke",
    response_model=RepositoryAuthorizationDetail,
)
async def revoke_authorization(
    authorization_id: UUID,
    data: RepositoryAuthorizationRevokeRequest,
    context: ApproveContext,
    session: DatabaseSession,
) -> RepositoryAuthorizationDetail:
    try:
        record = await engineering_repository_authorization_service.revoke(
            session,
            context=context,
            command=RevokeRepositoryAuthorization(
                authorization_id=authorization_id,
                **data.model_dump(),
            ),
        )
    except (
        RepositoryAuthorizationNotFoundError,
        RepositoryAuthorizationConflictError,
        RepositoryAuthorizationIneligibleError,
    ) as error:
        raise _http_error(error) from error
    return _detail(record)
