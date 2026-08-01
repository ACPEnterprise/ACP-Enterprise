from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.economics.phase4_service import (
    EconomicsPhase4NotFoundError,
    EconomicsPhase4QueryService,
)
from app.economics.schemas import (
    AllocationStatusResponse,
    AuditPackageResponse,
    BusinessFactListResponse,
    CloseReadinessResponse,
    EvidenceCompletenessResponse,
    ExportStatusResponse,
    FinancialIntegrityResponse,
    ProfitabilityProjectionResponse,
    ProfitMeasurementListResponse,
    ProfitMeasurementResponse,
    ProjectionLineageResponse,
    ReconciliationStatusResponse,
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


def _phase4_not_found(error: EconomicsPhase4NotFoundError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Financial integrity record not found.",
    )


@router.get(
    "/periods/{period_id}/close-readiness", response_model=CloseReadinessResponse
)
async def get_close_readiness(
    period_id: UUID,
    session: DatabaseSession,
    authorization: EconomicsReader,
) -> CloseReadinessResponse:
    try:
        return await EconomicsPhase4QueryService.close_readiness(
            session, authorization.company.id, period_id
        )
    except EconomicsPhase4NotFoundError as error:
        raise _phase4_not_found(error) from error


@router.get(
    "/periods/{period_id}/reconciliation",
    response_model=ReconciliationStatusResponse,
)
async def get_reconciliation_status(
    period_id: UUID,
    session: DatabaseSession,
    authorization: EconomicsReader,
) -> ReconciliationStatusResponse:
    try:
        return await EconomicsPhase4QueryService.reconciliation(
            session, authorization.company.id, period_id
        )
    except EconomicsPhase4NotFoundError as error:
        raise _phase4_not_found(error) from error


@router.get("/periods/{period_id}/allocations", response_model=AllocationStatusResponse)
async def get_allocation_status(
    period_id: UUID,
    session: DatabaseSession,
    authorization: EconomicsReader,
) -> AllocationStatusResponse:
    return await EconomicsPhase4QueryService.allocation_status(
        session, authorization.company.id, period_id
    )


@router.get("/periods/{period_id}/audit-package", response_model=AuditPackageResponse)
async def get_audit_package(
    period_id: UUID,
    session: DatabaseSession,
    authorization: EconomicsReader,
) -> AuditPackageResponse:
    try:
        return await EconomicsPhase4QueryService.audit_package(
            session, authorization.company.id, period_id
        )
    except EconomicsPhase4NotFoundError as error:
        raise _phase4_not_found(error) from error


@router.get("/periods/{period_id}/exports", response_model=list[ExportStatusResponse])
async def get_export_status(
    period_id: UUID,
    session: DatabaseSession,
    authorization: EconomicsReader,
) -> list[ExportStatusResponse]:
    return await EconomicsPhase4QueryService.export_status(
        session, authorization.company.id, period_id
    )


@router.get(
    "/projections/{projection_id}/lineage", response_model=ProjectionLineageResponse
)
async def get_projection_lineage(
    projection_id: UUID,
    session: DatabaseSession,
    authorization: EconomicsReader,
) -> ProjectionLineageResponse:
    try:
        return await EconomicsPhase4QueryService.projection_lineage(
            session, authorization.company.id, projection_id
        )
    except EconomicsPhase4NotFoundError as error:
        raise _phase4_not_found(error) from error


@router.get(
    "/periods/{period_id}/financial-integrity",
    response_model=FinancialIntegrityResponse,
)
async def get_financial_integrity(
    period_id: UUID,
    session: DatabaseSession,
    authorization: EconomicsReader,
) -> FinancialIntegrityResponse:
    try:
        return await EconomicsPhase4QueryService.financial_integrity(
            session, authorization.company.id, period_id
        )
    except EconomicsPhase4NotFoundError as error:
        raise _phase4_not_found(error) from error
