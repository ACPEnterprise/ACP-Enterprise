"""create companies and branches

Revision ID: c7b9e1d4a632
Revises: 8f3c2d1a9b47
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7b9e1d4a632"
down_revision: Union[str, Sequence[str], None] = "8f3c2d1a9b47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(btrim(name)) > 0",
            name="ck_companies_name_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(code)) > 0 AND code = upper(code)",
            name="ck_companies_code_normalized",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'suspended')",
            name="ck_companies_status",
        ),
        sa.CheckConstraint(
            "length(btrim(timezone)) > 0",
            name="ck_companies_timezone_not_blank",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_companies"),
        sa.UniqueConstraint("code", name="uq_companies_code"),
    )
    op.create_index("ix_companies_archived_at", "companies", ["archived_at"])

    op.create_table(
        "branches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(btrim(name)) > 0",
            name="ck_branches_name_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(code)) > 0 AND code = upper(code)",
            name="ck_branches_code_normalized",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_branches_status",
        ),
        sa.CheckConstraint(
            "length(btrim(timezone)) > 0",
            name="ck_branches_timezone_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_branches_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_branches"),
        sa.UniqueConstraint(
            "company_id",
            "code",
            name="uq_branches_company_id_code",
        ),
    )
    op.create_index("ix_branches_archived_at", "branches", ["archived_at"])
    op.create_index("ix_branches_company_id", "branches", ["company_id"])
    op.create_index(
        "uq_branches_active_primary_company",
        "branches",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text(
            "is_primary AND status = 'active' AND archived_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_branches_active_primary_company",
        table_name="branches",
    )
    op.drop_index("ix_branches_company_id", table_name="branches")
    op.drop_index("ix_branches_archived_at", table_name="branches")
    op.drop_table("branches")
    op.drop_index("ix_companies_archived_at", table_name="companies")
    op.drop_table("companies")
