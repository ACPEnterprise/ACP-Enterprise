from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.inventory.errors import (
    InventoryConflict,
    InventoryNotFound,
    InventoryValidation,
)
from app.inventory.schemas import (
    AdjustmentCreate,
    AdjustmentResponse,
    AllocationResponse,
    CycleCountComplete,
    CycleCountEntryResponse,
    CycleCountRecord,
    CycleCountSessionResponse,
    CycleCountStart,
    InventoryOverview,
    LocationCreate,
    LocationResponse,
    MovementResponse,
    ReservationAllocate,
    ReservationCreate,
    ReservationRelease,
    ReservationResponse,
    TransferCreate,
)
from app.inventory.service import inventory_service
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import InventoryPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/inventory", tags=["Inventory"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(InventoryPermission.READ))
]
ManageContext = Annotated[
    AuthorizationContext, Depends(require_permission(InventoryPermission.MANAGE))
]
MoveContext = Annotated[
    AuthorizationContext, Depends(require_permission(InventoryPermission.MOVE))
]
ReserveContext = Annotated[
    AuthorizationContext, Depends(require_permission(InventoryPermission.RESERVE))
]
AdjustContext = Annotated[
    AuthorizationContext, Depends(require_permission(InventoryPermission.ADJUST))
]
CountContext = Annotated[
    AuthorizationContext, Depends(require_permission(InventoryPermission.COUNT))
]


def translate(error: Exception) -> HTTPException:
    if isinstance(error, InventoryNotFound):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, InventoryConflict):
        return HTTPException(status_code=409, detail=str(error))
    return HTTPException(status_code=422, detail=str(error))


@router.get("/overview", response_model=InventoryOverview)
async def overview(
    context: ReadContext,
    session: DatabaseSession,
    branch_id: UUID | None = None,
) -> InventoryOverview:
    try:
        return await inventory_service.overview(
            session, context=context, branch_id=branch_id
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.post(
    "/locations", response_model=LocationResponse, status_code=status.HTTP_201_CREATED
)
async def create_location(
    data: LocationCreate, context: ManageContext, session: DatabaseSession
) -> LocationResponse:
    try:
        return LocationResponse.model_validate(
            await inventory_service.create_location(session, context=context, data=data)
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.post(
    "/transfers", response_model=MovementResponse, status_code=status.HTTP_201_CREATED
)
async def transfer(
    data: TransferCreate, context: MoveContext, session: DatabaseSession
) -> MovementResponse:
    try:
        return MovementResponse.model_validate(
            await inventory_service.transfer(session, context=context, data=data)
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    data: ReservationCreate, context: ReserveContext, session: DatabaseSession
) -> ReservationResponse:
    try:
        return ReservationResponse.model_validate(
            await inventory_service.create_reservation(
                session, context=context, data=data
            )
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.post(
    "/reservations/{reservation_id}/allocations",
    response_model=AllocationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def allocate(
    reservation_id: UUID,
    data: ReservationAllocate,
    context: ReserveContext,
    session: DatabaseSession,
) -> AllocationResponse:
    try:
        return AllocationResponse.model_validate(
            await inventory_service.allocate(
                session, context=context, reservation_id=reservation_id, data=data
            )
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.post(
    "/reservations/{reservation_id}/release", response_model=ReservationResponse
)
async def release(
    reservation_id: UUID,
    data: ReservationRelease,
    context: ReserveContext,
    session: DatabaseSession,
) -> ReservationResponse:
    try:
        return ReservationResponse.model_validate(
            await inventory_service.release(
                session, context=context, reservation_id=reservation_id, data=data
            )
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.post(
    "/adjustments",
    response_model=AdjustmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_adjustment(
    data: AdjustmentCreate, context: AdjustContext, session: DatabaseSession
) -> AdjustmentResponse:
    try:
        return AdjustmentResponse.model_validate(
            await inventory_service.post_adjustment(session, context=context, data=data)
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.get("/cycle-counts", response_model=tuple[CycleCountSessionResponse, ...])
async def list_cycle_counts(
    context: ReadContext, session: DatabaseSession, branch_id: UUID | None = None
) -> tuple[CycleCountSessionResponse, ...]:
    try:
        return await inventory_service.list_cycle_counts(
            session, context=context, branch_id=branch_id
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.post(
    "/cycle-counts",
    response_model=CycleCountSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_cycle_count(
    data: CycleCountStart, context: CountContext, session: DatabaseSession
) -> CycleCountSessionResponse:
    try:
        return CycleCountSessionResponse.model_validate(
            await inventory_service.start_cycle_count(
                session, context=context, data=data
            )
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.post(
    "/cycle-counts/{cycle_count_id}/entries",
    response_model=CycleCountEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_cycle_count(
    cycle_count_id: UUID,
    data: CycleCountRecord,
    context: CountContext,
    session: DatabaseSession,
) -> CycleCountEntryResponse:
    try:
        return CycleCountEntryResponse.model_validate(
            await inventory_service.record_cycle_count(
                session, context=context, session_id=cycle_count_id, data=data
            )
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.post(
    "/cycle-counts/{cycle_count_id}/complete",
    response_model=CycleCountSessionResponse,
)
async def complete_cycle_count(
    cycle_count_id: UUID,
    data: CycleCountComplete,
    context: AdjustContext,
    session: DatabaseSession,
) -> CycleCountSessionResponse:
    try:
        return CycleCountSessionResponse.model_validate(
            await inventory_service.complete_cycle_count(
                session, context=context, session_id=cycle_count_id, data=data
            )
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error
