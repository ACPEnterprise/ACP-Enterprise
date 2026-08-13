from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CreateFromEstimate:
    company_id: UUID
    branch_id: UUID
    estimate_id: UUID
    job_id: UUID
    due_date: date
    terms: str
    actor_user_id: UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class InvoiceMutation:
    company_id: UUID
    branch_id: UUID
    invoice_id: UUID
    expected_version: int
    actor_user_id: UUID
    idempotency_key: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class AmountMutation(InvoiceMutation):
    amount: Decimal
    reason_code: str


@dataclass(frozen=True, slots=True)
class PaymentReceiptFact:
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    receipt_id: UUID
    currency: str
    verified_amount: Decimal
    occurred_at: datetime
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class PaymentApplication(InvoiceMutation):
    receipt_id: UUID
    amount: Decimal


@dataclass(frozen=True, slots=True)
class PostingReceiptFact:
    company_id: UUID
    branch_id: UUID
    invoice_id: UUID
    source_event_id: UUID
    journal_id: UUID
    journal_version: int
    policy_version: str
    status: str
    effective_date: date
    posted_at: datetime
