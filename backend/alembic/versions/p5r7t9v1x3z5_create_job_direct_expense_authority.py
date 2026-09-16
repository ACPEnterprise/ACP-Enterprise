"""Create certified direct-expense-to-Job authority.

Revision ID: p5r7t9v1x3z5
Revises: n4p6r8t0v2x4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p5r7t9v1x3z5"
down_revision: str | Sequence[str] | None = "n4p6r8t0v2x4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "economics_job_direct_expense_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(40), nullable=False),
        sa.Column("source_record_type", sa.String(60), nullable=False),
        sa.Column("source_transaction_id", sa.String(191), nullable=False),
        sa.Column("source_line_id", sa.String(191), nullable=False),
        sa.Column("source_evidence_digest", sa.String(64), nullable=False),
        sa.Column("allocation_version", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("allocation_basis", sa.String(40), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("allocation_digest", sa.String(64), nullable=False),
        sa.Column("supersedes_allocation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("expected_prior_version", sa.Integer()),
        sa.Column("drafted_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("certified_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("certified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("allocation_version >= 1", name="ck_eco_expense_version"),
        sa.CheckConstraint("amount_minor > 0", name="ck_eco_expense_amount"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_eco_expense_currency"),
        sa.CheckConstraint(
            "status IN ('draft','ready_for_certification','certified','superseded','inactive')",
            name="ck_eco_expense_status",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_eco_direct_expense_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_allocation_id"],
            ["economics_job_direct_expense_allocations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["drafted_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["certified_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "source_record_type",
            "source_transaction_id",
            "source_line_id",
            "allocation_version",
            "job_id",
            name="uq_eco_expense_source_version_job",
        ),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_eco_expense_idempotency"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_eco_expense_company_id"),
    )
    op.create_index(
        "ix_eco_expense_job_period",
        "economics_job_direct_expense_allocations",
        ["company_id", "branch_id", "job_id", "effective_date", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_eco_expense_job_period",
        table_name="economics_job_direct_expense_allocations",
    )
    op.drop_table("economics_job_direct_expense_allocations")
