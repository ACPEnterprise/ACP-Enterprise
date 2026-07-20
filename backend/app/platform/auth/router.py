from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_database_session
from app.platform.auth.dependencies import AuthenticatedIdentity
from app.platform.auth.errors import (
    AuthenticationError,
    InvalidCredentialsError,
    PasswordPolicyError,
    RateLimitExceededError,
    RateLimitUnavailableError,
    RefreshTokenReuseError,
)
from app.platform.auth.rate_limit import AuthenticationRateLimiter
from app.platform.auth.schemas import (
    AuthenticationResponse,
    EmailVerificationConfirmRequest,
    GenericResponse,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshRequest,
    SessionResponse,
    UserIdentityResponse,
)
from app.platform.auth.services import (
    authentication_service,
    recovery_service,
    security_token_service,
)
from app.platform.security.metrics import security_metrics


router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
rate_limiter = AuthenticationRateLimiter()


def client_metadata(request: Request) -> tuple[str | None, str | None]:
    ip_address = request.client.host if request.client else None
    return ip_address, request.headers.get("user-agent")


async def enforce_rate_limit(
    *,
    bucket: str,
    identifier: str,
    limit: int,
    window_seconds: int,
) -> None:
    try:
        await rate_limiter.enforce(
            bucket=bucket,
            identifier_hash=security_token_service.hash_identifier(identifier),
            limit=limit,
            window_seconds=window_seconds,
        )
    except RateLimitExceededError as error:
        security_metrics.increment("rate_limit_denials_total", bucket=bucket)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication requests.",
        ) from error
    except RateLimitUnavailableError as error:
        security_metrics.increment("rate_limit_unavailable_total", bucket=bucket)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication safeguards are temporarily unavailable.",
        ) from error


def user_response(context: AuthenticatedIdentity) -> UserIdentityResponse:
    return UserIdentityResponse(
        id=context.user.id,
        normalized_email=context.user.normalized_email,
        first_name=context.user.first_name,
        last_name=context.user.last_name,
        display_name=context.user.display_name,
        email_verified_at=context.user.email_verified_at,
    )


@router.post("/login", response_model=AuthenticationResponse)
async def login(
    data: LoginRequest,
    request: Request,
    session: DatabaseSession,
) -> AuthenticationResponse:
    ip_address, user_agent = client_metadata(request)
    await enforce_rate_limit(
        bucket="login",
        identifier=f"{ip_address}:{data.email}",
        limit=10,
        window_seconds=300,
    )
    try:
        result = await authentication_service.authenticate(
            session,
            email=data.email,
            password=data.password,
            ip_address=ip_address,
            user_agent=user_agent,
            device_label=data.device_label,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        ) from error
    return AuthenticationResponse(
        user=UserIdentityResponse(
            id=result.user.id,
            normalized_email=result.user.normalized_email,
            first_name=result.user.first_name,
            last_name=result.user.last_name,
            display_name=result.user.display_name,
            email_verified_at=result.user.email_verified_at,
        ),
        session_id=result.session_id,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        access_token_expires_at=result.access_token_expires_at,
        refresh_token_expires_at=result.refresh_token_expires_at,
        session_absolute_expires_at=result.session_absolute_expires_at,
        session_idle_expires_at=result.session_idle_expires_at,
    )


@router.post("/refresh", response_model=AuthenticationResponse)
async def refresh(
    data: RefreshRequest,
    request: Request,
    session: DatabaseSession,
) -> AuthenticationResponse:
    ip_address, user_agent = client_metadata(request)
    await enforce_rate_limit(
        bucket="refresh",
        identifier=f"{ip_address}:{data.refresh_token[:16]}",
        limit=30,
        window_seconds=60,
    )
    try:
        result = await authentication_service.rotate_refresh_token(
            session,
            plaintext_token=data.refresh_token,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except RefreshTokenReuseError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid.",
        ) from error
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid.",
        ) from error
    return AuthenticationResponse(
        user=UserIdentityResponse(
            id=result.user.id,
            normalized_email=result.user.normalized_email,
            first_name=result.user.first_name,
            last_name=result.user.last_name,
            display_name=result.user.display_name,
            email_verified_at=result.user.email_verified_at,
        ),
        session_id=result.session_id,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        access_token_expires_at=result.access_token_expires_at,
        refresh_token_expires_at=result.refresh_token_expires_at,
    )


@router.post("/logout", response_model=GenericResponse)
async def logout(
    context: AuthenticatedIdentity,
    session: DatabaseSession,
) -> GenericResponse:
    await authentication_service.logout(
        session,
        authentication_session_id=context.authentication_session.id,
        actor_user_id=context.user.id,
    )
    return GenericResponse(message="Session logged out.")


@router.post("/logout-all", response_model=GenericResponse)
async def logout_all(
    context: AuthenticatedIdentity,
    session: DatabaseSession,
) -> GenericResponse:
    await authentication_service.logout_all(session, user_id=context.user.id)
    return GenericResponse(message="All sessions logged out.")


@router.post("/password-reset/request", response_model=GenericResponse)
async def request_password_reset(
    data: PasswordResetRequest,
    request: Request,
    session: DatabaseSession,
) -> GenericResponse:
    ip_address, user_agent = client_metadata(request)
    await enforce_rate_limit(
        bucket="password-reset",
        identifier=f"{ip_address}:{data.email}",
        limit=5,
        window_seconds=3600,
    )
    delivery = await recovery_service.request_password_reset(
        session,
        email=data.email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return GenericResponse(
        message="If the account is eligible, recovery instructions will be sent.",
        development_token=(
            delivery.plaintext_token
            if settings.environment in {"development", "test"}
            else None
        ),
    )


@router.post("/password-reset/confirm", response_model=GenericResponse)
async def confirm_password_reset(
    data: PasswordResetConfirmRequest,
    session: DatabaseSession,
) -> GenericResponse:
    try:
        await recovery_service.confirm_password_reset(
            session,
            plaintext_token=data.token,
            new_password=data.new_password,
        )
    except PasswordPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token is invalid.",
        ) from error
    return GenericResponse(message="Password reset completed.")


@router.post("/email-verification/request", response_model=GenericResponse)
async def request_email_verification(
    context: AuthenticatedIdentity,
    session: DatabaseSession,
) -> GenericResponse:
    await enforce_rate_limit(
        bucket="email-verification",
        identifier=str(context.user.id),
        limit=5,
        window_seconds=3600,
    )
    delivery = await recovery_service.request_email_verification(
        session,
        user_id=context.user.id,
    )
    return GenericResponse(
        message="Verification instructions will be sent.",
        development_token=(
            delivery.plaintext_token
            if settings.environment in {"development", "test"}
            else None
        ),
    )


@router.post("/email-verification/confirm", response_model=GenericResponse)
async def confirm_email_verification(
    data: EmailVerificationConfirmRequest,
    session: DatabaseSession,
) -> GenericResponse:
    try:
        await recovery_service.confirm_email_verification(
            session,
            plaintext_token=data.token,
        )
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email verification token is invalid.",
        ) from error
    return GenericResponse(message="Email verified.")


@router.get("/session", response_model=SessionResponse)
async def get_session(context: AuthenticatedIdentity) -> SessionResponse:
    record = context.authentication_session
    return SessionResponse(
        user=user_response(context),
        session_id=record.id,
        status=record.status,
        created_at=record.created_at,
        last_seen_at=record.last_seen_at,
        absolute_expires_at=record.absolute_expires_at,
        idle_expires_at=record.idle_expires_at,
        authentication_method=record.authentication_method,
    )
