from datetime import datetime
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
    BranchPurchasingPolicyItem,
    BranchPurchasingPolicyWrite,
    CreatePurchaseReturnCommand,
    DecidePurchaseOrderChangeCommand,
    DiscrepancyItem,
    PurchaseOrderArtifactItem,
    PurchaseOrderChangeItem,
    PurchaseOrderCreate,
    PurchaseOrderDispositionCommand,
    PurchaseOrderDispositionItem,
    PurchaseOrderItem,
    PurchaseOrderLineItem,
    PurchaseOrderLineUpdate,
    PurchaseOrderLineWrite,
    PurchaseOrderUpdate,
    PurchaseRequisitionCreate,
    PurchaseRequisitionItem,
    PurchaseRequisitionTransition,
    PurchaseReturnItem,
    PurchaseReturnTransitionCommand,
    PurchasingWorkspace,
    ReceiptItem,
    ReceiptLineItem,
    ReceivingReconciliation,
    RecordReceiptCommand,
    ReplenishmentDecisionCommand,
    ReplenishmentDecisionItem,
    ReplenishmentWorkbench,
    ReplenishmentWorkbenchRequest,
    RequestPurchaseOrderChangeCommand,
    ResolveDiscrepancyCommand,
    SupplyChainPolicyItem,
    SupplyChainPolicyWrite,
    TransitionCommand,
    VendorCreate,
    VendorItem,
    VendorPerformanceEvidenceReport,
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
ReceiveContext = Annotated[
    AuthorizationContext, Depends(require_permission(PurchasingPermission.RECEIVE))
]
ResolveContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(PurchasingPermission.RESOLVE_DISCREPANCY)),
]
ReturnCreateContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(PurchasingPermission.RETURN_CREATE)),
]
ReturnAuthorizeContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(PurchasingPermission.RETURN_AUTHORIZE)),
]
ReturnMoveContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(PurchasingPermission.RETURN_MOVE)),
]
ReturnCloseContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(PurchasingPermission.RETURN_CLOSE)),
]
ChangeRequestContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(PurchasingPermission.CHANGE_REQUEST)),
]
ChangeApproveContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(PurchasingPermission.CHANGE_APPROVE)),
]
CloseContext = Annotated[
    AuthorizationContext, Depends(require_permission(PurchasingPermission.CLOSE))
]
CancelContext = Annotated[
    AuthorizationContext, Depends(require_permission(PurchasingPermission.CANCEL))
]


