from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.equipment_readiness.schemas import (
    AttentionOut,
    CatalogCreate,
    CatalogOut,
    ComponentCreate,
    ComponentOut,
    ConfirmationOut,
    CustodyEventOut,
    CustodyTransferRequest,
    DailyConfirmationRequest,
    DailyPrompt,
    IntelligenceEvidence,
    JobFit,
    PlacementCreate,
    PlacementOut,
    ReadinessItem,
    RefreshUpcomingRequest,
    RequirementCreate,
    RequirementOut,
    ResolveAttentionRequest,
)
from app.equipment_readiness.service import (
    EquipmentConflict,
    EquipmentNotFound,
    EquipmentValidation,
    equipment_readiness_service,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AssetPermission, DispatchPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/equipment-readiness", tags=["Equipment Readiness"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Read = Annotated[AuthorizationContext, Depends(require_permission(AssetPermission.READ))]
Manage = Annotated[AuthorizationContext, Depends(require_permission(AssetPermission.MANAGE))]
Custody = Annotated[AuthorizationContext, Depends(require_permission(AssetPermission.CUSTODY))]
DispatchRead = Annotated[AuthorizationContext, Depends(require_permission(DispatchPermission.READ))]


def translated(error: Exception) -> HTTPException:
    if isinstance(error, EquipmentNotFound):
        return HTTPException(404, "Equipment readiness evidence was not found in the authorized scope.")
    if isinstance(error, EquipmentConflict):
        return HTTPException(409, "Equipment readiness changed. Refresh before trying again.")
    return HTTPException(422, "Equipment readiness request requires correction.")


@router.get("/catalog", response_model=list[CatalogOut])
async def catalog(context: Read, session: Session, branch_id: UUID | None = None):
    return [CatalogOut.model_validate(x) for x in await equipment_readiness_service.catalog(session, context, branch_id)]


@router.post("/catalog", response_model=CatalogOut, status_code=status.HTTP_201_CREATED)
async def create_catalog(data: CatalogCreate, context: Manage, session: Session):
    try:
        return CatalogOut.model_validate(await equipment_readiness_service.create_catalog(session, context, data))
    except (EquipmentNotFound, EquipmentConflict, EquipmentValidation) as exc:
        raise translated(exc) from exc


@router.post(
    "/catalog/{catalog_item_id}/components",
    response_model=ComponentOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_component(catalog_item_id: UUID, data: ComponentCreate, context: Manage, session: Session):
    try:
        return ComponentOut.model_validate(
            await equipment_readiness_service.add_component(session, context, catalog_item_id, data)
        )
    except (EquipmentNotFound, EquipmentConflict, EquipmentValidation) as exc:
        raise translated(exc) from exc


@router.post("/placements", response_model=PlacementOut, status_code=status.HTTP_201_CREATED)
async def create_placement(data: PlacementCreate, context: Manage, session: Session):
    try:
        return PlacementOut.model_validate(await equipment_readiness_service.create_placement(session, context, data))
    except (EquipmentNotFound, EquipmentConflict, EquipmentValidation) as exc:
        raise translated(exc) from exc


@router.get("/employees/{employee_id}/daily-prompt", response_model=DailyPrompt)
async def daily_prompt(employee_id: UUID, work_date: date, context: Read, session: Session):
    try:
        return DailyPrompt.model_validate(await equipment_readiness_service.daily_prompt(session, context, employee_id, work_date))
    except (EquipmentNotFound, EquipmentConflict, EquipmentValidation) as exc:
        raise translated(exc) from exc


@router.post("/daily-confirmations", response_model=list[ConfirmationOut])
async def confirm(data: DailyConfirmationRequest, context: Custody, session: Session):
    try:
        return [ConfirmationOut.model_validate(x) for x in await equipment_readiness_service.confirm(session, context, data)]
    except (EquipmentNotFound, EquipmentConflict, EquipmentValidation) as exc:
        raise translated(exc) from exc


@router.post("/placements/{placement_id}/custody", response_model=CustodyEventOut)
async def transfer(placement_id: UUID, data: CustodyTransferRequest, context: Custody, session: Session):
    try:
        return CustodyEventOut.model_validate(await equipment_readiness_service.transfer(session, context, placement_id, data))
    except (EquipmentNotFound, EquipmentConflict, EquipmentValidation) as exc:
        raise translated(exc) from exc


@router.post("/requirements", response_model=RequirementOut, status_code=status.HTTP_201_CREATED)
async def add_requirement(data: RequirementCreate, context: Manage, session: Session):
    try:
        return RequirementOut.model_validate(await equipment_readiness_service.add_requirement(session, context, data))
    except (EquipmentNotFound, EquipmentConflict, EquipmentValidation) as exc:
        raise translated(exc) from exc


@router.get("/dispatch/branches/{branch_id}", response_model=list[ReadinessItem])
async def dispatch_readiness(branch_id: UUID, context: DispatchRead, session: Session):
    try:
        return [ReadinessItem.model_validate(x) for x in await equipment_readiness_service.dispatch_readiness(session, context, branch_id)]
    except (EquipmentNotFound, EquipmentConflict, EquipmentValidation) as exc:
        raise translated(exc) from exc


@router.get("/dispatch/jobs/{job_id}/employees/{employee_id}", response_model=JobFit)
async def job_fit(job_id: UUID, employee_id: UUID, context: DispatchRead, session: Session):
    try:
        return JobFit.model_validate(await equipment_readiness_service.job_fit(session, context, job_id, employee_id))
    except (EquipmentNotFound, EquipmentConflict, EquipmentValidation) as exc:
        raise translated(exc) from exc


@router.get("/attention", response_model=list[AttentionOut])
async def attention(context: Read, session: Session, branch_id: UUID | None = None):
    return [AttentionOut.model_validate(x) for x in await equipment_readiness_service.attention(session, context, branch_id)]


@router.post("/attention/refresh-upcoming", response_model=list[AttentionOut])
async def refresh_upcoming(data: RefreshUpcomingRequest, context: Manage, session: Session):
    try:
        rows = await equipment_readiness_service.refresh_upcoming_attention(
            session, context, data.branch_id, data.as_of, data.horizon_hours
        )
        return [AttentionOut.model_validate(x) for x in rows]
    except (EquipmentNotFound, EquipmentConflict, EquipmentValidation) as exc:
        raise translated(exc) from exc


@router.post("/attention/{attention_id}/resolve", response_model=AttentionOut)
async def resolve_attention(attention_id: UUID, data: ResolveAttentionRequest, context: Manage, session: Session):
    try:
        return AttentionOut.model_validate(await equipment_readiness_service.resolve_attention(session, context, attention_id, data.resolution_note, data.expected_version))
    except (EquipmentNotFound, EquipmentConflict, EquipmentValidation) as exc:
        raise translated(exc) from exc


@router.get("/intelligence-evidence", response_model=IntelligenceEvidence)
async def intelligence(context: Read, session: Session):
    return IntelligenceEvidence.model_validate(await equipment_readiness_service.intelligence(session, context))
