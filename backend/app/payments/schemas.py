from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CollectInput(BaseModel):
    branch_id: UUID
    customer_id: UUID
    invoice_id: UUID | None = None
    amount: Decimal = Field(gt=0, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    opaque_payment_method: str = Field(
        pattern=r"^opaque_[A-Za-z0-9_.:-]+$", max_length=255
    )
    idempotency_key: str = Field(min_length=8, max_length=120)


class ApplyInput(BaseModel):
    branch_id: UUID
    invoice_id: UUID
    amount: Decimal = Field(gt=0, decimal_places=2)
    expected_invoice_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=120)
    occurred_at: datetime


class RefundInput(BaseModel):
    branch_id: UUID
    amount: Decimal = Field(gt=0, decimal_places=2)
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=120)


class IntentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    branch_id: UUID
    customer_id: UUID
    invoice_id: UUID | None
    amount: Decimal
    currency: str
    status: str
    version: int


class ReceiptItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    branch_id: UUID
    customer_id: UUID
    intent_id: UUID
    currency: str
    status: str
    captured_amount: Decimal
    available_amount: Decimal
    applied_amount: Decimal
    refunded_amount: Decimal
    disputed_amount: Decimal
    version: int
    captured_at: datetime


class RefundItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    receipt_id: UUID
    amount: Decimal
    currency: str
    status: str
    reason: str


EvidenceState = Literal[
    "AVAILABLE", "MEASURED_ZERO", "INCOMPLETE", "CONFLICTING", "UNAVAILABLE"
]


class MoneyAmountItem(BaseModel):
    amount: Decimal | None
    currency: str | None
    evidence_state: EvidenceState
    limitation: str | None = None


class BankAccountItem(BaseModel):
    account_id: str
    display_name: str
    account_type: str
    current_balance: Decimal | None
    available_balance: Decimal | None
    currency: str | None
    provider: str
    provider_as_of: datetime
    last_sync_at: datetime
    stale: bool
    reconciliation_state: str | None


class BankBalanceItem(MoneyAmountItem):
    connection_state: Literal["NOT_CONNECTED", "CONNECTED"]
    provider_as_of: datetime | None
    last_sync_at: datetime | None
    accounts: tuple[BankAccountItem, ...]


class DueInvoiceItem(BaseModel):
    invoice_id: UUID
    invoice_number: str
    branch_id: UUID
    customer_id: UUID
    invoice_date: date
    due_date: date
    terms: str
    open_balance: Decimal
    currency: str


class DueTodayItem(MoneyAmountItem):
    invoice_count: int
    items: tuple[DueInvoiceItem, ...]
    drilldown_path: str


class CodExpectedWorkItem(BaseModel):
    job_id: UUID
    job_number: str
    appointment_id: UUID
    appointment_number: str
    branch_id: UUID
    customer_id: UUID
    scheduled_at: datetime
    expected_amount: Decimal | None
    currency: str | None
    evidence_basis: Literal["ACCEPTED_ESTIMATE_REVISION", "UNAVAILABLE"]
    estimate_revision_id: UUID | None
    payment_term_code: (
        Literal["COD", "DUE_ON_COMPLETION", "DUE_ON_RECEIPT", "NET"] | None
    )
    payment_term_net_days: int | None
    payment_term_policy_id: UUID | None
    payment_term_version: int | None
    payment_term_source: str | None
    payment_term_evidence_digest: str | None
    state: Literal["QUALIFYING", "NOT_DUE_TODAY", "INCOMPLETE"]
    limitation: str | None


class CodExpectedItem(MoneyAmountItem):
    items: tuple[CodExpectedWorkItem, ...]


class CardTransactionItem(BaseModel):
    receipt_id: UUID
    intent_id: UUID
    branch_id: UUID
    customer_id: UUID
    invoice_id: UUID | None
    provider: str
    provider_operation_id: str | None
    charged_amount: Decimal
    refunded_amount: Decimal
    chargeback_amount: Decimal
    currency: str
    collected_at: datetime
    settlement_state: Literal["NOT_LINKED"]
    deposit_state: Literal["NOT_PROVEN"]
    evidence_digest: str


class FeeEvidenceItem(BaseModel):
    settlement_id: UUID
    provider: str
    provider_payout_id: str
    settlement_date: date
    gross_amount: Decimal
    fee_amount: Decimal
    net_amount: Decimal
    currency: str
    reconciliation_state: str
    evidence_digest: str


class CardProcessingItem(BaseModel):
    transaction_count: int
    amount_charged: MoneyAmountItem
    refund_amount: MoneyAmountItem
    chargeback_amount: MoneyAmountItem
    fees_paid: MoneyAmountItem
    effective_fee_rate: Decimal | None
    transactions: tuple[CardTransactionItem, ...]
    fee_evidence: tuple[FeeEvidenceItem, ...]
    limitation: str


class CollectionEvidenceItem(BaseModel):
    source_type: Literal["PROVIDER_RECEIPT", "MANUAL_PAYMENT_EVIDENCE"]
    source_id: UUID
    branch_id: UUID
    customer_id: UUID
    invoice_id: UUID | None
    amount: Decimal
    currency: str
    occurred_at: datetime
    settlement_state: Literal["NOT_LINKED", "NOT_ASSERTED"]
    evidence_digest: str


class CollectionStateItem(BaseModel):
    collected: MoneyAmountItem
    collection_evidence: tuple[CollectionEvidenceItem, ...]
    settled_gross: MoneyAmountItem
    settled_net: MoneyAmountItem
    deposited: MoneyAmountItem


class MoneyPositionItem(BaseModel):
    company_id: UUID
    branch_id: UUID | None
    period_start: date
    period_end: date
    as_of: date
    generated_at: datetime
    bank_balance: BankBalanceItem
    accounts_receivable_due_today: DueTodayItem
    cod_expected_today: CodExpectedItem
    expected_collections_today: MoneyAmountItem
    card_processing: CardProcessingItem
    collection_state: CollectionStateItem
