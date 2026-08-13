from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChartVersion(Base):
    __tablename__ = "accounting_chart_versions"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_accounting_chart_name"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_accounting_chart_currency"),
        CheckConstraint(
            "length(btrim(accounting_basis)) > 0", name="ck_accounting_chart_basis"
        ),
        UniqueConstraint(
            "company_id", "version", name="uq_accounting_chart_company_version"
        ),
        UniqueConstraint("company_id", "id", name="uq_accounting_chart_company_id"),
        Index(
            "uq_accounting_chart_one_active",
            "company_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    accounting_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    source_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Account(Base):
    __tablename__ = "accounting_accounts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "chart_version_id"],
            ["accounting_chart_versions.company_id", "accounting_chart_versions.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "classification IN ('asset','liability','equity','revenue','expense')",
            name="ck_accounting_accounts_classification",
        ),
        CheckConstraint(
            "normal_balance IN ('debit','credit')",
            name="ck_accounting_accounts_normal_balance",
        ),
        CheckConstraint(
            "status IN ('active','archived')", name="ck_accounting_accounts_status"
        ),
        CheckConstraint("length(btrim(code)) > 0", name="ck_accounting_accounts_code"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_accounting_accounts_name"),
        UniqueConstraint(
            "company_id", "code", name="uq_accounting_accounts_company_code"
        ),
        UniqueConstraint("company_id", "id", name="uq_accounting_accounts_company_id"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    chart_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    classification: Mapped[str] = mapped_column(String(16), nullable=False)
    normal_balance: Mapped[str] = mapped_column(String(6), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active")
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AccountSourceIdentity(Base):
    __tablename__ = "accounting_account_source_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["accounting_accounts.company_id", "accounting_accounts.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_company_id",
            "source_account_id",
            name="uq_accounting_source_identity",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    source_company_id: Mapped[str] = mapped_column(String(160), nullable=False)
    source_account_id: Mapped[str] = mapped_column(String(160), nullable=False)
    source_code: Mapped[str] = mapped_column(String(80), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_subtype: Mapped[str | None] = mapped_column(String(80))
    source_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ControlAccountAssignment(Base):
    __tablename__ = "accounting_control_account_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["accounting_accounts.company_id", "accounting_accounts.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "control_role IN ('accounts_receivable','accounts_payable','bank_cash','undeposited_funds','payment_clearing','sales_tax_payable','inventory_asset','payroll_liability','opening_balance')",
            name="ck_accounting_control_role",
        ),
        UniqueConstraint(
            "company_id",
            "control_role",
            "qualifier",
            "effective_from",
            name="uq_accounting_control_assignment",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    control_role: Mapped[str] = mapped_column(String(32), nullable=False)
    qualifier: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    approved_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )


class AccountingPeriod(Base):
    __tablename__ = "accounting_periods"
    __table_args__ = (
        CheckConstraint("start_date <= end_date", name="ck_accounting_period_dates"),
        CheckConstraint(
            "status IN ('open','closing','closed','reopened')",
            name="ck_accounting_period_status",
        ),
        UniqueConstraint(
            "company_id", "start_date", "end_date", name="uq_accounting_period_range"
        ),
        UniqueConstraint("company_id", "id", name="uq_accounting_period_company_id"),
        Index("ix_accounting_period_lookup", "company_id", "start_date", "end_date"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="open")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PeriodTransition(Base):
    __tablename__ = "accounting_period_transitions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "from_status IN ('open','closing','closed','reopened') AND to_status IN ('open','closing','closed','reopened') AND from_status <> to_status",
            name="ck_accounting_period_transition",
        ),
        UniqueConstraint(
            "company_id",
            "period_id",
            "from_version",
            name="uq_accounting_period_transition_version",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    period_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    from_status: Mapped[str] = mapped_column(String(12), nullable=False)
    to_status: Mapped[str] = mapped_column(String(12), nullable=False)
    from_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    evidence_digest: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Journal(Base):
    __tablename__ = "accounting_journals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "reversal_of_id"],
            ["accounting_journals.company_id", "accounting_journals.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "journal_type IN ('manual','automated','opening','reversal','corrective')",
            name="ck_accounting_journal_type",
        ),
        CheckConstraint(
            "status IN ('draft','prepared','approved','posted','rejected','cancelled')",
            name="ck_accounting_journal_status",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_accounting_journal_currency"
        ),
        CheckConstraint(
            "total_debits >= 0 AND total_credits >= 0",
            name="ck_accounting_journal_totals_nonnegative",
        ),
        CheckConstraint(
            "status <> 'posted' OR (total_debits > 0 AND total_debits = total_credits AND approved_by_user_id IS NOT NULL AND posted_at IS NOT NULL)",
            name="ck_accounting_journal_posted_balanced",
        ),
        UniqueConstraint("company_id", "id", name="uq_accounting_journal_company_id"),
        UniqueConstraint(
            "company_id",
            "client_idempotency_key",
            name="uq_accounting_journal_client_key",
        ),
        UniqueConstraint(
            "company_id", "reversal_of_id", name="uq_accounting_journal_reversal"
        ),
        Index("ix_accounting_journal_period", "company_id", "period_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    period_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    journal_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft")
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    total_debits: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    total_credits: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_identity: Mapped[str] = mapped_column(String(200), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    posting_rule_version: Mapped[str] = mapped_column(String(80), nullable=False)
    client_idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    prepared_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_of_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class JournalLine(Base):
    __tablename__ = "accounting_journal_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["accounting_journals.company_id", "accounting_journals.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["accounting_accounts.company_id", "accounting_accounts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="ck_accounting_line_one_side",
        ),
        UniqueConstraint("journal_id", "ordinal", name="uq_accounting_line_ordinal"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    journal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    debit: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    credit: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class JournalApproval(Base):
    __tablename__ = "accounting_journal_approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["accounting_journals.company_id", "accounting_journals.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "approval_type IN ('journal','period_reopen','opening_state','reconciliation')",
            name="ck_accounting_approval_type",
        ),
        UniqueConstraint(
            "company_id",
            "journal_id",
            "approval_type",
            name="uq_accounting_journal_approval",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    journal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    approval_type: Mapped[str] = mapped_column(String(24), nullable=False)
    approved_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PostingSource(Base):
    __tablename__ = "accounting_posting_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["accounting_journals.company_id", "accounting_journals.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id",
            "source_system",
            "source_type",
            "source_identity",
            "posting_rule_version",
            name="uq_accounting_posting_source",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    journal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_identity: Mapped[str] = mapped_column(String(200), nullable=False)
    posting_rule_version: Mapped[str] = mapped_column(String(80), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PostingFailure(Base):
    __tablename__ = "accounting_posting_failures"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(error_code)) > 0", name="ck_accounting_failure_code"
        ),
        Index(
            "ix_accounting_failure_source",
            "company_id",
            "source_system",
            "source_type",
            "source_identity",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(80), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_identity: Mapped[str] = mapped_column(String(200), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str] = mapped_column(String(80), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
