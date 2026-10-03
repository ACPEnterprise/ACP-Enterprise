from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.inventory.common_stock_seed import (
    ACCEPTED_COMMON_STOCK_SOURCE_DIGEST,
    CommonStockWorkbook,
    common_stock_admission_service,
    read_common_stock_workbook,
)
from app.inventory.costing import material_costing_service
from app.inventory.errors import (
    InventoryConflict,
    InventoryNotFound,
    InventoryValidation,
)
from app.inventory.job_materials import job_materials_service
from app.inventory.schemas import (
    AdjustmentCreate,
    AdjustmentResponse,
    AllocationResponse,
    CommonStockHeldRow,
    CommonStockSeedAdmission,
    CommonStockSeedPreview,
    CycleCountComplete,
    CycleCountEntryResponse,
    CycleCountRecord,
    CycleCountSessionResponse,
    CycleCountStart,
    InventoryOverview,
    ItemCreate,
    ItemResponse,
    JobMaterialsResponse,
    LocationCreate,
    LocationResponse,
    MaterialCostReadinessResponse,
    MaterialIssueCreate,
    MaterialIssueResponse,
    MaterialIssueReverse,
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
MAX_COMMON_STOCK_WORKBOOK_BYTES = 25 * 1024 * 1024
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


def _read_common_stock_upload(
    payload: bytes, source_filename: str
) -> CommonStockWorkbook:
    if not payload or len(payload) > MAX_COMMON_STOCK_WORKBOOK_BYTES:
        raise InventoryValidation("Common stock workbook size is invalid")
    if Path(source_filename).name != source_filename or not source_filename.endswith(
        ".numbers"
    ):
        raise InventoryValidation("Common stock source must be a Numbers workbook")
    try:
        with NamedTemporaryFile(suffix=".numbers") as temporary:
            temporary.write(payload)
            temporary.flush()
            workbook = read_common_stock_workbook(Path(temporary.name))
    except (OSError, ValueError) as error:
        raise InventoryValidation("Common stock workbook is invalid") from error
    if workbook.source_digest != ACCEPTED_COMMON_STOCK_SOURCE_DIGEST:
        raise InventoryValidation(
            "Common stock workbook is not the accepted owner source"
        )
    return CommonStockWorkbook(
        source_path=Path(source_filename),
        source_digest=workbook.source_digest,
        columns=workbook.columns,
        rows=workbook.rows,
    )


def _common_stock_preview(workbook: CommonStockWorkbook) -> CommonStockSeedPreview:
    return CommonStockSeedPreview(
        source_filename=workbook.source_path.name,
        source_digest=workbook.source_digest,
        source_rows_read=len(workbook.rows),
        acp_materials_proposed=workbook.proposed_count,
        rows_held=workbook.held_count,
        vendor_cross_references_proposed=workbook.proposed_count,
        purchase_cost_evidence_proposed=workbook.proposed_count,
        held_rows=tuple(
            CommonStockHeldRow(
                source_row_number=row.source_row_number,
                reason=row.hold_reason or "unknown",
            )
            for row in workbook.rows
            if row.disposition == "held"
        ),
    )


@router.post("/common-stock-seed/preview", response_model=CommonStockSeedPreview)
async def preview_common_stock_seed(
    context: ManageContext,
    source_filename: Annotated[str, Query(min_length=1, max_length=240)],
    payload: Annotated[bytes, Body(media_type="application/octet-stream")],
) -> CommonStockSeedPreview:
    del context
    try:
        return _common_stock_preview(
            _read_common_stock_upload(payload, source_filename)
        )
    except (InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.post("/common-stock-seed/admit", response_model=CommonStockSeedAdmission)
async def admit_common_stock_seed(
    context: ManageContext,
    session: DatabaseSession,
    source_filename: Annotated[str, Query(min_length=1, max_length=240)],
    expected_source_digest: Annotated[str, Query(min_length=64, max_length=64)],
    reason: Annotated[str, Query(min_length=3, max_length=500)],
    payload: Annotated[bytes, Body(media_type="application/octet-stream")],
) -> CommonStockSeedAdmission:
    try:
        workbook = _read_common_stock_upload(payload, source_filename)
        if workbook.source_digest != expected_source_digest.lower():
            raise InventoryConflict("Workbook changed after preview")
        admitted, held = await common_stock_admission_service.admit_authorized(
            session, workbook=workbook, context=context, reason=reason
        )
        preview = _common_stock_preview(workbook)
        return CommonStockSeedAdmission(
            **preview.model_dump(), records_admitted=admitted, records_held=held
        )
    except (InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


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


@router.get("/jobs/{job_id}/materials", response_model=JobMaterialsResponse)
async def job_materials(
    job_id: UUID,
    context: ReadContext,
    session: DatabaseSession,
) -> JobMaterialsResponse:
    try:
        return await job_materials_service.projection(
            session, context=context, job_id=job_id
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.put("/items/{code}", response_model=ItemResponse)
async def create_item(
    code: str, data: ItemCreate, context: ManageContext, session: DatabaseSession
) -> ItemResponse:
    try:
        return ItemResponse.model_validate(
            await inventory_service.create_item(
                session, context=context, code=code, data=data
            )
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.get("/cost-readiness", response_model=MaterialCostReadinessResponse)
async def cost_readiness(
    context: ReadContext,
    session: DatabaseSession,
) -> MaterialCostReadinessResponse:
    return await material_costing_service.readiness(session, context=context)


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
    "/reservations/{reservation_id}/issues",
    response_model=MaterialIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_material(
    reservation_id: UUID,
    data: MaterialIssueCreate,
    context: ReserveContext,
    session: DatabaseSession,
) -> MaterialIssueResponse:
    try:
        return MaterialIssueResponse.model_validate(
            await inventory_service.issue_material(
                session,
                context=context,
                reservation_id=reservation_id,
                data=data,
            )
        )
    except (InventoryNotFound, InventoryConflict, InventoryValidation) as error:
        raise translate(error) from error


@router.post(
    "/material-issues/{issue_id}/reversal",
    response_model=MaterialIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def reverse_material_issue(
    issue_id: UUID,
    data: MaterialIssueReverse,
    context: ReserveContext,
    session: DatabaseSession,
) -> MaterialIssueResponse:
    try:
        return MaterialIssueResponse.model_validate(
            await inventory_service.reverse_material_issue(
                session, context=context, issue_id=issue_id, data=data
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
