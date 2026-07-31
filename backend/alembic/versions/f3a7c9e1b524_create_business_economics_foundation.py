"""create business economics foundation

Revision ID: f3a7c9e1b524
Revises: e6b2c8d0f374
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f3a7c9e1b524"
down_revision: str | Sequence[str] | None = "e6b2c8d0f374"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_economics_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subject_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("confidence_status", sa.String(length=12), nullable=False),
        sa.Column("confidence_percentage", sa.Integer(), nullable=False),
        sa.Column("confidence_explanation", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('revenue', 'labor', 'materials', 'equipment', 'truck', 'overhead')",
            name="ck_business_economics_facts_category",
        ),
        sa.CheckConstraint(
            "confidence_status IN ('measured', 'estimated', 'unknown')",
            name="ck_business_economics_facts_confidence_status",
        ),
        sa.CheckConstraint(
            "confidence_percentage BETWEEN 0 AND 100",
            name="ck_business_economics_facts_confidence_percentage",
        ),
        sa.CheckConstraint(
            "(amount_minor IS NULL) = (confidence_status = 'unknown')",
            name="ck_business_economics_facts_known_amount",
        ),
        sa.CheckConstraint("version >= 1", name="ck_business_economics_facts_version"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_business_economics_facts_subject",
        "business_economics_facts",
        ["company_id", "subject_type", "subject_id", "occurred_at", "id"],
    )
    op.create_table(
        "business_economics_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_fact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("numerator", sa.Integer(), nullable=False),
        sa.Column("denominator", sa.Integer(), nullable=False),
        sa.Column("allocated_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "denominator > 0", name="ck_business_economics_allocations_denominator"
        ),
        sa.CheckConstraint(
            "numerator >= 0", name="ck_business_economics_allocations_numerator"
        ),
        sa.CheckConstraint(
            "numerator <= denominator", name="ck_business_economics_allocations_ratio"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_fact_id"], ["business_economics_facts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_business_economics_allocations_subject",
        "business_economics_allocations",
        ["company_id", "subject_type", "subject_id", "created_at", "id"],
    )
    op.create_table(
        "business_economics_profit_measurements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subject_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("revenue_minor", sa.BigInteger(), nullable=True),
        sa.Column("labor_minor", sa.BigInteger(), nullable=True),
        sa.Column("materials_minor", sa.BigInteger(), nullable=True),
        sa.Column("equipment_minor", sa.BigInteger(), nullable=True),
        sa.Column("truck_minor", sa.BigInteger(), nullable=True),
        sa.Column("overhead_minor", sa.BigInteger(), nullable=True),
        sa.Column("gross_profit_minor", sa.BigInteger(), nullable=True),
        sa.Column("net_profit_minor", sa.BigInteger(), nullable=True),
        sa.Column("confidence_status", sa.String(length=12), nullable=False),
        sa.Column("confidence_percentage", sa.Integer(), nullable=False),
        sa.Column("confidence_explanation", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence_status IN ('measured', 'estimated', 'unknown')",
            name="ck_business_economics_profit_measurements_confidence_status",
        ),
        sa.CheckConstraint(
            "confidence_percentage BETWEEN 0 AND 100",
            name="ck_business_economics_profit_measurements_confidence_percentage",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_business_economics_profit_measurements_version"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_business_economics_profit_measurements_latest",
        "business_economics_profit_measurements",
        ["company_id", "subject_type", "subject_id", "measured_at", "id"],
    )
    op.execute(
        sa.text(
            "INSERT INTO permissions (id, code, name, resource, action, status, created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'COMPANY_ECONOMICS_READ', 'Company Economics Read', "
            "'business_economics', 'read', 'active', now(), now()) "
            "ON CONFLICT (code) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM permissions WHERE code = 'COMPANY_ECONOMICS_READ'"))
    op.drop_index(
        "ix_business_economics_profit_measurements_latest",
        table_name="business_economics_profit_measurements",
    )
    op.drop_table("business_economics_profit_measurements")
    op.drop_index(
        "ix_business_economics_allocations_subject",
        table_name="business_economics_allocations",
    )
    op.drop_table("business_economics_allocations")
    op.drop_index(
        "ix_business_economics_facts_subject", table_name="business_economics_facts"
    )
    op.drop_table("business_economics_facts")
