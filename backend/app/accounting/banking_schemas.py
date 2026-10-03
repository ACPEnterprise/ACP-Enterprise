from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BankAccountCreate(BaseModel):
    ledger_account_id: UUID
    institution_name: str = Field(min_length=1, max_length=160)
    account_name: str = Field(min_length=1, max_length=160)
    account_type: str
    masked_identity: str = Field(min_length=1, max_length=40)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    source_system: str = Field(min_length=1, max_length=40)
    source_account_id: str = Field(min_length=1, max_length=180)
    source_version: str = Field(min_length=1, max_length=80)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_as_of: datetime
    opening_balance: Decimal | None = None
    opening_balance_date: date | None = None
    opening_balance_provenance: dict[str, object] = Field(default_factory=dict)


class BankAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    company_id: UUID
    ledger_account_id: UUID
    institution_name: str
    account_name: str
    account_type: str
    masked_identity: str
    currency: str
    status: str
    source_system: str
    source_account_id: str
    source_version: str
    source_digest: str
    source_as_of: datetime
    opening_balance: Decimal | None
    opening_balance_date: date | None


class BankTransactionIngest(BaseModel):
    source_system: str = Field(min_length=1, max_length=40)
    external_transaction_id: str = Field(min_length=1, max_length=240)
    related_identity: str | None = Field(default=None, max_length=240)
    group_key: str | None = Field(default=None, max_length=240)
    source_version: str = Field(min_length=1, max_length=80)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    acquired_at: datetime
    source_as_of: datetime
    posted_date: date
    effective_date: date | None = None
    amount: Decimal = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    direction: str
    kind: str
    description: str
    memo: str | None = None
    state: str = "posted"


class BankTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    company_id: UUID
    bank_account_id: UUID
    external_transaction_id: str
    related_identity: str | None
    group_key: str | None
    source_version: str
    source_digest: str
    acquired_at: datetime
    source_as_of: datetime
    posted_date: date
    effective_date: date | None
    amount: Decimal
    currency: str
    direction: str
    kind: str
    description: str
    memo: str | None
    state: str


class BankTransactionMatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    bank_transaction_id: UUID
    state: str
    target_type: str | None
    target_identity: str | None
    deterministic: bool
    reason_code: str
    evidence_digest: str


class BankReconciliationPrepare(BaseModel):
    statement_identity: str = Field(min_length=1, max_length=240)
    period_start: date
    period_end: date
    ending_balance: Decimal
    book_balance: Decimal
    cleared_total: Decimal
    outstanding_total: Decimal
    cleared_transaction_ids: tuple[UUID, ...]
    outstanding_items: list[dict[str, object]] = Field(default_factory=list)
    source_evidence: dict[str, object]


class BankReconciliationTransition(BaseModel):
    expected_version: int = Field(ge=1)


class ReconciliationActor(BaseModel):
    display_name: str
    occurred_at: datetime


class BankReconciliationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    company_id: UUID
    bank_account_id: UUID
    statement_identity: str
    period_start: date
    period_end: date
    ending_balance: Decimal
    book_balance: Decimal
    cleared_total: Decimal
    outstanding_total: Decimal
    difference: Decimal
    status: str
    cleared_transaction_ids: list[str]
    outstanding_items: list[dict[str, object]]
    source_evidence: dict[str, object]
    evidence_digest: str
    preparer_user_id: UUID
    preparer_membership_id: UUID | None
    reviewer_user_id: UUID | None
    prepared_at: datetime
    submitted_at: datetime | None
    closed_at: datetime | None
    version: int
    prepared_by: ReconciliationActor
    reviewed_by: ReconciliationActor | None


class BankAccountSummary(BaseModel):
    account: BankAccountResponse
    imported_count: int
    matched_count: int
    unmatched_count: int
    review_required_count: int
    transfer_candidate_count: int
    active_reconciliation_state: str
    current_difference: Decimal | None
    last_reconciled_through: date | None
    latest_closed_reconciliation: BankReconciliationResponse | None


class BankImportPreviewRequest(BaseModel):
    statement_identity: str = Field(min_length=1, max_length=240)
    period_start: date
    period_end: date
    opening_balance: Decimal | None = None
    ending_balance: Decimal | None = None
    transactions: tuple[BankTransactionIngest, ...]


class BankImportDisposition(BaseModel):
    source_system: str
    source_identity: str
    disposition: str
    reason: str


class BankImportPreviewResponse(BaseModel):
    bank_account_id: UUID
    statement_identity: str
    period_start: date
    period_end: date
    opening_balance: Decimal | None
    ending_balance: Decimal | None
    transaction_count: int
    new_count: int
    replay_count: int
    duplicate_count: int
    conflict_count: int
    invalid_count: int
    preview_digest: str
    dispositions: tuple[BankImportDisposition, ...]


class BankImportConfirmRequest(BankImportPreviewRequest):
    preview_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class BankImportConfirmResponse(BaseModel):
    preview_digest: str
    persisted_count: int
    replay_count: int
    quarantined_count: int
    dispositions: tuple[BankImportDisposition, ...]


class BankMatchReviewItem(BaseModel):
    transaction: BankTransactionResponse
    match_id: UUID | None
    match_state: str
    target_type: str | None
    target_identity: str | None
    reason_code: str
    deterministic: bool


class BankReconciliationPreviewRequest(BaseModel):
    statement_identity: str = Field(min_length=1, max_length=240)
    period_start: date
    period_end: date
    ending_balance: Decimal
    cleared_transaction_ids: tuple[UUID, ...]


class BankReconciliationPreviewResponse(BaseModel):
    bank_account_id: UUID
    statement_identity: str
    period_start: date
    period_end: date
    beginning_balance: Decimal
    ending_balance: Decimal
    book_balance: Decimal
    cleared_total: Decimal
    outstanding_total: Decimal
    difference: Decimal
    unresolved_exceptions: int
    can_close: bool
    blocker_reasons: tuple[str, ...]


class BankDrilldownResponse(BaseModel):
    transaction: BankTransactionResponse
    match: BankMatchReviewItem
    bank_account_id: UUID
    ledger_account_id: UUID
    target_reference: str | None
    source_system: str
    source_digest: str


class CashFlowSection(BaseModel):
    amount: Decimal
    journal_ids: tuple[UUID, ...]


class CashFlowResponse(BaseModel):
    period_start: date
    period_end: date
    basis: str
    cutoff: date
    completeness: str
    beginning_cash: Decimal
    operating_activities: CashFlowSection
    investing_activities: CashFlowSection
    financing_activities: CashFlowSection
    unclassified_amount: Decimal
    unclassified_journal_ids: tuple[UUID, ...]
    net_change: Decimal
    ending_cash: Decimal
    canonical_bank_cash: Decimal | None
    difference: Decimal | None
    tie_status: str
