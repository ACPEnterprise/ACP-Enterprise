"""Create governed Payroll compensation-proration policy authority."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5g7i9k1m3o5"
down_revision: str | Sequence[str] | None = "d4f6h8j0l2n4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payroll_compensation_proration_policy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("effective_start", sa.Date(), nullable=False),
        sa.Column("effective_end", sa.Date(), nullable=True),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("provenance", sa.String(160), nullable=False),
        sa.Column("policy_digest", sa.String(64), nullable=False),
        sa.Column(
            "drafted_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "supersedes_policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "payroll_compensation_proration_policy_versions.id",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("policy_version >= 1", name="ck_payroll_proration_version"),
        sa.CheckConstraint(
            "method IN ('unselected','block_payroll','by_work_date')",
            name="ck_payroll_proration_method",
        ),
        sa.CheckConstraint(
            "lifecycle IN ('draft','approved','superseded','retired')",
            name="ck_payroll_proration_lifecycle",
        ),
        sa.CheckConstraint(
            "effective_end IS NULL OR effective_end > effective_start",
            name="ck_payroll_proration_interval",
        ),
        sa.CheckConstraint(
            "(lifecycle = 'draft' AND approved_by_user_id IS NULL AND approved_at IS NULL) "
            "OR (lifecycle <> 'draft' AND approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_payroll_proration_approval",
        ),
        sa.UniqueConstraint(
            "company_id", "policy_version", name="uq_payroll_proration_company_version"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_payroll_proration_company_id"),
        sa.UniqueConstraint(
            "supersedes_policy_id", name="uq_payroll_proration_successor"
        ),
        sa.UniqueConstraint("policy_digest", name="uq_payroll_proration_digest"),
    )


def downgrade() -> None:
    op.drop_table("payroll_compensation_proration_policy_versions")
