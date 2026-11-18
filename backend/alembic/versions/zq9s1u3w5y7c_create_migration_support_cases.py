"""Persist tenant-scoped onboarding support cases.

Revision ID: zq9s1u3w5y7c
Revises: a1b3c5d7e9f0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "zq9s1u3w5y7c"
down_revision: str | Sequence[str] | None = "a1b3c5d7e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "migration_support_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("onboarding_stage", sa.String(40), nullable=False),
        sa.Column("source", sa.String(80)),
        sa.Column("domain", sa.String(80)),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_migration_support_cases_company_created",
        "migration_support_cases",
        ["company_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_migration_support_cases_company_created", table_name="migration_support_cases")
    op.drop_table("migration_support_cases")
