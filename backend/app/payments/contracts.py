from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

ProviderOutcome = Literal["authorized", "captured", "declined", "failed", "ambiguous"]


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    operation_id: UUID
    provider_idempotency_key: str
    merchant_account: str
    amount: Decimal
    currency: str
    opaque_payment_method: str


@dataclass(frozen=True, slots=True)
class ProviderResult:
    outcome: ProviderOutcome
    provider_operation_id: str | None
    provider_code: str | None
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class VerifiedWebhook:
    provider_event_id: str
    merchant_account: str
    event_type: str
    occurred_at: datetime
    allowed_evidence: dict[str, str]
    evidence_digest: str
    secret_version: str


class PaymentProvider(Protocol):
    name: str

    async def collect(self, request: ProviderRequest) -> ProviderResult: ...
    async def refund(self, request: ProviderRequest) -> ProviderResult: ...
    async def lookup(self, provider_operation_id: str) -> ProviderResult: ...


class WebhookVerifier(Protocol):
    def verify(
        self,
        *,
        raw_body: bytes,
        signature: str,
        timestamp: str,
        merchant_account: str,
    ) -> VerifiedWebhook: ...


@dataclass(frozen=True, slots=True)
class CreateIntent:
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    amount: Decimal
    currency: str
    opaque_payment_method: str
    idempotency_key: str
    actor_user_id: UUID
    invoice_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ApplyReceipt:
    company_id: UUID
    branch_id: UUID
    receipt_id: UUID
    invoice_id: UUID
    amount: Decimal
    expected_invoice_version: int
    idempotency_key: str
    actor_user_id: UUID
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class RequestRefund:
    company_id: UUID
    branch_id: UUID
    receipt_id: UUID
    amount: Decimal
    reason: str
    idempotency_key: str
    actor_user_id: UUID
    expected_version: int


@dataclass(frozen=True, slots=True)
class PostingReceiptFact:
    company_id: UUID
    source_event_id: UUID
    journal_id: UUID
    journal_version: int
    policy_version: str
    status: str
    effective_date: date
    posted_at: datetime


@dataclass(frozen=True, slots=True)
class CreateDeposit:
    company_id: UUID
    branch_id: UUID
    receipt_ids: tuple[UUID, ...]
    currency: str
    destination_reference: str
    idempotency_key: str
    actor_user_id: UUID


@dataclass(frozen=True, slots=True)
class RecordSettlement:
    company_id: UUID
    provider: str
    merchant_account: str
    provider_payout_id: str
    currency: str
    settlement_date: date
    gross_amount: Decimal
    refund_amount: Decimal
    dispute_amount: Decimal
    fee_amount: Decimal
    adjustment_amount: Decimal
    net_amount: Decimal
    evidence_digest: str
    actor_user_id: UUID


@dataclass(frozen=True, slots=True)
class RecordDispute:
    company_id: UUID
    branch_id: UUID
    receipt_id: UUID
    amount: Decimal
    provider_dispute_id: str
    evidence_digest: str
    idempotency_key: str
    actor_user_id: UUID
    expected_version: int
