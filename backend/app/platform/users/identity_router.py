from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.dependencies import (
    ResolvedAuthorization,
    require_permission,
)
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import (
    ClientRecovery,
    FailureCode,
    SafeFailure,
)
from app.platform.users.identity_models import PendingEmailChange
from app.platform.users.identity_schemas import (
    AdministrativeEmailChangeRequest,
    EmailAvailabilityRequest,
    EmailAvailabilityResponse,
    EmailChangeConfirmationRequest,
    EmailChangeRequestResponse,
    ForcedPasswordResetRequest,
    ForcedPasswordResetResponse,
    IdentityMutationResponse,
    IdentityStateResponse,
    IdentityUserResponse,
    PendingEmailChangeResponse,
    PendingEmailChangeStatus,
)
from app.platform.users.identity_service import (
    IdentityAdministrationConflictError,
    IdentityAdministrationError,
    IdentityAdministrationNotFoundError,
    IdentityAdministrationTokenError,
    IdentityState,
    identity_administration_service,
)
from app.platform.users.models import UserCredential

self_service_router = APIRouter(
    prefix="/api/v1/identity",
    tags=["Identity Self-Service"],
)
administration_router = APIRouter(
    prefix="/api/v1/identity-admin",
    tags=["Identity Administration"],
)
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
AdministrationContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.COMPANY_ADMINISTER)),
]


def translate_identity_error(error: IdentityAdministrationError) -> HTTPException:
    if isinstance(error, IdentityAdministrationNotFoundError):
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Identity resource was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=failure.detail(),
        )
    if isinstance(error, IdentityAdministrationTokenError):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Email change request is expired, revoked, or already processed.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=failure.detail(),
        )
    if isinstance(error, IdentityAdministrationConflictError):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Identity operation conflicts with current state.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=failure.detail(),
        )
    failure = SafeFailure(
        FailureCode.VALIDATION,
        "Identity operation could not be completed.",
        ClientRecovery.USER_CORRECTION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=failure.detail(),
    )


def pending_response(change: PendingEmailChange) -> PendingEmailChangeResponse:
    return PendingEmailChangeResponse(
        id=change.id,
        proposed_email=change.proposed_normalized_email,
        status=cast(PendingEmailChangeStatus, change.status),
        created_at=change.created_at,
        expires_at=change.expires_at,
        confirmed_at=change.confirmed_at,
        revoked_at=change.revoked_at,
        superseded_at=change.superseded_at,
        expired_at=change.expired_at,
    )


def state_response(state: IdentityState) -> IdentityStateResponse:
    return IdentityStateResponse(
        user_id=state.user_id,
        normalized_email=state.normalized_email,
        email_verified_at=state.email_verified_at,
        pending_email_change=(
            pending_response(state.pending_email_change)
            if state.pending_email_change
            else None
        ),
        password_change_required=state.password_change_required,
        password_change_required_at=state.password_change_required_at,
        password_change_required_reason_code=(
            state.password_change_required_reason_code
        ),
        password_change_required_cleared_at=(state.password_change_required_cleared_at),
        credential_version=state.credential_version,
        authorization_version=state.authorization_version,
    )


def forced_reset_response(
    credential: UserCredential, *, changed: bool
) -> ForcedPasswordResetResponse:
    return ForcedPasswordResetResponse(
        required=credential.password_change_required,
        changed=changed,
        required_at=credential.password_change_required_at,
        reason_code=credential.password_change_required_reason_code,
        cleared_at=credential.password_change_required_cleared_at,
        credential_version=credential.credential_version,
    )


@administration_router.post(
    "/users/{user_id}/email-availability",
    response_model=EmailAvailabilityResponse,
    summary="Validate administrative login-email availability",
    response_description="Current reservation availability for the proposed email.",
)
async def validate_email_availability(
    user_id: UUID,
    data: EmailAvailabilityRequest,
    context: AdministrationContext,
    session: DatabaseSession,
) -> EmailAvailabilityResponse:
    try:
        available = await identity_administration_service.is_email_available(
            session,
            context=context,
            target_user_id=user_id,
            proposed_email=data.email,
        )
    except IdentityAdministrationError as error:
        raise translate_identity_error(error) from error
    return EmailAvailabilityResponse(available=available)


@administration_router.post(
    "/users/{user_id}/email-change",
    response_model=EmailChangeRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request an administrative login-email change",
    response_description="Pending verification request without persisted token material.",
)
async def request_email_change(
    user_id: UUID,
    data: AdministrativeEmailChangeRequest,
    context: AdministrationContext,
    session: DatabaseSession,
) -> EmailChangeRequestResponse:
    try:
        delivery = (
            await identity_administration_service.request_administrative_email_change(
                session,
                context=context,
                target_user_id=user_id,
                proposed_email=data.email,
            )
        )
    except IdentityAdministrationError as error:
        raise translate_identity_error(error) from error
    return EmailChangeRequestResponse(
        change=pending_response(delivery.change),
        created=delivery.created,
        development_token=(
            delivery.plaintext_token
            if settings.environment in {"development", "test"}
            else None
        ),
    )


