"""Create provider-neutral current accounting operation registers.

Revision ID: zq9s1u3w5y7a
Revises: yp8r0t2v4x6z
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "zq9s1u3w5y7a"
down_revision: str | Sequence[str] | None = "yp8r0t2v4x6z"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounting_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("reference", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("journal_id", postgresql.UUID(as_uuid=True)),
        sa.Column("related_operation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('undeposited_receipt','deposit','card_account','card_charge','card_credit','card_payment','fixed_asset','depreciation','tax_accrual','tax_payment','inventory_valuation','inventory_purchase','inventory_usage','inventory_adjustment','job_cost','cutover_activation')",
            name="ck_accounting_operation_kind",
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','posted','reversed')",
            name="ck_accounting_operation_status",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_accounting_operation_amount"),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_accounting_operation_currency"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_id"],
            ["accounting_journals.company_id", "accounting_journals.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "related_operation_id"],
            ["accounting_operations.company_id", "accounting_operations.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_accounting_operation_company_id"
        ),
        sa.UniqueConstraint(
            "company_id",
            "kind",
            "reference",
            name="uq_accounting_operation_reference",
        ),
    )
    op.create_index(
        "ix_accounting_operation_company_kind_date",
        "accounting_operations",
        ["company_id", "kind", "effective_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_accounting_operation_company_kind_date",
        table_name="accounting_operations",
    )
    op.drop_table("accounting_operations")
