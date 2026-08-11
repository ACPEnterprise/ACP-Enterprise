"""add estimate options discounts and operational tax policy

Revision ID: v7l9h1d3e508
Revises: u6k8g0c2d497
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "v7l9h1d3e508"
down_revision: str | None = "u6k8g0c2d497"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "price_book_option_groups",
        sa.Column(
            "minimum_selections", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "price_book_option_groups",
        sa.Column(
            "maximum_selections", sa.Integer(), nullable=False, server_default="1"
        ),
    )
    op.create_check_constraint(
        "ck_price_book_option_groups_selection_bounds",
        "price_book_option_groups",
        "minimum_selections >= 0 AND maximum_selections >= 1 AND minimum_selections <= maximum_selections",
    )
    op.create_table(
        "operational_tax_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "tax_classification_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("rate_basis_points", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_operational_tax_policy_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "tax_classification_id"],
            [
                "price_book_tax_classifications.company_id",
                "price_book_tax_classifications.id",
            ],
            name="fk_operational_tax_policy_classification",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "rate_basis_points BETWEEN 0 AND 10000",
            name="ck_operational_tax_policy_rate",
        ),
        sa.CheckConstraint("version >= 1", name="ck_operational_tax_policy_version"),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_operational_tax_policy_currency"
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="ck_operational_tax_policy_window",
        ),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_operational_tax_policy_company_id"
        ),
    )
    op.create_index(
        "ix_operational_tax_policy_resolution",
        "operational_tax_policies",
        [
            "company_id",
            "branch_id",
            "tax_classification_id",
            "currency",
            "effective_at",
        ],
    )
    for name, type_ in (
        ("discount_type", sa.String(20)),
        ("discount_value", sa.Numeric(18, 4)),
        ("discount_amount", sa.Numeric(18, 2)),
        ("taxable_basis", sa.Numeric(18, 2)),
        ("tax_amount", sa.Numeric(18, 2)),
    ):
        nullable = name in {"discount_type", "discount_value"}
        op.add_column(
            "estimate_revisions",
            sa.Column(
                name, type_, nullable=nullable, server_default=None if nullable else "0"
            ),
        )
    op.add_column(
        "estimate_revisions",
        sa.Column(
            "calculation_evidence",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "ck_estimate_revisions_calculation_amounts",
        "estimate_revisions",
        "discount_amount >= 0 AND tax_amount >= 0 AND taxable_basis >= 0",
    )
    op.create_check_constraint(
        "ck_estimate_revisions_discount_type",
        "estimate_revisions",
        "discount_type IS NULL OR discount_type IN ('fixed','percentage')",
    )
    for name, type_, default in (
        ("discount_allocation", sa.Numeric(18, 2), "0"),
        ("discounted_basis", sa.Numeric(18, 2), "0"),
        ("tax_amount", sa.Numeric(18, 2), "0"),
        ("taxable", sa.Boolean(), sa.false()),
        ("tax_classification_id", postgresql.UUID(as_uuid=True), None),
        ("tax_policy_id", postgresql.UUID(as_uuid=True), None),
        ("tax_policy_version", sa.Integer(), None),
        ("applied_rate_basis_points", sa.Integer(), None),
    ):
        op.add_column(
            "estimate_revision_line_items",
            sa.Column(name, type_, nullable=default is None, server_default=default),
        )
    for name in ("option_group_id", "option_id"):
        op.add_column(
            "estimate_commercial_snapshot_references",
            sa.Column(name, postgresql.UUID(as_uuid=True)),
        )
    for name in ("minimum_selections", "maximum_selections"):
        op.add_column(
            "estimate_commercial_snapshot_references", sa.Column(name, sa.Integer())
        )


def downgrade() -> None:
    for name in (
        "maximum_selections",
        "minimum_selections",
        "option_id",
        "option_group_id",
    ):
        op.drop_column("estimate_commercial_snapshot_references", name)
    for name in (
        "applied_rate_basis_points",
        "tax_policy_version",
        "tax_policy_id",
        "tax_classification_id",
        "taxable",
        "tax_amount",
        "discounted_basis",
        "discount_allocation",
    ):
        op.drop_column("estimate_revision_line_items", name)
    op.drop_constraint(
        "ck_estimate_revisions_discount_type", "estimate_revisions", type_="check"
    )
    op.drop_constraint(
        "ck_estimate_revisions_calculation_amounts", "estimate_revisions", type_="check"
    )
    for name in (
        "calculation_evidence",
        "tax_amount",
        "taxable_basis",
        "discount_amount",
        "discount_value",
        "discount_type",
    ):
        op.drop_column("estimate_revisions", name)
    op.drop_index(
        "ix_operational_tax_policy_resolution", table_name="operational_tax_policies"
    )
    op.drop_table("operational_tax_policies")
    op.drop_constraint(
        "ck_price_book_option_groups_selection_bounds",
        "price_book_option_groups",
        type_="check",
    )
    op.drop_column("price_book_option_groups", "maximum_selections")
    op.drop_column("price_book_option_groups", "minimum_selections")
