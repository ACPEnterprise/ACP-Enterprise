from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InvoiceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CreateInvoiceInput(InvoiceSchema):
    branch_id: UUID
    estimate_id: UUID
    job_id: UUID
    due_date: date
    terms: str = Field(min_length=1, max_length=8000)
    idempotency_key: str = Field(min_length=1, max_length=160)


class MutationInput(InvoiceSchema):
    branch_id: UUID
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=160)
    occurred_at: datetime


class AmountInput(MutationInput):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    reason_code: str = Field(min_length=1, max_length=80)


class PaymentApplicationInput(MutationInput):
    receipt_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class InvoiceItem(InvoiceSchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    job_id: UUID
    estimate_id: UUID | None
    estimate_revision_id: UUID | None
    invoice_number: str
    status: str
    accounting_status: str
    currency: str
    issue_date: date
    due_date: date
    terms: str
    subtotal_amount: Decimal
    discount_amount: Decimal
    taxable_basis: Decimal | None
    tax_amount: Decimal
    total_amount: Decimal
    open_amount: Decimal
    calculation_digest: str
    legacy_evidence_missing: bool
    version: int
    issued_at: datetime | None
    created_at: datetime
    updated_at: datetime
