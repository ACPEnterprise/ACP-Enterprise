from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class APSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class VendorCreate(APSchema):
    code: str = Field(min_length=1, max_length=80)
    legal_name: str = Field(min_length=1, max_length=240)
    display_name: str = Field(min_length=1, max_length=240)
    provenance: str = Field(min_length=1, max_length=40)
    default_terms: str | None = Field(default=None, max_length=120)


class VendorItem(APSchema):
    id: UUID
    company_id: UUID
    code: str
    legal_name: str
    display_name: str
    status: str
    default_terms: str | None
    provenance: str
    version: int
    created_at: datetime


class VendorMapInput(APSchema):
    source_system: str
    source_company_id: str
    source_vendor_id: str
    source_digest: str = Field(min_length=64, max_length=64)


class AccountMappingInput(APSchema):
    mapping_key: str
    classification: str
    account_id: UUID
    effective_from: date
    effective_to: date | None = None
    policy_version: str


class BillLineInput(APSchema):
    description: str
    quantity: Decimal
    unit: str | None = None
    net_amount: Decimal
    tax_amount: Decimal = Decimal(0)
    mapping_id: UUID
    branch_id: UUID
    purchasing_reference: str | None = None
    receipt_reference: str | None = None


class BillCreate(APSchema):
    branch_id: UUID
    vendor_id: UUID
    vendor_document_number: str
    bill_date: date
    received_date: date
    due_date: date
    terms_snapshot: str
    currency: str = Field(min_length=3, max_length=3)
    source_system: str
    source_identity: str
    source_digest: str = Field(min_length=64, max_length=64)
    evidence_reference: str
    idempotency_key: str
    replacement_for_bill_id: UUID | None = None
    lines: list[BillLineInput] = Field(min_length=1)


class BillItem(APSchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    vendor_id: UUID
    bill_number: str
    vendor_document_number: str
    bill_date: date
    due_date: date
    currency: str
    status: str
    accounting_status: str
    total_amount: Decimal
    open_amount: Decimal
    version: int


class TransitionInput(APSchema):
    expected_version: int = Field(ge=1)


class DuplicateOverrideInput(APSchema):
    duplicate_bill_id: UUID
    requester_user_id: UUID
    reason: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)


class CreditCreate(APSchema):
    vendor_id: UUID
    credit_number: str
    credit_date: date
    currency: str = Field(min_length=3, max_length=3)
    amount: Decimal
    reason: str
    mapping_id: UUID
    source_system: str
    source_identity: str
    source_digest: str = Field(min_length=64, max_length=64)


class CreditApplyInput(APSchema):
    bill_id: UUID
    amount: Decimal
    idempotency_key: str


class UnapplyInput(APSchema):
    idempotency_key: str


class DisbursementCreate(APSchema):
    branch_id: UUID
    vendor_id: UUID
    approver_user_id: UUID
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    effective_date: date
    method_category: str
    external_reference: str
    source_system: str
    source_identity: str
    evidence_digest: str = Field(min_length=64, max_length=64)


class DisbursementApplyInput(APSchema):
    bill_id: UUID
    amount: Decimal
    idempotency_key: str


class ReverseInput(APSchema):
    effective_date: date
    reason: str


class AgingItem(APSchema):
    vendor_id: UUID
    bill_id: UUID
    bill_number: str
    bill_date: date
    due_date: date
    original_amount: Decimal
    open_amount: Decimal
    currency: str
    days_past_due: int
    status: str
