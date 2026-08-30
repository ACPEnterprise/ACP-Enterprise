from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

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
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Inventory resource was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        return HTTPException(status_code=404, detail=failure.detail())
    if isinstance(error, InventoryConflict):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Inventory operation conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(status_code=409, detail=failure.detail())
    failure = SafeFailure(
        FailureCode.VALIDATION,
        "Inventory request requires correction.",
        ClientRecovery.USER_CORRECTION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(status_code=422, detail=failure.detail())


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
    context: ReadContext,
    session: DatabaseSession,
    branch_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> tuple[CycleCountSessionResponse, ...]:
    try:
        return await inventory_service.list_cycle_counts(
            session,
            context=context,
            branch_id=branch_id,
            limit=limit,
            offset=offset,
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
