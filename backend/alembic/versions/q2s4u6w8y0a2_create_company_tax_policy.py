"""Create versioned Company tax-policy authority.

Revision ID: q2s4u6w8y0a2
Revises: o1q9s27h4u0v
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "q2s4u6w8y0a2"
down_revision: str | Sequence[str] | None = "o1q9s27h4u0v"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "company_tax_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_identity", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_service_treatment", sa.String(length=24), nullable=False),
        sa.Column("customer_material_treatment", sa.String(length=24), nullable=False),
        sa.Column(
            "purchase_material_tax_handling", sa.String(length=24), nullable=False
        ),
        sa.Column("authority_source", sa.String(length=80), nullable=False),
        sa.Column("authority_notes", sa.Text(), nullable=True),
        sa.Column("authorized_exceptions", postgresql.JSONB(), nullable=False),
        sa.Column("supersedes_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("certified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("certified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_company_tax_policy_version"),
        sa.CheckConstraint(
            "status IN ('draft','certified','superseded')",
            name="ck_company_tax_policy_status",
        ),
        sa.CheckConstraint(
            "customer_service_treatment IN ('NOT_TAXED','TAXED','REVIEW_REQUIRED')",
            name="ck_company_tax_policy_service_treatment",
        ),
        sa.CheckConstraint(
            "customer_material_treatment IN ('NOT_TAXED','TAXED','REVIEW_REQUIRED')",
            name="ck_company_tax_policy_material_treatment",
        ),
        sa.CheckConstraint(
            "purchase_material_tax_handling IN ('PAID_AT_PURCHASE','EXEMPT','REVIEW_REQUIRED')",
            name="ck_company_tax_policy_purchase_handling",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="ck_company_tax_policy_window",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["certified_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_policy_id"], ["company_tax_policies.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "policy_identity",
            "version",
            name="uq_company_tax_policy_version",
        ),
    )
    op.create_index(
        "ix_company_tax_policy_effective",
        "company_tax_policies",
        ["company_id", "status", "effective_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_company_tax_policy_effective", table_name="company_tax_policies")
    op.drop_table("company_tax_policies")
