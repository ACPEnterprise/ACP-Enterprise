from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountingSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class ChartCreate(AccountingSchema):
    name: str = Field(min_length=1, max_length=160)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    accounting_basis: str = Field(min_length=1, max_length=40)
    source_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_at: datetime


class ChartResponse(ChartCreate):
    id: UUID
    company_id: UUID
    version: int
    is_active: bool


class AccountCreate(AccountingSchema):
    chart_version_id: UUID
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=240)
    classification: str
    normal_balance: str
    effective_from: date
    source_system: str = Field(min_length=1, max_length=40)
    source_company_id: str = Field(min_length=1, max_length=160)
    source_account_id: str = Field(min_length=1, max_length=160)
    source_code: str = Field(min_length=1, max_length=80)
    source_type: str = Field(min_length=1, max_length=80)
    source_subtype: str | None = Field(default=None, max_length=80)
    source_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class AccountResponse(AccountingSchema):
    id: UUID
    company_id: UUID
    chart_version_id: UUID
    code: str
    name: str
    classification: str
    normal_balance: str
    status: str
    effective_from: date
    effective_to: date | None


class ControlAssignmentCreate(AccountingSchema):
    account_id: UUID
    control_role: str
    qualifier: str = Field(default="", max_length=160)
    effective_from: date


class PeriodCreate(AccountingSchema):
    name: str = Field(min_length=1, max_length=80)
    start_date: date
    end_date: date


class PeriodResponse(AccountingSchema):
    id: UUID
    company_id: UUID
    name: str
    start_date: date
    end_date: date
    status: str
    version: int


class PeriodTransitionRequest(AccountingSchema):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    finance_approver_user_id: UUID | None = None
    evidence_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    controls_reconciled: bool = False


class JournalLineCreate(AccountingSchema):
    account_id: UUID
    branch_id: UUID | None = None
    debit: Decimal = Field(default=Decimal(0), ge=0, max_digits=20, decimal_places=4)
    credit: Decimal = Field(default=Decimal(0), ge=0, max_digits=20, decimal_places=4)
    description: str = Field(min_length=1, max_length=500)

    @field_validator("debit", "credit")
    @classmethod
    def finite_money(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Money must be finite")
        return value


class JournalCreate(AccountingSchema):
    period_id: UUID
    journal_type: str
    effective_date: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    description: str = Field(min_length=1, max_length=500)
    source_system: str = Field(min_length=1, max_length=80)
    source_type: str = Field(min_length=1, max_length=80)
    source_identity: str = Field(min_length=1, max_length=200)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    posting_rule_version: str = Field(min_length=1, max_length=80)
    client_idempotency_key: str = Field(min_length=1, max_length=160)
    evidence_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    control_override_reason: str | None = Field(default=None, max_length=1000)
    lines: tuple[JournalLineCreate, ...] = Field(min_length=2)


class JournalApprove(AccountingSchema):
    expected_version: int = Field(ge=1)
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=1000)


class JournalTransition(AccountingSchema):
    expected_version: int = Field(ge=1)


class ReversalCreate(AccountingSchema):
    effective_date: date
    period_id: UUID
    client_idempotency_key: str = Field(min_length=1, max_length=160)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=1000)


class JournalLineResponse(AccountingSchema):
    id: UUID
    ordinal: int
    account_id: UUID
    branch_id: UUID | None
    debit: Decimal
    credit: Decimal
    description: str


class JournalResponse(AccountingSchema):
    id: UUID
    company_id: UUID
    period_id: UUID
    journal_type: str
    status: str
    effective_date: date
    currency: str
    description: str
    total_debits: Decimal
    total_credits: Decimal
    source_system: str
    source_type: str
    source_identity: str
    source_digest: str
    posting_rule_version: str
    prepared_by_user_id: UUID
    approved_by_user_id: UUID | None
    posted_at: datetime | None
    reversal_of_id: UUID | None
    version: int
    lines: tuple[JournalLineResponse, ...]


class TrialBalanceResponse(AccountingSchema):
    total_debits: Decimal
    total_credits: Decimal
    net: Decimal
    balanced: bool
