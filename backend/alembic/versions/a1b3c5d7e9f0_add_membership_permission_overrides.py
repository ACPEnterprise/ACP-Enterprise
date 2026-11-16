"""Add company-scoped employee permission overrides.

Revision ID: a1b3c5d7e9f0
Revises: zq9s1u3w5y7b
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "a1b3c5d7e9f0"
down_revision: str | Sequence[str] | None = "zq9s1u3w5y7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "membership_permission_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effect", sa.String(10), nullable=False),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "reason",
            sa.Text,
            nullable=False,
            server_default=sa.text("'Employee access editor'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["memberships.company_id", "memberships.id"],
            name="fk_membership_permission_overrides_company_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"], ["permissions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "effect IN ('grant', 'deny')",
            name="ck_membership_permission_overrides_effect",
        ),
        sa.UniqueConstraint(
            "membership_id",
            "permission_id",
            name="uq_membership_permission_overrides_membership_permission",
        ),
    )
    op.create_index(
        "ix_membership_permission_overrides_company_membership",
        "membership_permission_overrides",
        ["company_id", "membership_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_membership_permission_overrides_company_membership",
        table_name="membership_permission_overrides",
    )
    op.drop_table("membership_permission_overrides")
