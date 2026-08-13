"""create internal accounting core

Revision ID: w8m0i2e4f619
Revises: u6k8f0h2j497
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.accounting import models as accounting_models  # noqa: F401

revision: str = "w8m0i2e4f619"
down_revision: str | None = "u6k8f0h2j497"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "accounting_chart_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("accounting_basis", sa.String(40), nullable=False),
        sa.Column("source_checksum", sa.String(64), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("approved_by_user_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_accounting_chart_name"),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_accounting_chart_currency"
        ),
        sa.CheckConstraint(
            "length(btrim(accounting_basis)) > 0", name="ck_accounting_chart_basis"
        ),
        sa.UniqueConstraint(
            "company_id", "version", name="uq_accounting_chart_company_version"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_accounting_chart_company_id"),
    )
    op.create_index(
        "uq_accounting_chart_one_active",
        "accounting_chart_versions",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "accounting_accounts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("chart_version_id", UUID, nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("classification", sa.String(16), nullable=False),
        sa.Column("normal_balance", sa.String(6), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "chart_version_id"],
            ["accounting_chart_versions.company_id", "accounting_chart_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "classification IN ('asset','liability','equity','revenue','expense')",
            name="ck_accounting_accounts_classification",
        ),
        sa.CheckConstraint(
            "normal_balance IN ('debit','credit')",
            name="ck_accounting_accounts_normal_balance",
        ),
        sa.CheckConstraint(
            "status IN ('active','archived')", name="ck_accounting_accounts_status"
        ),
        sa.CheckConstraint(
            "length(btrim(code)) > 0", name="ck_accounting_accounts_code"
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0", name="ck_accounting_accounts_name"
        ),
        sa.UniqueConstraint(
            "company_id", "code", name="uq_accounting_accounts_company_code"
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_accounting_accounts_company_id"
        ),
    )
    op.create_table(
        "accounting_account_source_identities",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("source_system", sa.String(40), nullable=False),
        sa.Column("source_company_id", sa.String(160), nullable=False),
        sa.Column("source_account_id", sa.String(160), nullable=False),
        sa.Column("source_code", sa.String(80), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("source_subtype", sa.String(80)),
        sa.Column("source_checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["accounting_accounts.company_id", "accounting_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_company_id",
            "source_account_id",
            name="uq_accounting_source_identity",
        ),
    )
    op.create_table(
        "accounting_control_account_assignments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("control_role", sa.String(32), nullable=False),
        sa.Column("qualifier", sa.String(160), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("approved_by_user_id", UUID, nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["accounting_accounts.company_id", "accounting_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "control_role IN ('accounts_receivable','accounts_payable','bank_cash','undeposited_funds','payment_clearing','sales_tax_payable','inventory_asset','payroll_liability','opening_balance')",
            name="ck_accounting_control_role",
        ),
        sa.UniqueConstraint(
            "company_id",
            "control_role",
            "qualifier",
            "effective_from",
            name="uq_accounting_control_assignment",
        ),
    )
    op.create_table(
        "accounting_periods",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("start_date <= end_date", name="ck_accounting_period_dates"),
        sa.CheckConstraint(
            "status IN ('open','closing','closed','reopened')",
            name="ck_accounting_period_status",
        ),
        sa.UniqueConstraint(
            "company_id", "start_date", "end_date", name="uq_accounting_period_range"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_accounting_period_company_id"),
    )
    op.create_index(
        "ix_accounting_period_lookup",
        "accounting_periods",
        ["company_id", "start_date", "end_date"],
    )
    op.create_table(
        "accounting_period_transitions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("period_id", UUID, nullable=False),
        sa.Column("from_status", sa.String(12), nullable=False),
        sa.Column("to_status", sa.String(12), nullable=False),
        sa.Column("from_version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_by_user_id", UUID, nullable=False),
        sa.Column("approved_by_user_id", UUID),
        sa.Column("evidence_digest", sa.String(64)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "from_status IN ('open','closing','closed','reopened') AND to_status IN ('open','closing','closed','reopened') AND from_status <> to_status",
            name="ck_accounting_period_transition",
        ),
        sa.UniqueConstraint(
            "company_id",
            "period_id",
            "from_version",
            name="uq_accounting_period_transition_version",
        ),
    )
    op.create_table(
        "accounting_journals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("period_id", UUID, nullable=False),
        sa.Column("journal_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("total_debits", sa.Numeric(20, 4), nullable=False),
        sa.Column("total_credits", sa.Numeric(20, 4), nullable=False),
        sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("source_identity", sa.String(200), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("posting_rule_version", sa.String(80), nullable=False),
        sa.Column("client_idempotency_key", sa.String(160), nullable=False),
        sa.Column("prepared_by_user_id", UUID, nullable=False),
        sa.Column("approved_by_user_id", UUID),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("reversal_of_id", UUID),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "period_id"],
            ["accounting_periods.company_id", "accounting_periods.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "reversal_of_id"],
            ["accounting_journals.company_id", "accounting_journals.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prepared_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "journal_type IN ('manual','automated','opening','reversal','corrective')",
            name="ck_accounting_journal_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft','prepared','approved','posted','rejected','cancelled')",
            name="ck_accounting_journal_status",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_accounting_journal_currency"
        ),
        sa.CheckConstraint(
            "total_debits >= 0 AND total_credits >= 0",
            name="ck_accounting_journal_totals_nonnegative",
        ),
        sa.CheckConstraint(
            "status <> 'posted' OR (total_debits > 0 AND total_debits = total_credits AND approved_by_user_id IS NOT NULL AND posted_at IS NOT NULL)",
            name="ck_accounting_journal_posted_balanced",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_accounting_journal_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "client_idempotency_key",
            name="uq_accounting_journal_client_key",
        ),
        sa.UniqueConstraint(
            "company_id", "reversal_of_id", name="uq_accounting_journal_reversal"
        ),
    )
    op.create_index(
        "ix_accounting_journal_period",
        "accounting_journals",
        ["company_id", "period_id", "status"],
    )
    op.create_table(
        "accounting_journal_lines",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("journal_id", UUID, nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("branch_id", UUID),
        sa.Column("debit", sa.Numeric(20, 4), nullable=False),
        sa.Column("credit", sa.Numeric(20, 4), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["accounting_journals.company_id", "accounting_journals.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "account_id"],
            ["accounting_accounts.company_id", "accounting_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="ck_accounting_line_one_side",
        ),
        sa.UniqueConstraint("journal_id", "ordinal", name="uq_accounting_line_ordinal"),
    )
    op.create_table(
        "accounting_journal_approvals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("journal_id", UUID, nullable=False),
        sa.Column("approval_type", sa.String(24), nullable=False),
        sa.Column("approved_by_user_id", UUID, nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["accounting_journals.company_id", "accounting_journals.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "approval_type IN ('journal','period_reopen','opening_state','reconciliation')",
            name="ck_accounting_approval_type",
        ),
        sa.UniqueConstraint(
            "company_id",
            "journal_id",
            "approval_type",
            name="uq_accounting_journal_approval",
        ),
    )
    op.create_table(
        "accounting_posting_sources",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("journal_id", UUID, nullable=False),
        sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("source_identity", sa.String(200), nullable=False),
        sa.Column("posting_rule_version", sa.String(80), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("correlation_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["accounting_journals.company_id", "accounting_journals.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_type",
            "source_identity",
            "posting_rule_version",
            name="uq_accounting_posting_source",
        ),
    )
    op.create_table(
        "accounting_posting_failures",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("source_identity", sa.String(200), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=False),
        sa.Column("correlation_id", UUID, nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "length(btrim(error_code)) > 0", name="ck_accounting_failure_code"
        ),
    )
    op.create_index(
        "ix_accounting_failure_source",
        "accounting_posting_failures",
        ["company_id", "source_system", "source_type", "source_identity"],
    )
    op.execute("""
        CREATE FUNCTION accounting_reject_posted_mutation() RETURNS trigger AS $$
        BEGIN
          IF OLD.status = 'posted' THEN RAISE EXCEPTION 'posted accounting journals are immutable'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_accounting_journal_immutable BEFORE UPDATE OR DELETE ON accounting_journals
        FOR EACH ROW EXECUTE FUNCTION accounting_reject_posted_mutation();
        CREATE FUNCTION accounting_reject_posted_line_mutation() RETURNS trigger AS $$
        DECLARE target_journal_id uuid;
        BEGIN
          IF TG_OP = 'INSERT' THEN target_journal_id := NEW.journal_id; ELSE target_journal_id := OLD.journal_id; END IF;
          IF EXISTS (SELECT 1 FROM accounting_journals j WHERE j.id = target_journal_id AND j.status = 'posted')
          THEN RAISE EXCEPTION 'posted accounting journal lines are immutable'; END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_accounting_line_immutable BEFORE INSERT OR UPDATE OR DELETE ON accounting_journal_lines
        FOR EACH ROW EXECUTE FUNCTION accounting_reject_posted_line_mutation();
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_accounting_line_immutable ON accounting_journal_lines; DROP FUNCTION IF EXISTS accounting_reject_posted_line_mutation(); DROP TRIGGER IF EXISTS trg_accounting_journal_immutable ON accounting_journals; DROP FUNCTION IF EXISTS accounting_reject_posted_mutation();"
    )
    op.drop_index(
        "ix_accounting_failure_source", table_name="accounting_posting_failures"
    )
    op.drop_table("accounting_posting_failures")
    op.drop_table("accounting_posting_sources")
    op.drop_table("accounting_journal_approvals")
    op.drop_table("accounting_journal_lines")
    op.drop_index("ix_accounting_journal_period", table_name="accounting_journals")
    op.drop_table("accounting_journals")
    op.drop_table("accounting_period_transitions")
    op.drop_index("ix_accounting_period_lookup", table_name="accounting_periods")
    op.drop_table("accounting_periods")
    op.drop_table("accounting_control_account_assignments")
    op.drop_table("accounting_account_source_identities")
    op.drop_table("accounting_accounts")
    op.drop_index(
        "uq_accounting_chart_one_active", table_name="accounting_chart_versions"
    )
    op.drop_table("accounting_chart_versions")
