import math
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer
from app.database.session import get_database_session
from app.financials.models import (
    Estimate,
    EstimateLineItem,
    Invoice,
    InvoiceLineItem,
    Payment,
)
from app.financials.schemas import (
    FinancialDetail,
    FinancialLineItemResponse,
    FinancialListItem,
    PaginatedFinancials,
    PaginatedPayments,
    PaymentResponse,
)
from app.jobs.models import Job
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import JobPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/financials", tags=["Financials"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
FinancialReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(JobPermission.READ))
]


def _scope(context: AuthorizationContext, branch_id: UUID | None) -> tuple[UUID, ...]:
    branches = tuple(item.id for item in context.authorized_branches)
    if branch_id is not None:
        if not context.can_access_branch(branch_id):
            raise HTTPException(
                status_code=404, detail="Financial resource was not found."
            )
        return (branch_id,)
    return branches


async def _documents(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    model: type[Estimate] | type[Invoice],
    number_column: object,
    branch_id: UUID | None,
    search_text: str | None,
    page: int,
    page_size: int,
) -> PaginatedFinancials:
    branches = _scope(context, branch_id)
    statement = (
        select(model, Job.job_number, Customer.display_name)
        .join(Job, Job.id == model.job_id)
        .join(Customer, Customer.id == model.customer_id)
        .where(model.company_id == context.company.id, model.branch_id.in_(branches))
    )
    if search_text and search_text.strip():
        pattern = f"%{search_text.strip()}%"
        statement = statement.where(
            or_(
                number_column.ilike(pattern),
                Job.job_number.ilike(pattern),
                Customer.display_name.ilike(pattern),
                model.status.cast(String).ilike(pattern),
            )
        )
    total = int(
        await session.scalar(select(func.count()).select_from(statement.subquery()))
        or 0
    )
    rows = (
        await session.execute(
            statement.order_by(model.created_at.desc(), model.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return PaginatedFinancials(
        items=tuple(
            FinancialListItem(
                id=document.id,
                number=getattr(document, "estimate_number", None)
                or document.invoice_number,
                status=document.status,
                job_id=document.job_id,
                job_number=job_number,
                customer_id=document.customer_id,
                customer_display_name=customer_name,
                currency=document.currency,
                total_amount=document.total_amount,
                created_at=document.created_at,
            )
            for document, job_number, customer_name in rows
        ),
        page=page,
        page_size=page_size,
        total_count=total,
        total_pages=math.ceil(total / page_size),
    )


@router.get("/estimates", response_model=PaginatedFinancials)
async def list_estimates(
    context: FinancialReadContext,
    session: DatabaseSession,
    branch_id: UUID | None = None,
    search_text: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginatedFinancials:
    return await _documents(
        session,
        context=context,
        model=Estimate,
        number_column=Estimate.estimate_number,
        branch_id=branch_id,
        search_text=search_text,
        page=page,
        page_size=page_size,
    )


@router.get("/invoices", response_model=PaginatedFinancials)
async def list_invoices(
    context: FinancialReadContext,
    session: DatabaseSession,
    branch_id: UUID | None = None,
    search_text: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginatedFinancials:
    return await _documents(
        session,
        context=context,
        model=Invoice,
        number_column=Invoice.invoice_number,
        branch_id=branch_id,
        search_text=search_text,
        page=page,
        page_size=page_size,
    )


async def _detail(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    identifier: UUID,
    model: type[Estimate] | type[Invoice],
    line_model: type[EstimateLineItem] | type[InvoiceLineItem],
) -> FinancialDetail:
    row = (
        await session.execute(
            select(model, Job.job_number, Customer.display_name)
            .join(Job, Job.id == model.job_id)
            .join(Customer, Customer.id == model.customer_id)
            .where(
                model.id == identifier,
                model.company_id == context.company.id,
                model.branch_id.in_(_scope(context, None)),
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Financial resource was not found.")
    document, job_number, customer_name = row
    parent_column = (
        line_model.estimate_id
        if line_model is EstimateLineItem
        else line_model.invoice_id
    )
    lines = (
        await session.scalars(
            select(line_model)
            .where(
                parent_column == identifier, line_model.company_id == context.company.id
            )
            .order_by(line_model.position)
        )
    ).all()
    payments = ()
    if model is Invoice:
        payments = tuple(
            PaymentResponse.model_validate(item)
            for item in (
                await session.scalars(
                    select(Payment)
                    .where(
                        Payment.invoice_id == identifier,
                        Payment.company_id == context.company.id,
                    )
                    .order_by(Payment.paid_at, Payment.id)
                )
            ).all()
        )
    return FinancialDetail(
        id=document.id,
        number=getattr(document, "estimate_number", None) or document.invoice_number,
        status=document.status,
        job_id=document.job_id,
        job_number=job_number,
        customer_id=document.customer_id,
        customer_display_name=customer_name,
        branch_id=document.branch_id,
        service_location_id=document.service_location_id,
        currency=document.currency,
        subtotal_amount=document.subtotal_amount,
        tax_amount=document.tax_amount,
        total_amount=document.total_amount,
        created_at=document.created_at,
        issued_at=getattr(document, "issued_at", None),
        due_on=getattr(document, "due_on", None),
        presented_at=getattr(document, "presented_at", None),
        expires_on=getattr(document, "expires_on", None),
        line_items=tuple(
            FinancialLineItemResponse.model_validate(item) for item in lines
        ),
        payments=payments,
    )


@router.get("/estimates/{estimate_id}", response_model=FinancialDetail)
async def get_estimate(
    estimate_id: UUID, context: FinancialReadContext, session: DatabaseSession
) -> FinancialDetail:
    return await _detail(
        session,
        context=context,
        identifier=estimate_id,
        model=Estimate,
        line_model=EstimateLineItem,
    )


@router.get("/invoices/{invoice_id}", response_model=FinancialDetail)
async def get_invoice(
    invoice_id: UUID, context: FinancialReadContext, session: DatabaseSession
) -> FinancialDetail:
    return await _detail(
        session,
        context=context,
        identifier=invoice_id,
        model=Invoice,
        line_model=InvoiceLineItem,
    )


@router.get("/payments", response_model=PaginatedPayments)
async def list_payments(
    context: FinancialReadContext,
    session: DatabaseSession,
    branch_id: UUID | None = None,
    search_text: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginatedPayments:
    statement = select(Payment).where(
        Payment.company_id == context.company.id,
        Payment.branch_id.in_(_scope(context, branch_id)),
    )
    if search_text and search_text.strip():
        pattern = f"%{search_text.strip()}%"
        statement = statement.where(
            or_(Payment.method.ilike(pattern), Payment.reference.ilike(pattern))
        )
    total = int(
        await session.scalar(select(func.count()).select_from(statement.subquery()))
        or 0
    )
    values = (
        await session.scalars(
            statement.order_by(Payment.paid_at.desc(), Payment.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return PaginatedPayments(
        items=tuple(PaymentResponse.model_validate(item) for item in values),
        page=page,
        page_size=page_size,
        total_count=total,
        total_pages=math.ceil(total / page_size),
    )


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID, context: FinancialReadContext, session: DatabaseSession
) -> PaymentResponse:
    payment = await session.scalar(
        select(Payment).where(
            Payment.id == payment_id,
            Payment.company_id == context.company.id,
            Payment.branch_id.in_(_scope(context, None)),
        )
    )
    if payment is None:
        raise HTTPException(status_code=404, detail="Financial resource was not found.")
    return PaymentResponse.model_validate(payment)
