"""register economics policy parameter gaps

Revision ID: e6v8r0t2w497
Revises: d5u7q9s1v386
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e6v8r0t2w497"
down_revision: str | Sequence[str] | None = "d5u7q9s1v386"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "economics_policy_snapshots",
        sa.Column(
            "parameter_gap_digests",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.alter_column(
        "economics_policy_snapshots", "parameter_gap_digests", server_default=None
    )
    op.create_table(
        "economics_company_policy_gaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("family_key", sa.String(100), nullable=False),
        sa.Column("gap_key", sa.String(120), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("authority_dependency", sa.String(200), nullable=False),
        sa.Column("effective_start", sa.Date(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("decision_evidence_digest", sa.String(64), nullable=False),
        sa.Column("gap_digest", sa.String(64), nullable=False),
        sa.Column(
            "registered_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "branch_id IS NULL", name="ck_eco_policy_gap_company_scope_v1"
        ),
        sa.CheckConstraint(
            "state IN ('unresolved','resolved')", name="ck_eco_policy_gap_state"
        ),
        sa.UniqueConstraint(
            "company_id",
            "family_key",
            "gap_key",
            "effective_start",
            name="uq_eco_policy_gap_identity",
        ),
    )
    op.create_index(
        "ix_eco_policy_gap_open",
        "economics_company_policy_gaps",
        ["company_id", "family_key", "state"],
    )


def downgrade() -> None:
    op.drop_index("ix_eco_policy_gap_open", table_name="economics_company_policy_gaps")
    op.drop_table("economics_company_policy_gaps")
    op.drop_column("economics_policy_snapshots", "parameter_gap_digests")
