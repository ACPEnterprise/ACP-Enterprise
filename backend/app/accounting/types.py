from enum import StrEnum


class AccountClassification(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class NormalBalance(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class PeriodStatus(StrEnum):
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    REOPENED = "reopened"


class JournalStatus(StrEnum):
    DRAFT = "draft"
    PREPARED = "prepared"
    APPROVED = "approved"
    POSTED = "posted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class JournalType(StrEnum):
    MANUAL = "manual"
    AUTOMATED = "automated"
    OPENING = "opening"
    REVERSAL = "reversal"
    CORRECTIVE = "corrective"


class ApprovalType(StrEnum):
    JOURNAL = "journal"
    PERIOD_REOPEN = "period_reopen"
    OPENING_STATE = "opening_state"
    RECONCILIATION = "reconciliation"


class ControlRole(StrEnum):
    ACCOUNTS_RECEIVABLE = "accounts_receivable"
    ACCOUNTS_PAYABLE = "accounts_payable"
    BANK_CASH = "bank_cash"
    UNDEPOSITED_FUNDS = "undeposited_funds"
    PAYMENT_CLEARING = "payment_clearing"
    SALES_TAX_PAYABLE = "sales_tax_payable"
    INVENTORY_ASSET = "inventory_asset"
    PAYROLL_LIABILITY = "payroll_liability"
    OPENING_BALANCE = "opening_balance"
