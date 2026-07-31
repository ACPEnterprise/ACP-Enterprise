"""add authoritative economics ingestion

Revision ID: b5d9f3a7c201
Revises: a4c8e2f6b190
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b5d9f3a7c201"
down_revision: str | Sequence[str] | None = "a4c8e2f6b190"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, type_ in (
        ("accounting_basis", sa.String(length=16)),
        ("correction_kind", sa.String(length=20)),
        ("corrects_fact_id", postgresql.UUID(as_uuid=True)),
        ("input_digest", sa.String(length=64)),
        ("effective_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("business_economics_facts", sa.Column(name, type_, nullable=True))
    op.execute(
        sa.text(
            "UPDATE business_economics_facts SET accounting_basis = 'accrual', "
            "correction_kind = 'original', input_digest = "
            "md5(id::text) || md5('fact:' || id::text), effective_at = occurred_at"
        )
    )
    for name in (
        "accounting_basis",
        "correction_kind",
        "input_digest",
        "effective_at",
    ):
        op.alter_column("business_economics_facts", name, nullable=False)
    op.create_foreign_key(
        "fk_business_economics_facts_corrects_fact_id",
        "business_economics_facts",
        "business_economics_facts",
        ["corrects_fact_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_business_economics_facts_accounting_basis",
        "business_economics_facts",
        "accounting_basis IN ('accrual', 'cash', 'operational')",
    )
    op.create_check_constraint(
        "ck_business_economics_facts_correction_kind",
        "business_economics_facts",
        "correction_kind IN ('original', 'reversal', 'supersession', 'effective_date')",
    )
    op.create_check_constraint(
        "ck_business_economics_facts_correction_reference",
        "business_economics_facts",
        "(correction_kind = 'original' AND corrects_fact_id IS NULL) OR "
        "(correction_kind <> 'original' AND corrects_fact_id IS NOT NULL)",
    )
    op.create_unique_constraint(
        "uq_business_economics_facts_input_digest",
        "business_economics_facts",
        ["company_id", "input_digest"],
    )

    op.add_column(
        "business_economics_profit_measurements",
        sa.Column("input_digest", sa.String(length=64), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE business_economics_profit_measurements SET input_digest = "
            "md5(id::text) || md5('measurement:' || id::text)"
        )
    )
    op.alter_column(
        "business_economics_profit_measurements", "input_digest", nullable=False
    )
    op.create_unique_constraint(
        "uq_business_economics_profit_measurements_input_digest",
        "business_economics_profit_measurements",
        ["company_id", "input_digest"],
    )

    op.create_table(
        "business_economics_recalculation_scopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("reason_fact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "scope_type IN ('job', 'branch', 'company')",
            name="ck_business_economics_recalculation_scope_type",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reason_fact_id"],
            ["business_economics_facts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_business_economics_recalculation_pending",
        "business_economics_recalculation_scopes",
        ["company_id", "processed_at", "requested_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_business_economics_recalculation_pending",
        table_name="business_economics_recalculation_scopes",
    )
    op.drop_table("business_economics_recalculation_scopes")
    op.drop_constraint(
        "uq_business_economics_profit_measurements_input_digest",
        "business_economics_profit_measurements",
        type_="unique",
    )
    op.drop_column("business_economics_profit_measurements", "input_digest")
    op.drop_constraint(
        "uq_business_economics_facts_input_digest",
        "business_economics_facts",
        type_="unique",
    )
    op.drop_constraint(
        "ck_business_economics_facts_correction_reference",
        "business_economics_facts",
        type_="check",
    )
    op.drop_constraint(
        "ck_business_economics_facts_correction_kind",
        "business_economics_facts",
        type_="check",
    )
    op.drop_constraint(
        "ck_business_economics_facts_accounting_basis",
        "business_economics_facts",
        type_="check",
    )
    op.drop_constraint(
        "fk_business_economics_facts_corrects_fact_id",
        "business_economics_facts",
        type_="foreignkey",
    )
    for name in (
        "effective_at",
        "input_digest",
        "corrects_fact_id",
        "correction_kind",
        "accounting_basis",
    ):
        op.drop_column("business_economics_facts", name)
