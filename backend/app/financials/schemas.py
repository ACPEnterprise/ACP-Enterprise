from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FinancialSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class FinancialListItem(FinancialSchema):
    id: UUID
    number: str
    status: str
    job_id: UUID
    job_number: str
    customer_id: UUID
    customer_display_name: str
    currency: str
    total_amount: Decimal
    created_at: datetime


class PaginatedFinancials(FinancialSchema):
    items: tuple[FinancialListItem, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    total_count: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class FinancialLineItemResponse(FinancialSchema):
    id: UUID
    position: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    total_amount: Decimal


class PaymentResponse(FinancialSchema):
    id: UUID
    invoice_id: UUID
    customer_id: UUID
    amount: Decimal
    currency: str
    status: str
    paid_at: datetime | None
    method: str | None
    reference: str | None
    created_at: datetime


class FinancialDetail(FinancialListItem):
    branch_id: UUID
    service_location_id: UUID
    subtotal_amount: Decimal
    tax_amount: Decimal
    issued_at: datetime | None = None
    due_on: date | None = None
    presented_at: datetime | None = None
    expires_on: date | None = None
    line_items: tuple[FinancialLineItemResponse, ...]
    payments: tuple[PaymentResponse, ...] = ()


class PaginatedPayments(FinancialSchema):
    items: tuple[PaymentResponse, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    total_count: int = Field(ge=0)
    total_pages: int = Field(ge=0)
