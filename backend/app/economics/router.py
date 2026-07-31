from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.economics.schemas import (
    ProfitMeasurementListResponse,
    ProfitMeasurementResponse,
)
from app.economics.service import (
    EconomicsMeasurementNotFoundError,
    EconomicsQueryService,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EconomicsPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/economics", tags=["Business Economics"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
EconomicsReader = Annotated[
    AuthorizationContext, Depends(require_permission(EconomicsPermission.READ))
]


@router.get("/measurements", response_model=ProfitMeasurementListResponse)
async def list_profit_measurements(
    session: DatabaseSession,
    authorization: EconomicsReader,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProfitMeasurementListResponse:
    return await EconomicsQueryService.list_measurements(
        session, authorization.company.id, limit, offset
    )


@router.get(
    "/subjects/{subject_type}/{subject_id}/profitability",
    response_model=ProfitMeasurementResponse,
)
async def get_subject_profitability(
    subject_type: Annotated[str, Path(min_length=1, max_length=64)],
    subject_id: UUID,
    session: DatabaseSession,
    authorization: EconomicsReader,
) -> ProfitMeasurementResponse:
    try:
        return await EconomicsQueryService.latest_for_subject(
            session, authorization.company.id, subject_type, subject_id
        )
    except EconomicsMeasurementNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profit measurement not found.",
        ) from error
