"""Create provider-neutral bank connectivity authority.

Revision ID: bx9z1b3d5f7h
Revises: bw8y0a2c4e6g
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "bx9z1b3d5f7h"
down_revision: str | None = "bw8y0a2c4e6g"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounting_bank_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_institution_id", sa.String(180), nullable=False),
        sa.Column("provider_connection_id", sa.String(240), nullable=False),
        sa.Column("institution_name", sa.String(160), nullable=False),
        sa.Column("credential_reference", sa.String(240), nullable=False),
        sa.Column("consent_status", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("cursor", sa.String(512)),
        sa.Column("provider_version", sa.String(80)),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("source_as_of", sa.DateTime(timezone=True)),
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider IN ('plaid','finicity','mx','yodlee','direct_bank')",
            name="ck_bank_connection_provider",
        ),
        sa.CheckConstraint(
            "status IN ('pending','healthy','degraded','reconnect_required','revoked','inactive')",
            name="ck_bank_connection_status",
        ),
        sa.UniqueConstraint(
            "company_id",
            "provider",
            "provider_connection_id",
            name="uq_bank_connection_provider_identity",
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_bank_connection_company_id"),
    )
    op.drop_constraint(
        "accounting_bank_accounts_company_id_ledger_account_id_fkey",
        "accounting_bank_accounts",
        type_="foreignkey",
    )
    op.alter_column("accounting_bank_accounts", "ledger_account_id", nullable=True)
    op.add_column(
        "accounting_bank_accounts",
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounting_bank_connections.id", ondelete="RESTRICT"),
        ),
    )
    op.add_column(
        "accounting_bank_accounts",
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "accounting_bank_accounts", sa.Column("account_subtype", sa.String(48))
    )
    op.add_column(
        "accounting_bank_accounts",
        sa.Column(
            "ownership_scope", sa.String(32), nullable=False, server_default="company"
        ),
    )
    op.create_foreign_key(
        "fk_bank_account_ledger_company",
        "accounting_bank_accounts",
        "accounting_accounts",
        ["company_id", "ledger_account_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "ck_accounting_bank_account_type", "accounting_bank_accounts", type_="check"
    )
    op.create_check_constraint(
        "ck_accounting_bank_account_type",
        "accounting_bank_accounts",
        "account_type IN ('checking','savings','money_market','cash','credit','loan','investment','other')",
    )
    op.create_table(
        "accounting_bank_account_gl_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bank_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ledger_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["company_id", "bank_account_id"],
            ["accounting_bank_accounts.company_id", "accounting_bank_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "ledger_account_id"],
            ["accounting_accounts.company_id", "accounting_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('approved','superseded','revoked')",
            name="ck_bank_gl_mapping_status",
        ),
        sa.UniqueConstraint(
            "company_id",
            "bank_account_id",
            "version",
            name="uq_bank_gl_mapping_version",
        ),
    )
    op.create_table(
        "accounting_bank_balance_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bank_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_balance", sa.Numeric(18, 2)),
        sa.Column("available_balance", sa.Numeric(18, 2)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("balance_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_cursor", sa.String(512)),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("provenance", postgresql.JSONB, nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "bank_account_id"],
            ["accounting_bank_accounts.company_id", "accounting_bank_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id",
            "bank_account_id",
            "source_digest",
            name="uq_bank_balance_evidence_digest",
        ),
    )
    for column in (
        sa.Column("authorized_date", sa.Date),
        sa.Column("pending_transaction_id", sa.String(240)),
        sa.Column(
            "evidence_status", sa.String(16), nullable=False, server_default="active"
        ),
        sa.Column(
            "provider_metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "category_metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("provider_cursor", sa.String(512)),
    ):
        op.add_column("accounting_bank_transactions", column)
    op.create_check_constraint(
        "ck_bank_transaction_evidence_status",
        "accounting_bank_transactions",
        "evidence_status IN ('active','removed','superseded')",
    )
    op.create_table(
        "accounting_bank_transaction_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bank_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_transaction_id", sa.String(240), nullable=False),
        sa.Column("provider_cursor", sa.String(512)),
        sa.Column("change_type", sa.String(16), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("evidence", postgresql.JSONB, nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "bank_transaction_id"],
            [
                "accounting_bank_transactions.company_id",
                "accounting_bank_transactions.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "change_type IN ('added','modified','removed')",
            name="ck_bank_transaction_version_change_type",
        ),
        sa.UniqueConstraint(
            "company_id",
            "bank_transaction_id",
            "source_digest",
            name="uq_bank_transaction_version_digest",
        ),
    )


def downgrade() -> None:
    op.drop_table("accounting_bank_transaction_versions")
    op.drop_constraint(
        "ck_bank_transaction_evidence_status",
        "accounting_bank_transactions",
        type_="check",
    )
    for name in (
        "provider_cursor",
        "category_metadata",
        "provider_metadata",
        "evidence_status",
        "pending_transaction_id",
        "authorized_date",
    ):
        op.drop_column("accounting_bank_transactions", name)
    op.drop_table("accounting_bank_balance_evidence")
    op.drop_table("accounting_bank_account_gl_mappings")
    op.drop_constraint(
        "fk_bank_account_ledger_company", "accounting_bank_accounts", type_="foreignkey"
    )
    for name in ("ownership_scope", "account_subtype", "branch_id", "connection_id"):
        op.drop_column("accounting_bank_accounts", name)
    op.alter_column("accounting_bank_accounts", "ledger_account_id", nullable=False)
    op.create_foreign_key(
        "accounting_bank_accounts_company_id_ledger_account_id_fkey",
        "accounting_bank_accounts",
        "accounting_accounts",
        ["company_id", "ledger_account_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "ck_accounting_bank_account_type", "accounting_bank_accounts", type_="check"
    )
    op.create_check_constraint(
        "ck_accounting_bank_account_type",
        "accounting_bank_accounts",
        "account_type IN ('checking','savings','money_market','cash','other')",
    )
    op.drop_table("accounting_bank_connections")
