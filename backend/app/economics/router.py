from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.economics.schemas import (
    BusinessFactListResponse,
    EvidenceCompletenessResponse,
    ProfitabilityProjectionResponse,
    ProfitMeasurementListResponse,
    ProfitMeasurementResponse,
    StaleMeasurementResponse,
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


@router.get("/facts", response_model=BusinessFactListResponse)
async def list_business_facts(
    session: DatabaseSession,
    authorization: EconomicsReader,
    subject_type: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    subject_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BusinessFactListResponse:
    if subject_id is not None and subject_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="subject_type is required when subject_id is supplied.",
        )
    return await EconomicsQueryService.list_facts(
        session,
        authorization.company.id,
        subject_type,
        subject_id,
        limit,
        offset,
    )


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


@router.get("/jobs/{job_id}/profitability", response_model=ProfitMeasurementResponse)
async def get_job_profitability(
    job_id: UUID,
    session: DatabaseSession,
    authorization: EconomicsReader,
) -> ProfitMeasurementResponse:
    try:
        return await EconomicsQueryService.latest_for_subject(
            session, authorization.company.id, "job", job_id
        )
    except EconomicsMeasurementNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profit measurement not found.",
        ) from error


@router.get(
    "/branches/{branch_id}/profitability",
    response_model=ProfitabilityProjectionResponse,
)
async def get_branch_profitability(
    branch_id: UUID,
    session: DatabaseSession,
    authorization: EconomicsReader,
) -> ProfitabilityProjectionResponse:
    if not authorization.can_access_branch(branch_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Branch access denied."
        )
    return await EconomicsQueryService.branch_profitability(
        session, authorization.company.id, branch_id
    )


@router.get("/company/profitability", response_model=ProfitabilityProjectionResponse)
async def get_company_profitability(
    session: DatabaseSession,
    authorization: EconomicsReader,
) -> ProfitabilityProjectionResponse:
    return await EconomicsQueryService.company_profitability(
        session, authorization.company.id
    )


@router.get(
    "/subjects/{subject_type}/{subject_id}/history",
    response_model=ProfitMeasurementListResponse,
)
async def get_measurement_history(
    subject_type: Annotated[str, Path(min_length=1, max_length=64)],
    subject_id: UUID,
    session: DatabaseSession,
    authorization: EconomicsReader,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProfitMeasurementListResponse:
    return await EconomicsQueryService.history_for_subject(
        session,
        authorization.company.id,
        subject_type,
        subject_id,
        limit,
        offset,
    )


@router.get("/evidence-completeness", response_model=EvidenceCompletenessResponse)
async def get_evidence_completeness(
    session: DatabaseSession,
    authorization: EconomicsReader,
) -> EvidenceCompletenessResponse:
    return await EconomicsQueryService.evidence_completeness(
        session, authorization.company.id
    )


@router.get("/stale-measurements", response_model=list[StaleMeasurementResponse])
async def get_stale_measurements(
    session: DatabaseSession,
    authorization: EconomicsReader,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[StaleMeasurementResponse]:
    return await EconomicsQueryService.stale_measurements(
        session, authorization.company.id, limit
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
