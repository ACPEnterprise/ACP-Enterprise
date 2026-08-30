from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.payments.contracts import ApplyReceipt, CreateIntent, RequestRefund
from app.payments.errors import PaymentConflict, PaymentError, PaymentNotFound
from app.payments.schemas import (
    ApplyInput,
    CollectInput,
    IntentItem,
    ReceiptItem,
    RefundInput,
    RefundItem,
)
from app.payments.service import payment_service
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import PaymentPermission
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

router = APIRouter(prefix="/api/v1/payments", tags=["Payments"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Read = Annotated[AuthorizationContext, Depends(require_permission(PaymentPermission.READ))]
Collect = Annotated[AuthorizationContext, Depends(require_permission(PaymentPermission.COLLECT))]
Apply = Annotated[AuthorizationContext, Depends(require_permission(PaymentPermission.APPLY))]
RefundPermission = Annotated[AuthorizationContext, Depends(require_permission(PaymentPermission.REFUND))]


def _error(exc: PaymentError) -> HTTPException:
    if isinstance(exc, PaymentNotFound):
        return _not_found()
    if isinstance(exc, PaymentConflict):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Payment operation conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_409_CONFLICT, failure.detail())
    failure = SafeFailure(
        FailureCode.VALIDATION,
        "Payment request violates domain validation rules.",
        ClientRecovery.USER_CORRECTION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, failure.detail())


def _not_found() -> HTTPException:
    failure = SafeFailure(
        FailureCode.NOT_FOUND,
        "Payment resource was not found.",
        ClientRecovery.TERMINAL_FAILURE,
        current_correlation_id(),
    )
    return HTTPException(status.HTTP_404_NOT_FOUND, failure.detail())


def _branch(context: AuthorizationContext, branch_id: UUID) -> None:
    if not context.can_access_branch(branch_id):
        raise _not_found()


@router.post("/intents", response_model=IntentItem, status_code=status.HTTP_201_CREATED)
async def collect_payment(payload: CollectInput, context: Collect, session: Session) -> IntentItem:
    _branch(context, payload.branch_id)
    try:
        return IntentItem.model_validate(await payment_service.collect(session, CreateIntent(company_id=context.company.id, actor_user_id=context.user.id, **payload.model_dump())))
    except PaymentError as exc:
        raise _error(exc) from exc


@router.get("/receipts", response_model=list[ReceiptItem])
async def list_receipts(
    context: Read,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReceiptItem]:
    rows = await payment_service.list_receipts(
        session,
        context.company.id,
        context.authorized_branch_ids,
        limit=limit,
        offset=offset,
    )
    return [ReceiptItem.model_validate(row) for row in rows]


@router.get("/receipts/{receipt_id}", response_model=ReceiptItem)
async def get_receipt(receipt_id: UUID, context: Read, session: Session) -> ReceiptItem:
    row = await payment_service.get_receipt(session, context.company.id, receipt_id)
    if row is None or not context.can_access_branch(row.branch_id):
        raise _not_found()
    return ReceiptItem.model_validate(row)


@router.post("/receipts/{receipt_id}/applications", response_model=ReceiptItem)
async def apply_receipt(receipt_id: UUID, payload: ApplyInput, context: Apply, session: Session) -> ReceiptItem:
    _branch(context, payload.branch_id)
    try:
        return ReceiptItem.model_validate(await payment_service.apply(session, ApplyReceipt(company_id=context.company.id, receipt_id=receipt_id, actor_user_id=context.user.id, **payload.model_dump())))
    except PaymentError as exc:
        raise _error(exc) from exc


@router.post("/receipts/{receipt_id}/refunds", response_model=RefundItem)
async def refund_receipt(receipt_id: UUID, payload: RefundInput, context: RefundPermission, session: Session) -> RefundItem:
    _branch(context, payload.branch_id)
    try:
        return RefundItem.model_validate(await payment_service.request_refund(session, RequestRefund(company_id=context.company.id, receipt_id=receipt_id, actor_user_id=context.user.id, **payload.model_dump())))
    except PaymentError as exc:
        raise _error(exc) from exc
