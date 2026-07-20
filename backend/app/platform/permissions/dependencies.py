from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.auth.dependencies import AuthenticatedIdentity
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationError,
    PermissionDeniedError,
    authorization_service,
)
from app.platform.security.decisions import (
    AuthorizationDenial,
    authorization_decision_logger,
)


DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


async def get_authorization_context(
    authenticated: AuthenticatedIdentity,
    session: DatabaseSession,
    company_id: Annotated[UUID, Header(alias="X-Company-ID")],
    active_branch_id: Annotated[UUID | None, Header(alias="X-Branch-ID")] = None,
) -> AuthorizationContext:
    try:
        return await authorization_service.resolve(
            session,
            authenticated=authenticated,
            company_id=company_id,
            branch_id=active_branch_id,
        )
    except AuthorizationError as error:
        authorization_decision_logger.denied(
            AuthorizationDenial(
                reason=type(error).__name__,
                actor_user_id=authenticated.user.id,
                company_id=company_id,
                branch_id=active_branch_id,
                resource="tenant_context",
            )
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access denied.",
        ) from error


ResolvedAuthorization = Annotated[
    AuthorizationContext,
    Depends(get_authorization_context),
]


def require_permission(
    permission_code: str,
) -> Callable[[AuthorizationContext], Awaitable[AuthorizationContext]]:
    async def dependency(
        context: ResolvedAuthorization,
    ) -> AuthorizationContext:
        try:
            authorization_service.require_permission(context, permission_code)
        except PermissionDeniedError as error:
            authorization_decision_logger.denied(
                AuthorizationDenial(
                    reason="missing_permission",
                    actor_user_id=context.user.id,
                    company_id=context.company.id,
                    branch_id=context.active_branch.id
                    if context.active_branch
                    else None,
                    permission_code=permission_code,
                    resource="permission_dependency",
                )
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied.",
            ) from error
        return context

    return dependency


def require_branch_access(
    branch_id: UUID,
) -> Callable[[AuthorizationContext], Awaitable[AuthorizationContext]]:
    async def dependency(
        context: ResolvedAuthorization,
    ) -> AuthorizationContext:
        try:
            authorization_service.require_branch(context, branch_id)
        except AuthorizationError as error:
            authorization_decision_logger.denied(
                AuthorizationDenial(
                    reason="branch_access_denied",
                    actor_user_id=context.user.id,
                    company_id=context.company.id,
                    branch_id=branch_id,
                    resource="branch_dependency",
                )
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Branch access denied.",
            ) from error
        return context

    return dependency
