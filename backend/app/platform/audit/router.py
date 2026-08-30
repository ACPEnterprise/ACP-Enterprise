from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.audit.access_service import audit_access_service
from app.platform.audit.schemas import AuditRecordResponse
from app.platform.permissions.authorization import (
    AuthorizationContext,
    TenantAccessDeniedError,
)
from app.platform.permissions.codes import LaunchPlatformPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/platform/audit", tags=["Platform Audit"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
AuditReader = Annotated[
    AuthorizationContext,
    Depends(require_permission(LaunchPlatformPermission.AUDIT_READ)),
]


@router.get("", response_model=list[AuditRecordResponse])
async def list_audit_records(
    context: AuditReader,
    session: DatabaseSession,
    branch_id: Annotated[UUID | None, Query()] = None,
    actor_user_id: Annotated[UUID | None, Query()] = None,
    resource_type: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    action: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    outcome: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
    correlation_id: Annotated[UUID | None, Query()] = None,
    occurred_before: Annotated[datetime | None, Query()] = None,
    before_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[AuditRecordResponse]:
    try:
        records = await audit_access_service.list_records(
            session,
            context=context,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            resource_type=resource_type,
            action=action,
            outcome=outcome,
            correlation_id=correlation_id,
            occurred_before=occurred_before,
            before_id=before_id,
            limit=limit,
        )
    except TenantAccessDeniedError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Branch access denied.",
        ) from error
    return [
        AuditRecordResponse.model_validate(record, from_attributes=True)
        for record in records
    ]
