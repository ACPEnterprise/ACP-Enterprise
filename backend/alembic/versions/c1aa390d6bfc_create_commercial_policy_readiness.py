"""create commercial policy readiness

Revision ID: c1aa390d6bfc
Revises: 19i4k89084j8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1aa390d6bfc"
down_revision: str | Sequence[str] | None = "19i4k89084j8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commercial_policy_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("policy_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("readiness_reason", sa.String(500), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "policy_type IN ('discount','price_override','estimate_expiration','rounding','tax_readiness','document_template','delivery_readiness')",
            name="ck_commercial_policy_type",
        ),
        sa.CheckConstraint(
            "status IN ('unconfigured','draft','active','inactive')",
            name="ck_commercial_policy_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_commercial_policy_version"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_commercial_policy_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_commercial_policy_command"
        ),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "policy_type",
            "version",
            name="uq_commercial_policy_version",
        ),
    )
    op.create_index(
        "ix_commercial_policy_current",
        "commercial_policy_versions",
        ["company_id", "branch_id", "policy_type", "version"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_commercial_policy_current", table_name="commercial_policy_versions"
    )
    op.drop_table("commercial_policy_versions")
