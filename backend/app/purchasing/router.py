from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import PurchasingPermission
from app.platform.permissions.dependencies import require_permission

from .errors import (
    PurchasingConflict,
    PurchasingError,
    PurchasingNotFound,
    PurchasingValidation,
)
from .schemas import (
    PurchaseOrderCreate,
    PurchaseOrderItem,
    PurchaseOrderLineItem,
    PurchaseOrderLineUpdate,
    PurchaseOrderLineWrite,
    PurchaseOrderUpdate,
    PurchasingWorkspace,
    TransitionCommand,
    VendorCreate,
    VendorItem,
    VendorUpdate,
)
from .service import purchasing_service

router = APIRouter(prefix="/api/v1/purchasing", tags=["Purchasing"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(PurchasingPermission.READ))
]
ManageContext = Annotated[
    AuthorizationContext, Depends(require_permission(PurchasingPermission.MANAGE))
]
ApproveContext = Annotated[
    AuthorizationContext, Depends(require_permission(PurchasingPermission.APPROVE))
]
IssueContext = Annotated[
    AuthorizationContext, Depends(require_permission(PurchasingPermission.ISSUE))
]


def http_error(error: PurchasingError) -> HTTPException:
    if isinstance(error, PurchasingNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, PurchasingConflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    if isinstance(error, PurchasingValidation):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Purchasing operation failed")


@router.get("", response_model=PurchasingWorkspace)
async def workspace(
    context: ReadContext,
    session: DatabaseSession,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> PurchasingWorkspace:
    return await purchasing_service.workspace(session, context=context, search=search)


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrderItem)
async def get_order(
    po_id: UUID, context: ReadContext, session: DatabaseSession
) -> PurchaseOrderItem:
    try:
        return await purchasing_service.get_order(session, context=context, po_id=po_id)
    except PurchasingError as error:
        raise http_error(error) from error


@router.post("/vendors", response_model=VendorItem, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    payload: VendorCreate, context: ManageContext, session: DatabaseSession
) -> VendorItem:
    try:
        return VendorItem.model_validate(
            await purchasing_service.create_vendor(
                session, context=context, payload=payload
            )
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.put("/vendors/{vendor_id}", response_model=VendorItem)
async def update_vendor(
    vendor_id: UUID,
    payload: VendorUpdate,
    context: ManageContext,
    session: DatabaseSession,
) -> VendorItem:
    try:
        return VendorItem.model_validate(
            await purchasing_service.update_vendor(
                session, context=context, vendor_id=vendor_id, payload=payload
            )
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.post(
    "/purchase-orders",
    response_model=PurchaseOrderItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    payload: PurchaseOrderCreate, context: ManageContext, session: DatabaseSession
) -> PurchaseOrderItem:
    try:
        record = await purchasing_service.create_order(
            session, context=context, payload=payload
        )
        return await purchasing_service.get_order(
            session, context=context, po_id=record.id
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.put("/purchase-orders/{po_id}", response_model=PurchaseOrderItem)
async def update_order(
    po_id: UUID,
    payload: PurchaseOrderUpdate,
    context: ManageContext,
    session: DatabaseSession,
) -> PurchaseOrderItem:
    try:
        await purchasing_service.update_order(
            session, context=context, po_id=po_id, payload=payload
        )
        return await purchasing_service.get_order(session, context=context, po_id=po_id)
    except PurchasingError as error:
        raise http_error(error) from error


@router.post(
    "/purchase-orders/{po_id}/lines",
    response_model=PurchaseOrderLineItem,
    status_code=status.HTTP_201_CREATED,
)
async def add_line(
    po_id: UUID,
    payload: PurchaseOrderLineWrite,
    context: ManageContext,
    session: DatabaseSession,
) -> PurchaseOrderLineItem:
    try:
        return PurchaseOrderLineItem.model_validate(
            await purchasing_service.add_line(
                session, context=context, po_id=po_id, payload=payload
            )
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.put(
    "/purchase-orders/{po_id}/lines/{line_id}", response_model=PurchaseOrderLineItem
)
async def update_line(
    po_id: UUID,
    line_id: UUID,
    payload: PurchaseOrderLineUpdate,
    context: ManageContext,
    session: DatabaseSession,
) -> PurchaseOrderLineItem:
    try:
        return PurchaseOrderLineItem.model_validate(
            await purchasing_service.update_line(
                session, context=context, po_id=po_id, line_id=line_id, payload=payload
            )
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.post("/purchase-orders/{po_id}/submit", response_model=PurchaseOrderItem)
async def submit(
    po_id: UUID,
    payload: TransitionCommand,
    context: ManageContext,
    session: DatabaseSession,
) -> PurchaseOrderItem:
    return await _transition(po_id, "submit", payload, context, session)


@router.post("/purchase-orders/{po_id}/approve", response_model=PurchaseOrderItem)
async def approve(
    po_id: UUID,
    payload: TransitionCommand,
    context: ApproveContext,
    session: DatabaseSession,
) -> PurchaseOrderItem:
    return await _transition(po_id, "approve", payload, context, session)


@router.post("/purchase-orders/{po_id}/issue", response_model=PurchaseOrderItem)
async def issue(
    po_id: UUID,
    payload: TransitionCommand,
    context: IssueContext,
    session: DatabaseSession,
) -> PurchaseOrderItem:
    return await _transition(po_id, "issue", payload, context, session)


@router.post("/purchase-orders/{po_id}/cancel", response_model=PurchaseOrderItem)
async def cancel(
    po_id: UUID,
    payload: TransitionCommand,
    context: IssueContext,
    session: DatabaseSession,
) -> PurchaseOrderItem:
    return await _transition(po_id, "cancel", payload, context, session)


@router.post("/purchase-orders/{po_id}/close", response_model=PurchaseOrderItem)
async def close(
    po_id: UUID,
    payload: TransitionCommand,
    context: IssueContext,
    session: DatabaseSession,
) -> PurchaseOrderItem:
    return await _transition(po_id, "close", payload, context, session)


async def _transition(
    po_id: UUID,
    target: str,
    payload: TransitionCommand,
    context: AuthorizationContext,
    session: AsyncSession,
) -> PurchaseOrderItem:
    try:
        await purchasing_service.transition(
            session, context=context, po_id=po_id, target=target, payload=payload
        )
        return await purchasing_service.get_order(session, context=context, po_id=po_id)
    except PurchasingError as error:
        raise http_error(error) from error
