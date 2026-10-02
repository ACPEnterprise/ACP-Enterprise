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


class BankReconciliationClose(BaseModel):
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
    preparer_user_id: UUID


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
    evidence_digest: str
    preparer_user_id: UUID
    reviewer_user_id: UUID | None
    closed_at: datetime | None
