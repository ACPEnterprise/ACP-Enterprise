from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import require_permission

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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Employee identity is not ready for self-service operations.",
        ) from error
