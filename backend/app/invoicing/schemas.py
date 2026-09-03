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


class InvoiceWorkspaceItem(InvoiceSchema):
    id: UUID
    branch_id: UUID
    customer_id: UUID
    customer_number: str
    customer_display_name: str
    service_location_id: UUID
    service_location_label: str
    job_id: UUID
    job_number: str
    estimate_id: UUID | None
    invoice_number: str
    status: str
    accounting_status: str
    currency: str
    issue_date: date
    due_date: date
    terms: str
    total_amount: Decimal
    open_amount: Decimal
    age_days: int
    aging_bucket: str
    attention_reasons: tuple[str, ...]
    last_ar_activity_type: str | None
    last_ar_activity_at: datetime | None
    legacy_evidence_missing: bool
    version: int


class CustomerBalanceItem(InvoiceSchema):
    customer_id: UUID
    customer_number: str
    customer_display_name: str
    currency: str
    invoice_total: Decimal
    open_balance: Decimal
    credit_total: Decimal
    write_off_total: Decimal
    applied_payment_total: Decimal
    unapplied_receipt_total: Decimal
    disputed_receipt_total: Decimal
    native_invoice_count: int
    legacy_evidence_incomplete: bool
    as_of: date
