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
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

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
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[AuditRecordResponse]:
    try:
        records = await audit_access_service.list_records(
            session,
            context=context,
            branch_id=branch_id,
            limit=limit,
        )
    except TenantAccessDeniedError as error:
        failure = SafeFailure(
            FailureCode.FORBIDDEN,
            "Branch access denied.",
            ClientRecovery.OWNER_ADMIN_ACTION_REQUIRED,
            current_correlation_id(),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=failure.detail(),
        ) from error
    return [
        AuditRecordResponse.model_validate(record, from_attributes=True)
        for record in records
    ]
