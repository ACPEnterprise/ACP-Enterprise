from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import WorkforcePermission
from app.platform.permissions.dependencies import require_permission
from app.workforce.schemas import (
    WorkforceDirectory,
    WorkforceEligibilityRequest,
    WorkforceEligibilityResponse,
    WorkforceEmployeeDetail,
)
from app.workforce.service import workforce_operations_service

router = APIRouter(prefix="/api/v1/workforce", tags=["Workforce"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(WorkforcePermission.READ))
]


@router.get("/employees", response_model=WorkforceDirectory)
async def directory(context: ReadContext, session: Session) -> WorkforceDirectory:
    return await workforce_operations_service.directory(session, context=context)


@router.get("/employees/{employee_id}", response_model=WorkforceEmployeeDetail)
async def detail(
    employee_id: UUID, context: ReadContext, session: Session
) -> WorkforceEmployeeDetail:
    result = await workforce_operations_service.detail(
        session, context=context, employee_id=employee_id
    )
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Workforce profile was not found."
        )
    return result


@router.post("/eligibility", response_model=WorkforceEligibilityResponse)
async def eligibility(
    payload: WorkforceEligibilityRequest, context: ReadContext, session: Session
) -> WorkforceEligibilityResponse:
    return await workforce_operations_service.eligibility(
        session, context=context, request=payload
    )
