"""Create Beta Release service principals.

Revision ID: tq0f2h4j6l8n
Revises: ti9k1m3o5q7s
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "tq0f2h4j6l8n"
down_revision: str | None = "ti9k1m3o5q7s"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "release_service_principals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("environment", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('active','revoked')", name="ck_release_principals_state"
        ),
        sa.CheckConstraint("version >= 1", name="ck_release_principals_version"),
        sa.CheckConstraint(
            "environment IN ('beta','preview','test')",
            name="ck_release_principals_environment",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_release_principals_membership_company",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_release_principals_user"),
        sa.UniqueConstraint(
            "company_id", "environment", name="uq_release_principals_scope"
        ),
    )


def downgrade() -> None:
    op.drop_table("release_service_principals")
