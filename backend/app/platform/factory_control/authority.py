from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_security_database_session
from app.platform.auth.dependencies import AuthenticatedIdentity
from app.platform.auth.services import AuthenticatedContext
from app.platform.factory_control.models import PlatformAuthorityAssignment
from app.platform.permissions.codes import LaunchPlatformPermission
from app.platform.users.models import User
from app.worker_control.transport.http.dependencies import (
    AuthenticatedIdentity as AuthenticatedWorkerIdentity,
)
from app.worker_control.transport.http.dependencies import WorkerHttpIdentity
from app.worker_identity.models import WorkerIdentity

AuthorityDatabase = Annotated[
    AsyncSession, Depends(get_security_database_session, scope="function")
]


@dataclass(frozen=True)
class PlatformReaderContext:
    user_id: UUID
    authority_code: str


@dataclass(frozen=True)
class FactoryControllerContext:
    worker_identity_id: UUID
    worker_id: UUID
    tenant_company_id: UUID
    authority_code: str
    permission_code: str


async def active_user_platform_permissions(
    session: AsyncSession, *, user_id: UUID
) -> frozenset[str]:
    return frozenset(
        (
            await session.scalars(
                select(PlatformAuthorityAssignment.permission_code).where(
                    PlatformAuthorityAssignment.principal_type == "USER",
                    PlatformAuthorityAssignment.user_id == user_id,
                    PlatformAuthorityAssignment.status == "active",
                    PlatformAuthorityAssignment.authority_code.in_(
                        ("PLATFORM_OWNER", "PLATFORM_ADMIN")
                    ),
                )
            )
        ).all()
    )


async def require_platform_factory_reader(
    authenticated: AuthenticatedIdentity,
    session: AuthorityDatabase,
) -> PlatformReaderContext:
    assignment = await session.scalar(
        select(PlatformAuthorityAssignment).where(
            PlatformAuthorityAssignment.principal_type == "USER",
            PlatformAuthorityAssignment.user_id == authenticated.user.id,
            PlatformAuthorityAssignment.status == "active",
            PlatformAuthorityAssignment.authority_code.in_(
                ("PLATFORM_OWNER", "PLATFORM_ADMIN")
            ),
            PlatformAuthorityAssignment.permission_code
            == LaunchPlatformPermission.FACTORY_CONTROL_READ,
        )
    )
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform authority required.",
        )
    return PlatformReaderContext(
        user_id=authenticated.user.id, authority_code=assignment.authority_code
    )


PlatformReader = Annotated[
    PlatformReaderContext, Depends(require_platform_factory_reader)
]


def require_factory_controller_permission(
    permission_code: str,
) -> Callable[[WorkerHttpIdentity, AsyncSession], Awaitable[FactoryControllerContext]]:
    if permission_code not in {
        LaunchPlatformPermission.FACTORY_CONTROL_INGEST,
        LaunchPlatformPermission.FACTORY_CONTROL_SNAPSHOT,
    }:
        raise ValueError("Unsupported Factory Control controller permission.")

    async def dependency(
        identity: AuthenticatedWorkerIdentity,
        session: AuthorityDatabase,
    ) -> FactoryControllerContext:
        worker_identity = await session.scalar(
            select(WorkerIdentity).where(
                WorkerIdentity.company_id == identity.context.company_id,
                WorkerIdentity.orchestration_worker_id == identity.context.worker_id,
                WorkerIdentity.state == "active",
            )
        )
        if worker_identity is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Factory controller authority required.",
            )
        assignment = await session.scalar(
            select(PlatformAuthorityAssignment).where(
                PlatformAuthorityAssignment.principal_type == "WORKER_IDENTITY",
                PlatformAuthorityAssignment.worker_identity_id == worker_identity.id,
                PlatformAuthorityAssignment.status == "active",
                PlatformAuthorityAssignment.authority_code == "FACTORY_CONTROLLER",
                PlatformAuthorityAssignment.permission_code == permission_code,
            )
        )
        if assignment is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Factory controller authority required.",
            )
        return FactoryControllerContext(
            worker_identity_id=worker_identity.id,
            worker_id=identity.context.worker_id,
            tenant_company_id=identity.context.company_id,
            authority_code=assignment.authority_code,
            permission_code=permission_code,
        )

    return dependency


async def authenticated_user_platform_permissions(
    authenticated: AuthenticatedContext, session: AsyncSession
) -> frozenset[str]:
    """Expose only UI hints; API authorization always rechecks the active grant."""
    return await active_user_platform_permissions(
        session, user_id=authenticated.user.id
    )


async def revoke_platform_authority_assignment(
    session: AsyncSession,
    *,
    assignment_id: UUID,
    revoked_by_user_id: UUID,
    reason: str,
    revoked_at: datetime,
) -> PlatformAuthorityAssignment:
    """Governed primitive used by a future platform-custody administration path."""
    if not reason.strip():
        raise ValueError("Platform authority revocation requires a reason.")
    assignment = await session.scalar(
        select(PlatformAuthorityAssignment)
        .where(PlatformAuthorityAssignment.id == assignment_id)
        .with_for_update()
    )
    if assignment is None:
        raise ValueError("Platform authority assignment was not found.")
    if assignment.status == "revoked":
        return assignment
    assignment.status = "revoked"
    assignment.revoked_by_user_id = revoked_by_user_id
    assignment.revoked_at = revoked_at
    assignment.revocation_reason = reason.strip()
    assignment.version += 1
    if assignment.user_id is not None:
        user = await session.scalar(
            select(User).where(User.id == assignment.user_id).with_for_update()
        )
        if user is None:
            raise ValueError("Platform authority user was not found.")
        user.authorization_version += 1
        user.updated_at = revoked_at
    await session.flush()
    return assignment
