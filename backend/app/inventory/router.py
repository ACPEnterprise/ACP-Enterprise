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
    AllocationResponse,
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
