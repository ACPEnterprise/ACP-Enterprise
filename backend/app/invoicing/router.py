from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.invoicing.contracts import (
    AmountMutation,
    CreateFromEstimate,
    InvoiceMutation,
    PaymentApplication,
)
from app.invoicing.errors import InvoiceConflict, InvoiceError, InvoiceNotFound
from app.invoicing.schemas import (
    AmountInput,
    CreateInvoiceInput,
    InvoiceItem,
    MutationInput,
    PaymentApplicationInput,
)
from app.invoicing.service import invoice_service
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import InvoicePermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/invoices", tags=["Invoices"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Read = Annotated[
    AuthorizationContext, Depends(require_permission(InvoicePermission.READ))
]
Manage = Annotated[
    AuthorizationContext, Depends(require_permission(InvoicePermission.MANAGE))
]
Issue = Annotated[
    AuthorizationContext, Depends(require_permission(InvoicePermission.ISSUE))
]
Adjust = Annotated[
    AuthorizationContext, Depends(require_permission(InvoicePermission.ADJUST))
]
Apply = Annotated[
    AuthorizationContext, Depends(require_permission(InvoicePermission.APPLY_PAYMENT))
]


def _error(error: InvoiceError) -> HTTPException:
    if isinstance(error, InvoiceNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, InvoiceConflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


def _branch(context: AuthorizationContext, branch_id: UUID) -> None:
    if not context.can_access_branch(branch_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice was not found.")


@router.get("", response_model=list[InvoiceItem])
async def list_invoices(context: Read, session: Session) -> list[InvoiceItem]:
    rows = await invoice_service.list(
        session, context.company.id, context.authorized_branch_ids
    )
    return [InvoiceItem.model_validate(row) for row in rows]


@router.get("/{invoice_id}", response_model=InvoiceItem)
async def get_invoice(invoice_id: UUID, context: Read, session: Session) -> InvoiceItem:
    row = await invoice_service.get(session, context.company.id, invoice_id)
    if row is None or not context.can_access_branch(row.branch_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice was not found.")
    return InvoiceItem.model_validate(row)


@router.post("", response_model=InvoiceItem, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    payload: CreateInvoiceInput, context: Manage, session: Session
) -> InvoiceItem:
    _branch(context, payload.branch_id)
    try:
        row = await invoice_service.create_from_estimate(
            session,
            CreateFromEstimate(
                company_id=context.company.id,
                actor_user_id=context.user.id,
                **payload.model_dump(),
            ),
        )
        return InvoiceItem.model_validate(row)
    except InvoiceError as error:
        raise _error(error) from error


def _mutation(
    context: AuthorizationContext, invoice_id: UUID, payload: MutationInput
) -> InvoiceMutation:
    _branch(context, payload.branch_id)
    return InvoiceMutation(
        company_id=context.company.id,
        invoice_id=invoice_id,
        actor_user_id=context.user.id,
        **payload.model_dump(),
    )


@router.post("/{invoice_id}/issue", response_model=InvoiceItem)
async def issue_invoice(
    invoice_id: UUID, payload: MutationInput, context: Issue, session: Session
) -> InvoiceItem:
    try:
        return InvoiceItem.model_validate(
            await invoice_service.issue(
                session, _mutation(context, invoice_id, payload)
            )
        )
    except InvoiceError as error:
        raise _error(error) from error


async def _amount(action, invoice_id, payload, context, session):
    _branch(context, payload.branch_id)
    spec = AmountMutation(
        company_id=context.company.id,
        invoice_id=invoice_id,
        actor_user_id=context.user.id,
        **payload.model_dump(),
    )
    try:
        return InvoiceItem.model_validate(await action(session, spec))
    except InvoiceError as error:
        raise _error(error) from error


@router.post("/{invoice_id}/credits", response_model=InvoiceItem)
async def credit_invoice(
    invoice_id: UUID, payload: AmountInput, context: Adjust, session: Session
) -> InvoiceItem:
    return await _amount(invoice_service.credit, invoice_id, payload, context, session)


@router.post("/{invoice_id}/write-offs", response_model=InvoiceItem)
async def write_off_invoice(
    invoice_id: UUID, payload: AmountInput, context: Adjust, session: Session
) -> InvoiceItem:
    return await _amount(
        invoice_service.write_off, invoice_id, payload, context, session
    )


@router.post("/{invoice_id}/void", response_model=InvoiceItem)
async def void_invoice(
    invoice_id: UUID, payload: MutationInput, context: Adjust, session: Session
) -> InvoiceItem:
    try:
        return InvoiceItem.model_validate(
            await invoice_service.void(session, _mutation(context, invoice_id, payload))
        )
    except InvoiceError as error:
        raise _error(error) from error


@router.post("/{invoice_id}/payment-applications", response_model=InvoiceItem)
async def apply_payment(
    invoice_id: UUID, payload: PaymentApplicationInput, context: Apply, session: Session
) -> InvoiceItem:
    _branch(context, payload.branch_id)
    spec = PaymentApplication(
        company_id=context.company.id,
        invoice_id=invoice_id,
        actor_user_id=context.user.id,
        **payload.model_dump(),
    )
    try:
        return InvoiceItem.model_validate(
            await invoice_service.apply_payment(session, spec)
        )
    except InvoiceError as error:
        raise _error(error) from error


@router.post("/{invoice_id}/payment-applications/reverse", response_model=InvoiceItem)
async def reverse_payment_application(
    invoice_id: UUID,
    payload: PaymentApplicationInput,
    context: Apply,
    session: Session,
) -> InvoiceItem:
    _branch(context, payload.branch_id)
    spec = PaymentApplication(
        company_id=context.company.id,
        invoice_id=invoice_id,
        actor_user_id=context.user.id,
        **payload.model_dump(),
    )
    try:
        return InvoiceItem.model_validate(
            await invoice_service.reverse_payment_application(session, spec)
        )
    except InvoiceError as error:
        raise _error(error) from error