def http_error(error: PurchasingError) -> HTTPException:
    if isinstance(error, PurchasingNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, PurchasingConflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    if isinstance(error, PurchasingValidation):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Purchasing operation failed")


@router.post(
    "/requisitions",
    response_model=PurchaseRequisitionItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_requisition(
    payload: PurchaseRequisitionCreate, context: ManageContext, session: DatabaseSession
) -> PurchaseRequisitionItem:
    try:
        return await purchasing_service.create_requisition(
            session, context=context, payload=payload
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.post(
    "/requisitions/{requisition_id}/submit", response_model=PurchaseRequisitionItem
)
async def submit_requisition(
    requisition_id: UUID,
    payload: PurchaseRequisitionTransition,
    context: ManageContext,
    session: DatabaseSession,
) -> PurchaseRequisitionItem:
    try:
        return await purchasing_service.transition_requisition(
            session,
            context=context,
            requisition_id=requisition_id,
            action="submit",
            payload=payload,
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.post(
    "/requisitions/{requisition_id}/{action}", response_model=PurchaseRequisitionItem
)
async def decide_requisition(
    requisition_id: UUID,
    action: str,
    payload: PurchaseRequisitionTransition,
    context: ApproveContext,
    session: DatabaseSession,
) -> PurchaseRequisitionItem:
    if action not in {"approve", "reject", "convert", "cancel"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unsupported requisition action")
    try:
        return await purchasing_service.transition_requisition(
            session,
            context=context,
            requisition_id=requisition_id,
            action=action,
            payload=payload,
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.put("/supply-chain-policies", response_model=SupplyChainPolicyItem)
async def configure_supply_chain_policy(
    payload: SupplyChainPolicyWrite, context: ManageContext, session: DatabaseSession
) -> SupplyChainPolicyItem:
    try:
        return await purchasing_service.configure_supply_chain_policy(
            session, context=context, payload=payload
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.get("/branch-policies", response_model=tuple[BranchPurchasingPolicyItem, ...])
async def branch_policies(
    context: ReadContext, session: DatabaseSession
) -> tuple[BranchPurchasingPolicyItem, ...]:
    return await purchasing_service.branch_policies(session, context=context)


@router.put("/branch-policies", response_model=BranchPurchasingPolicyItem)
async def configure_branch_policy(
    payload: BranchPurchasingPolicyWrite,
    context: ManageContext,
    session: DatabaseSession,
) -> BranchPurchasingPolicyItem:
    try:
        return await purchasing_service.configure_branch_policy(
            session, context=context, payload=payload
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.get("", response_model=PurchasingWorkspace)
async def workspace(
    context: ReadContext,
    session: DatabaseSession,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> PurchasingWorkspace:
    return await purchasing_service.workspace(session, context=context, search=search)


@router.post("/replenishment/workbench", response_model=ReplenishmentWorkbench)
async def replenishment_workbench(
    payload: ReplenishmentWorkbenchRequest,
    context: ReadContext,
    session: DatabaseSession,
) -> ReplenishmentWorkbench:
    try:
        return await purchasing_service.replenishment_workbench(
            session, context=context, payload=payload
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.post("/replenishment/decisions", response_model=ReplenishmentDecisionItem)
async def decide_replenishment(
    payload: ReplenishmentDecisionCommand,
    context: ApproveContext,
    session: DatabaseSession,
) -> ReplenishmentDecisionItem:
    try:
        return await purchasing_service.decide_replenishment(
            session, context=context, payload=payload
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrderItem)
async def get_order(
    po_id: UUID, context: ReadContext, session: DatabaseSession
) -> PurchaseOrderItem:
    try:
        return await purchasing_service.get_order(session, context=context, po_id=po_id)
    except PurchasingError as error:
        raise http_error(error) from error


@router.get(
    "/purchase-orders/{po_id}/artifact", response_model=PurchaseOrderArtifactItem
)
async def purchase_order_artifact(
    po_id: UUID, context: ReadContext, session: DatabaseSession
) -> PurchaseOrderArtifactItem:
    try:
        return await purchasing_service.purchase_order_artifact(
            session, context=context, po_id=po_id
        )
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


@router.get(
    "/vendors/{vendor_id}/performance-evidence",
    response_model=VendorPerformanceEvidenceReport,
)
async def vendor_performance_evidence(
    vendor_id: UUID,
    context: ReadContext,
    session: DatabaseSession,
    from_at: Annotated[datetime | None, Query()] = None,
    to_at: Annotated[datetime | None, Query()] = None,
) -> VendorPerformanceEvidenceReport:
    try:
        return await purchasing_service.vendor_performance_evidence(
            session,
            context=context,
            vendor_id=vendor_id,
            from_at=from_at,
            to_at=to_at,
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


async def _terminal_disposition(
    po_id: UUID,
    action: str,
    payload: PurchaseOrderDispositionCommand,
    context: AuthorizationContext,
    session: AsyncSession,
) -> PurchaseOrderDispositionItem:
    try:
        return PurchaseOrderDispositionItem.model_validate(
            await purchasing_service.terminal_disposition(
                session,
                context=context,
                po_id=po_id,
                action=action,
                payload=payload,
            )
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.post(
    "/purchase-orders/{po_id}/dispositions/complete",
    response_model=PurchaseOrderDispositionItem,
)
async def complete_purchase_order(
    po_id: UUID,
    payload: PurchaseOrderDispositionCommand,
    context: CloseContext,
    session: DatabaseSession,
) -> PurchaseOrderDispositionItem:
    return await _terminal_disposition(po_id, "complete", payload, context, session)


@router.post(
    "/purchase-orders/{po_id}/dispositions/cancel",
    response_model=PurchaseOrderDispositionItem,
)
async def cancel_purchase_order_disposition(
    po_id: UUID,
    payload: PurchaseOrderDispositionCommand,
    context: CancelContext,
    session: DatabaseSession,
) -> PurchaseOrderDispositionItem:
    return await _terminal_disposition(po_id, "cancel", payload, context, session)


@router.post(
    "/purchase-orders/{po_id}/receipts",
    response_model=ReceiptItem,
    status_code=status.HTTP_201_CREATED,
)
async def record_receipt(
    po_id: UUID,
    payload: RecordReceiptCommand,
    context: ReceiveContext,
    session: DatabaseSession,
) -> ReceiptItem:
    try:
        record = await purchasing_service.record_receipt(
            session, context=context, po_id=po_id, payload=payload
        )
        lines = await purchasing_service.repository.receipt_lines(
            session, context.company.id, record.id
        )
        return ReceiptItem.model_validate(record).model_copy(
            update={
                "lines": tuple(ReceiptLineItem.model_validate(item) for item in lines)
            }
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.get(
    "/purchase-orders/{po_id}/receiving-reconciliation",
    response_model=ReceivingReconciliation,
)
async def receiving_reconciliation(
    po_id: UUID,
    context: ReadContext,
    session: DatabaseSession,
) -> ReceivingReconciliation:
    try:
        return await purchasing_service.receiving_reconciliation(
            session, context=context, po_id=po_id
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.post(
    "/purchase-orders/{po_id}/discrepancies/{discrepancy_id}/resolve",
    response_model=DiscrepancyItem,
)
async def resolve_discrepancy(
    po_id: UUID,
    discrepancy_id: UUID,
    payload: ResolveDiscrepancyCommand,
    context: ResolveContext,
    session: DatabaseSession,
) -> DiscrepancyItem:
    try:
        return DiscrepancyItem.model_validate(
            await purchasing_service.resolve_discrepancy(
                session,
                context=context,
                po_id=po_id,
                discrepancy_id=discrepancy_id,
                payload=payload,
            )
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.post(
    "/purchase-orders/{po_id}/returns",
    response_model=PurchaseReturnItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_purchase_return(
    po_id: UUID,
    payload: CreatePurchaseReturnCommand,
    context: ReturnCreateContext,
    session: DatabaseSession,
) -> PurchaseReturnItem:
    try:
        return PurchaseReturnItem.model_validate(
            await purchasing_service.create_purchase_return(
                session, context=context, po_id=po_id, payload=payload
            )
        )
    except PurchasingError as error:
        raise http_error(error) from error


async def _return_transition(
    po_id: UUID,
    return_id: UUID,
    action: str,
    payload: PurchaseReturnTransitionCommand,
    context: AuthorizationContext,
    session: AsyncSession,
) -> PurchaseReturnItem:
    try:
        return PurchaseReturnItem.model_validate(
            await purchasing_service.transition_purchase_return(
                session,
                context=context,
                po_id=po_id,
                return_id=return_id,
                action=action,
                payload=payload,
            )
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.post(
    "/purchase-orders/{po_id}/returns/{return_id}/request-authorization",
    response_model=PurchaseReturnItem,
)
async def request_return_authorization(
    po_id: UUID,
    return_id: UUID,
    payload: PurchaseReturnTransitionCommand,
    context: ReturnCreateContext,
    session: DatabaseSession,
) -> PurchaseReturnItem:
    return await _return_transition(
        po_id, return_id, "request_authorization", payload, context, session
    )


@router.post(
    "/purchase-orders/{po_id}/returns/{return_id}/authorize",
    response_model=PurchaseReturnItem,
)
async def authorize_return(
    po_id: UUID,
    return_id: UUID,
    payload: PurchaseReturnTransitionCommand,
    context: ReturnAuthorizeContext,
    session: DatabaseSession,
) -> PurchaseReturnItem:
    return await _return_transition(
        po_id, return_id, "authorize", payload, context, session
    )


@router.post(
    "/purchase-orders/{po_id}/returns/{return_id}/deny",
    response_model=PurchaseReturnItem,
)
async def deny_return(
    po_id: UUID,
    return_id: UUID,
    payload: PurchaseReturnTransitionCommand,
    context: ReturnAuthorizeContext,
    session: DatabaseSession,
) -> PurchaseReturnItem:
    return await _return_transition(po_id, return_id, "deny", payload, context, session)


@router.post(
    "/purchase-orders/{po_id}/returns/{return_id}/ready",
    response_model=PurchaseReturnItem,
)
async def ready_return(
    po_id: UUID,
    return_id: UUID,
    payload: PurchaseReturnTransitionCommand,
    context: ReturnMoveContext,
    session: DatabaseSession,
) -> PurchaseReturnItem:
    return await _return_transition(
        po_id, return_id, "mark_ready", payload, context, session
    )


@router.post(
    "/purchase-orders/{po_id}/returns/{return_id}/returned",
    response_model=PurchaseReturnItem,
)
async def returned_return(
    po_id: UUID,
    return_id: UUID,
    payload: PurchaseReturnTransitionCommand,
    context: ReturnMoveContext,
    session: DatabaseSession,
) -> PurchaseReturnItem:
    return await _return_transition(
        po_id, return_id, "mark_returned", payload, context, session
    )


@router.post(
    "/purchase-orders/{po_id}/returns/{return_id}/vendor-received",
    response_model=PurchaseReturnItem,
)
async def vendor_received_return(
    po_id: UUID,
    return_id: UUID,
    payload: PurchaseReturnTransitionCommand,
    context: ReturnMoveContext,
    session: DatabaseSession,
) -> PurchaseReturnItem:
    return await _return_transition(
        po_id, return_id, "vendor_received", payload, context, session
    )


@router.post(
    "/purchase-orders/{po_id}/returns/{return_id}/close",
    response_model=PurchaseReturnItem,
)
async def close_return(
    po_id: UUID,
    return_id: UUID,
    payload: PurchaseReturnTransitionCommand,
    context: ReturnCloseContext,
    session: DatabaseSession,
) -> PurchaseReturnItem:
    return await _return_transition(
        po_id, return_id, "close", payload, context, session
    )


@router.post(
    "/purchase-orders/{po_id}/returns/{return_id}/cancel",
    response_model=PurchaseReturnItem,
)
async def cancel_return(
    po_id: UUID,
    return_id: UUID,
    payload: PurchaseReturnTransitionCommand,
    context: ReturnCloseContext,
    session: DatabaseSession,
) -> PurchaseReturnItem:
    return await _return_transition(
        po_id, return_id, "cancel", payload, context, session
    )


@router.post(
    "/purchase-orders/{po_id}/changes",
    response_model=PurchaseOrderChangeItem,
    status_code=status.HTTP_201_CREATED,
)
async def request_po_change(
    po_id: UUID,
    payload: RequestPurchaseOrderChangeCommand,
    context: ChangeRequestContext,
    session: DatabaseSession,
) -> PurchaseOrderChangeItem:
    try:
        return PurchaseOrderChangeItem.model_validate(
            await purchasing_service.request_change(
                session, context=context, po_id=po_id, payload=payload
            )
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.post(
    "/purchase-orders/{po_id}/changes/{change_id}/approve",
    response_model=PurchaseOrderChangeItem,
)
async def approve_po_change(
    po_id: UUID,
    change_id: UUID,
    payload: DecidePurchaseOrderChangeCommand,
    context: ChangeApproveContext,
    session: DatabaseSession,
) -> PurchaseOrderChangeItem:
    try:
        return PurchaseOrderChangeItem.model_validate(
            await purchasing_service.decide_change(
                session,
                context=context,
                po_id=po_id,
                change_id=change_id,
                action="approve",
                payload=payload,
            )
        )
    except PurchasingError as error:
        raise http_error(error) from error


@router.post(
    "/purchase-orders/{po_id}/changes/{change_id}/reject",
    response_model=PurchaseOrderChangeItem,
)
async def reject_po_change(
    po_id: UUID,
    change_id: UUID,
    payload: DecidePurchaseOrderChangeCommand,
    context: ChangeApproveContext,
    session: DatabaseSession,
) -> PurchaseOrderChangeItem:
    try:
        return PurchaseOrderChangeItem.model_validate(
            await purchasing_service.decide_change(
                session,
                context=context,
                po_id=po_id,
                change_id=change_id,
                action="reject",
                payload=payload,
            )
        )
    except PurchasingError as error:
        raise http_error(error) from error


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
