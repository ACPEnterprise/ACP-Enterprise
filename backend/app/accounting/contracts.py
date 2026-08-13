from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class JournalLineInput:
    account_id: UUID
    debit: Decimal
    credit: Decimal
    description: str
    branch_id: UUID | None = None


@dataclass(frozen=True)
class JournalRecord:
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


@dataclass(frozen=True)
class TrialBalanceRecord:
    total_debits: Decimal
    total_credits: Decimal
    net: Decimal
