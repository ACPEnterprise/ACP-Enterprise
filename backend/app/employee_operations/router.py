from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

from .errors import EmployeeIdentityNotReady
from .permissions import EmployeeOperationsPermission
from .schemas import EmployeeDayResponse
from .service import employee_day_service

router = APIRouter(prefix="/api/v1/employee-operations", tags=["Employee Operations"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
OwnDayRead = Annotated[
    AuthorizationContext,
    Depends(require_permission(EmployeeOperationsPermission.OWN_DAY_READ)),
]


@router.get("/me/day", response_model=EmployeeDayResponse)
async def own_day(
    context: OwnDayRead,
    session: Session,
    business_date: Annotated[date | None, Query()] = None,
) -> EmployeeDayResponse:
    try:
        return await employee_day_service.day(
            session, context=context, business_date=business_date
        )
    except EmployeeIdentityNotReady as error:
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Employee identity is not ready for self-service operations.",
            ClientRecovery.OWNER_ADMIN_ACTION_REQUIRED,
            current_correlation_id(),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=failure.detail(),
        ) from error
