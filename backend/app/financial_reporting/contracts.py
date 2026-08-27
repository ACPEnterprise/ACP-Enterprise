from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReportingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReportScope(ReportingModel):
    company_id: UUID
    branch_id: UUID | None
    scope_label: str
    includes_company_unassigned: bool


class ReportQuality(ReportingModel):
    completeness: str = "complete"
    freshness: str = "current"
    reconciliation: str = "reconciled"
    integrity: str = "passed"
    review: str = "unreviewed"
    variance: Decimal = Decimal(0)


class ReportManifest(ReportingModel):
    report_name: str
    definition_version: str
    company_id: UUID
    branch_id: UUID | None
    currency: str
    accounting_basis: str
    timezone: str
    start_date: date | None
    as_of_date: date
    period_id: UUID | None
    period_status: str | None
    ledger_cutoff: str
    contributing_line_count: int
    generated_at: datetime
    requested_by_user_id: UUID
    checksum: str


class AccountBalanceRow(ReportingModel):
    account_id: UUID
    code: str
    name: str
    classification: str
    normal_balance: str
    status: str
    hierarchy_path: tuple[str, ...]
    beginning_balance: Decimal
    debits: Decimal
    credits: Decimal
    ending_balance: Decimal
    display_balance: Decimal


class TrialBalanceResult(ReportingModel):
    scope: ReportScope
    manifest: ReportManifest
    quality: ReportQuality
    rows: tuple[AccountBalanceRow, ...]
    total_beginning_balance: Decimal
    total_debits: Decimal
    total_credits: Decimal
    total_ending_balance: Decimal


class StatementRow(ReportingModel):
    account_id: UUID
    code: str
    name: str
    classification: str
    amount: Decimal
    hierarchy_path: tuple[str, ...]


class BalanceSheetResult(ReportingModel):
    scope: ReportScope
    manifest: ReportManifest
    quality: ReportQuality
    assets: tuple[StatementRow, ...]
    liabilities: tuple[StatementRow, ...]
    equity: tuple[StatementRow, ...]
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal
    current_earnings: Decimal
    liabilities_equity_and_current_earnings: Decimal


class IncomeStatementResult(ReportingModel):
    scope: ReportScope
    manifest: ReportManifest
    quality: ReportQuality
    revenue: tuple[StatementRow, ...]
    expenses: tuple[StatementRow, ...]
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal


class GeneralLedgerRow(ReportingModel):
    line_id: UUID
    journal_id: UUID
    ordinal: int
    account_id: UUID
    account_code: str
    account_name: str
    branch_id: UUID | None
    period_id: UUID
    period_name: str
    effective_date: date
    posted_at: datetime
    journal_type: str
    journal_description: str
    line_description: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal
    prepared_by_user_id: UUID
    approved_by_user_id: UUID
    source_system: str
    source_type: str
    source_identity: str
    source_digest: str
    posting_rule_version: str
    correlation_id: UUID
    reversal_of_id: UUID | None


class GeneralLedgerResult(ReportingModel):
    scope: ReportScope
    manifest: ReportManifest
    quality: ReportQuality
    account_id: UUID | None
    beginning_balance: Decimal
    total_debits: Decimal
    total_credits: Decimal
    ending_balance: Decimal
    rows: tuple[GeneralLedgerRow, ...]