@administration_router.delete(
    "/email-changes/{change_id}",
    response_model=IdentityMutationResponse,
    summary="Revoke a pending administrative email change",
)
async def revoke_email_change(
    change_id: UUID,
    context: AdministrationContext,
    session: DatabaseSession,
) -> IdentityMutationResponse:
    try:
        changed = await identity_administration_service.revoke_email_change(
            session,
            context=context,
            change_id=change_id,
        )
    except IdentityAdministrationError as error:
        raise translate_identity_error(error) from error
    return IdentityMutationResponse(
        changed=changed,
        message="Pending email change revoked." if changed else "No change required.",
    )


@administration_router.get(
    "/users/{user_id}",
    response_model=IdentityStateResponse,
    summary="Retrieve company-scoped identity administration state",
)
async def get_administrative_identity_state(
    user_id: UUID,
    context: AdministrationContext,
    session: DatabaseSession,
) -> IdentityStateResponse:
    try:
        state = await identity_administration_service.get_identity_state(
            session,
            context=context,
            target_user_id=user_id,
        )
    except IdentityAdministrationError as error:
        raise translate_identity_error(error) from error
    return state_response(state)


@administration_router.post(
    "/users/{user_id}/forced-password-reset",
    response_model=ForcedPasswordResetResponse,
    summary="Require a password reset for a company identity",
)
async def require_forced_password_reset(
    user_id: UUID,
    data: ForcedPasswordResetRequest,
    context: AdministrationContext,
    session: DatabaseSession,
) -> ForcedPasswordResetResponse:
    try:
        (
            credential,
            changed,
        ) = await identity_administration_service.require_password_reset(
            session,
            context=context,
            target_user_id=user_id,
            reason_code=data.reason_code,
        )
    except IdentityAdministrationError as error:
        raise translate_identity_error(error) from error
    return forced_reset_response(credential, changed=changed)


@administration_router.post(
    "/users/{user_id}/forced-password-reset/clear",
    response_model=ForcedPasswordResetResponse,
    summary="Clear a verified forced-password-reset requirement",
)
async def clear_administrative_forced_password_reset(
    user_id: UUID,
    context: AdministrationContext,
    session: DatabaseSession,
) -> ForcedPasswordResetResponse:
    try:
        (
            credential,
            changed,
        ) = await identity_administration_service.clear_password_reset_after_change(
            session,
            context=context,
            target_user_id=user_id,
        )
    except IdentityAdministrationError as error:
        raise translate_identity_error(error) from error
    return forced_reset_response(credential, changed=changed)


@self_service_router.post(
    "/email-change/confirm",
    response_model=IdentityUserResponse,
    summary="Confirm the authenticated user's pending login-email change",
)
async def confirm_own_email_change(
    data: EmailChangeConfirmationRequest,
    context: ResolvedAuthorization,
    session: DatabaseSession,
) -> IdentityUserResponse:
    try:
        user = await identity_administration_service.confirm_own_email_change(
            session,
            context=context,
            plaintext_token=data.token,
        )
    except IdentityAdministrationError as error:
        raise translate_identity_error(error) from error
    return IdentityUserResponse(
        id=user.id,
        normalized_email=user.normalized_email,
        email_verified_at=user.email_verified_at,
    )


@self_service_router.get(
    "/me",
    response_model=IdentityStateResponse,
    summary="Retrieve the authenticated user's identity state",
)
async def get_own_identity_state(
    context: ResolvedAuthorization,
    session: DatabaseSession,
) -> IdentityStateResponse:
    try:
        state = await identity_administration_service.get_identity_state(
            session,
            context=context,
            target_user_id=context.user.id,
        )
    except IdentityAdministrationError as error:
        raise translate_identity_error(error) from error
    return state_response(state)


@self_service_router.post(
    "/me/forced-password-reset/clear",
    response_model=ForcedPasswordResetResponse,
    summary="Clear the authenticated user's verified reset requirement",
)
async def clear_own_forced_password_reset(
    context: ResolvedAuthorization,
    session: DatabaseSession,
) -> ForcedPasswordResetResponse:
    try:
        (
            credential,
            changed,
        ) = await identity_administration_service.clear_password_reset_after_change(
            session,
            context=context,
            target_user_id=context.user.id,
        )
    except IdentityAdministrationError as error:
        raise translate_identity_error(error) from error
    return forced_reset_response(credential, changed=changed)
