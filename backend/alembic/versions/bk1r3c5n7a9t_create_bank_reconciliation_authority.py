"""create bank reconciliation authority

Revision ID: bk1r3c5n7a9t
Revises: 19i4k89084j8, ti9k1m3o5q7s, g5e4c93b0f6d, d2b1f49e7c0a
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "bk1r3c5n7a9t"
down_revision: str | tuple[str, ...] | None = (
    "19i4k89084j8",
    "ti9k1m3o5q7s",
    "g5e4c93b0f6d",
    "d2b1f49e7c0a",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

U = postgresql.UUID(as_uuid=True)
J = postgresql.JSONB(astext_type=sa.Text())
M = sa.Numeric(18, 2)
TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "accounting_bank_accounts",
        sa.Column("id", U, primary_key=True),
        sa.Column(
            "company_id",
            U,
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ledger_account_id", U, nullable=False),
        sa.Column("institution_name", sa.String(160), nullable=False),
        sa.Column("account_name", sa.String(160), nullable=False),
        sa.Column("account_type", sa.String(24), nullable=False),
        sa.Column("masked_identity", sa.String(40), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_system", sa.String(40), nullable=False),
        sa.Column("source_account_id", sa.String(180), nullable=False),
        sa.Column("source_version", sa.String(80), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("source_as_of", TZ, nullable=False),
        sa.Column("opening_balance", M),
        sa.Column("opening_balance_date", sa.Date()),
        sa.Column("opening_balance_provenance", J, nullable=False),
        sa.Column(
            "created_by_user_id",
            U,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "ledger_account_id"],
            ["accounting_accounts.company_id", "accounting_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "account_type IN ('checking','savings','money_market','cash','other')",
            name="ck_accounting_bank_account_type",
        ),
        sa.CheckConstraint(
            "status IN ('active','inactive')", name="ck_accounting_bank_account_status"
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_bank_account_currency"),
        sa.CheckConstraint(
            "length(btrim(masked_identity)) > 0", name="ck_bank_account_masked_identity"
        ),
        sa.CheckConstraint(
            "opening_balance IS NULL OR (opening_balance_date IS NOT NULL AND opening_balance_provenance <> '{}'::jsonb)",
            name="ck_bank_account_opening_provenance",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_account_id",
            name="uq_bank_account_source_identity",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_bank_account_company_id"),
    )
    op.create_table(
        "accounting_bank_transactions",
        sa.Column("id", U, primary_key=True),
        sa.Column("company_id", U, nullable=False),
        sa.Column("bank_account_id", U, nullable=False),
        sa.Column("source_system", sa.String(40), nullable=False),
        sa.Column("external_transaction_id", sa.String(240), nullable=False),
        sa.Column("source_version", sa.String(80), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("acquired_at", TZ, nullable=False),
        sa.Column("source_as_of", TZ, nullable=False),
        sa.Column("posted_date", sa.Date(), nullable=False),
        sa.Column("effective_date", sa.Date()),
        sa.Column("amount", M, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("direction", sa.String(12), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("memo", sa.Text()),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("prior_source_digest", sa.String(64)),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "bank_account_id"],
            ["accounting_bank_accounts.company_id", "accounting_bank_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "kind IN ('deposit','withdrawal','check','ach','merchant_settlement','fee','interest','refund','reversal','transfer','payroll','vendor_payment','owner_movement','other')",
            name="ck_bank_transaction_kind",
        ),
        sa.CheckConstraint(
            "state IN ('pending','posted')", name="ck_bank_transaction_state"
        ),
        sa.CheckConstraint(
            "direction IN ('inflow','outflow')", name="ck_bank_transaction_direction"
        ),
        sa.CheckConstraint("amount > 0", name="ck_bank_transaction_positive_amount"),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_bank_transaction_currency"
        ),
        sa.UniqueConstraint(
            "company_id",
            "bank_account_id",
            "source_system",
            "external_transaction_id",
            name="uq_bank_transaction_source_identity",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_bank_transaction_company_id"),
    )
    op.create_index(
        "ix_bank_transaction_period",
        "accounting_bank_transactions",
        ["company_id", "bank_account_id", "posted_date"],
    )
    op.create_table(
        "accounting_bank_transaction_matches",
        sa.Column("id", U, primary_key=True),
        sa.Column("company_id", U, nullable=False),
        sa.Column("bank_transaction_id", U, nullable=False),
        sa.Column("state", sa.String(28), nullable=False),
        sa.Column("target_type", sa.String(48)),
        sa.Column("target_identity", sa.String(240)),
        sa.Column("candidate_evidence", J, nullable=False),
        sa.Column("deterministic", sa.Boolean(), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column(
            "decided_by_user_id",
            U,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("created_at", TZ, nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "bank_transaction_id"],
            [
                "accounting_bank_transactions.company_id",
                "accounting_bank_transactions.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "state IN ('matched','unmatched','ambiguous','review_required','ignored','transfer_candidate','reconciliation_only')",
            name="ck_bank_transaction_match_state",
        ),
        sa.CheckConstraint(
            "NOT deterministic OR state = 'matched'",
            name="ck_bank_match_deterministic_state",
        ),
        sa.UniqueConstraint(
            "company_id", "bank_transaction_id", name="uq_bank_match_transaction"
        ),
    )
    op.create_table(
        "accounting_bank_reconciliations",
        sa.Column("id", U, primary_key=True),
        sa.Column("company_id", U, nullable=False),
        sa.Column("bank_account_id", U, nullable=False),
        sa.Column("statement_identity", sa.String(240), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("ending_balance", M, nullable=False),
        sa.Column("book_balance", M, nullable=False),
        sa.Column("cleared_total", M, nullable=False),
        sa.Column("outstanding_total", M, nullable=False),
        sa.Column("difference", M, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("cleared_transaction_ids", J, nullable=False),
        sa.Column("outstanding_items", J, nullable=False),
        sa.Column("source_evidence", J, nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column(
            "preparer_user_id",
            U,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "reviewer_user_id",
            U,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("prepared_at", TZ, nullable=False),
        sa.Column("closed_at", TZ),
        sa.ForeignKeyConstraint(
            ["company_id", "bank_account_id"],
            ["accounting_bank_accounts.company_id", "accounting_bank_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "period_start <= period_end", name="ck_bank_reconciliation_period"
        ),
        sa.CheckConstraint(
            "status IN ('draft','review_required','ready_to_close','closed')",
            name="ck_bank_reconciliation_status",
        ),
        sa.CheckConstraint(
            "status <> 'closed' OR (difference = 0 AND closed_at IS NOT NULL AND reviewer_user_id IS NOT NULL)",
            name="ck_bank_reconciliation_closed_integrity",
        ),
        sa.UniqueConstraint(
            "company_id",
            "bank_account_id",
            "statement_identity",
            name="uq_bank_reconciliation_statement",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_bank_reconciliation_company_id"
        ),
    )


def downgrade() -> None:
    op.drop_table("accounting_bank_reconciliations")
    op.drop_table("accounting_bank_transaction_matches")
    op.drop_index(
        "ix_bank_transaction_period", table_name="accounting_bank_transactions"
    )
    op.drop_table("accounting_bank_transactions")
    op.drop_table("accounting_bank_accounts")
