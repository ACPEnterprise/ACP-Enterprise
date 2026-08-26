from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class VendorSpec:
    company_id: UUID
    actor_user_id: UUID
    code: str
    legal_name: str
    display_name: str
    provenance: str
    default_terms: str | None = None


@dataclass(frozen=True)
class BillLineSpec:
    description: str
    quantity: Decimal
    net_amount: Decimal
    tax_amount: Decimal
    mapping_id: UUID
    branch_id: UUID
    unit: str | None = None
    purchasing_reference: str | None = None
    receipt_reference: str | None = None


@dataclass(frozen=True)
class BillSpec:
    company_id: UUID
    branch_id: UUID
    actor_user_id: UUID
    vendor_id: UUID
    vendor_document_number: str
    bill_date: date
    received_date: date
    due_date: date
    terms_snapshot: str
    currency: str
    source_system: str
    source_identity: str
    source_digest: str
    evidence_reference: str
    idempotency_key: str
    lines: tuple[BillLineSpec, ...]
    replacement_for_bill_id: UUID | None = None


@dataclass(frozen=True)
class CreditSpec:
    company_id: UUID
    actor_user_id: UUID
    vendor_id: UUID
    credit_number: str
    credit_date: date
    currency: str
    amount: Decimal
    reason: str
    mapping_id: UUID
    source_system: str
    source_identity: str
    source_digest: str


@dataclass(frozen=True)
class DisbursementSpec:
    company_id: UUID
    branch_id: UUID
    recorder_user_id: UUID
    approver_user_id: UUID
    vendor_id: UUID
    amount: Decimal
    currency: str
    effective_date: date
    method_category: str
    external_reference: str
    source_system: str
    source_identity: str
    evidence_digest: str


@dataclass(frozen=True)
class PostingReceiptSpec:
    company_id: UUID
    source_event_id: UUID
    source_type: str
    source_id: UUID
    journal_id: UUID | None
    journal_version: int | None
    mapping_version: str
    status: str
    effective_date: date
    failure_reason: str | None = None
