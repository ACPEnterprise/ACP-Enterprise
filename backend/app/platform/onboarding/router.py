from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.dependencies import require_permission

from .schemas import (
    OnboardingActivateRequest,
    OnboardingInitiateRequest,
    OnboardingView,
)
from .service import (
    OnboardingAuthorizationError,
    OnboardingCommand,
    OnboardingConflictError,
    identity_onboarding_service,
)

router = APIRouter(prefix="/api/v1/identity-onboarding", tags=["Identity Onboarding"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
OnboardingAdmin = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.IDENTITY_ONBOARDING_MANAGE)),
]


def _safe_error(error: Exception) -> HTTPException:
    if isinstance(error, OnboardingAuthorizationError):
        return HTTPException(
            status.HTTP_403_FORBIDDEN, "Onboarding authority is required."
        )
    return HTTPException(
        status.HTTP_409_CONFLICT,
        "Onboarding operation conflicts with current authority.",
    )


@router.post("", response_model=OnboardingView, status_code=status.HTTP_201_CREATED)
async def initiate(
    data: OnboardingInitiateRequest, context: OnboardingAdmin, session: Session
) -> OnboardingView:
    try:
        record = await identity_onboarding_service.initiate(
            session,
            context=context,
            command=OnboardingCommand(
                request_key=data.request_key,
                branch_id=data.branch_id,
                first_name=data.first_name,
                last_name=data.last_name,
                display_name=data.display_name,
                employee_type=data.employee_type,
                employee_number_prefix=data.employee_number_prefix,
                employee_number_width=data.employee_number_width,
                role_ids=data.role_ids,
                login_email=(
                    data.login_email.get_secret_value() if data.login_email else None
                ),
                existing_user_id=data.existing_user_id,
            ),
        )
    except (OnboardingAuthorizationError, OnboardingConflictError) as error:
        raise _safe_error(error) from error
    return OnboardingView.model_validate(record)


@router.post("/activate/complete", response_model=OnboardingView)
async def activate(data: OnboardingActivateRequest, session: Session) -> OnboardingView:
    try:
        record = await identity_onboarding_service.activate(
            session, token=data.token, password=data.password
        )
    except OnboardingConflictError as error:
        raise _safe_error(error) from error
    return OnboardingView.model_validate(record)


@router.post("/{request_id}/revoke", response_model=OnboardingView)
async def revoke(
    request_id: UUID, context: OnboardingAdmin, session: Session
) -> OnboardingView:
    try:
        record = await identity_onboarding_service.revoke(
            session, context=context, request_id=request_id
        )
    except (OnboardingAuthorizationError, OnboardingConflictError) as error:
        raise _safe_error(error) from error
    return OnboardingView.model_validate(record)


@router.post("/{request_id}/reissue", response_model=OnboardingView)
async def reissue(
    request_id: UUID, context: OnboardingAdmin, session: Session
) -> OnboardingView:
    try:
        record = await identity_onboarding_service.reissue(
            session, context=context, request_id=request_id
        )
    except (OnboardingAuthorizationError, OnboardingConflictError) as error:
        raise _safe_error(error) from error
    return OnboardingView.model_validate(record)


@router.get("/{request_id}", response_model=OnboardingView)
async def get_state(
    request_id: UUID, context: OnboardingAdmin, session: Session
) -> OnboardingView:
    try:
        record = await identity_onboarding_service.get(
            session, context=context, request_id=request_id
        )
    except (OnboardingAuthorizationError, OnboardingConflictError) as error:
        raise _safe_error(error) from error
    return OnboardingView.model_validate(record)
