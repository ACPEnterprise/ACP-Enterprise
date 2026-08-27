"""create technician field evidence

Revision ID: z1q3l5n7r942
Revises: y0p2k4m6q831
Create Date: 2026-08-27 19:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z1q3l5n7r942"
down_revision: str | Sequence[str] | None = "y0p2k4m6q831"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "field_work_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("note_type", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("recorded_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "note_type IN ('work_performed','internal','customer_visible')",
            name="ck_field_notes_type",
        ),
        sa.CheckConstraint("length(btrim(content)) > 0", name="ck_field_notes_content"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_notes_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["dispatch_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_field_notes_idempotency"
        ),
    )
    op.create_index(
        "ix_field_notes_job_created",
        "field_work_notes",
        ["company_id", "job_id", "created_at"],
    )
    op.create_table(
        "field_customer_approvals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("disposition", sa.String(24), nullable=False),
        sa.Column("customer_name", sa.String(200)),
        sa.Column("reason", sa.Text()),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("recorded_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "disposition IN ('approved','unavailable','refused')",
            name="ck_field_approvals_disposition",
        ),
        sa.CheckConstraint(
            "(disposition = 'approved' AND customer_name IS NOT NULL) OR (disposition <> 'approved' AND reason IS NOT NULL)",
            name="ck_field_approvals_evidence",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_approvals_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["dispatch_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_field_approvals_idempotency"
        ),
    )
    op.create_index(
        "ix_field_approvals_job_created",
        "field_customer_approvals",
        ["company_id", "job_id", "created_at"],
    )
    op.create_table(
        "field_invoice_handoffs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("requested_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','completed','reconciliation_required')",
            name="ck_field_handoffs_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_handoffs_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["dispatch_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "job_id", name="uq_field_handoffs_job"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_field_handoffs_idempotency"
        ),
    )


def downgrade() -> None:
    op.drop_table("field_invoice_handoffs")
    op.drop_index(
        "ix_field_approvals_job_created", table_name="field_customer_approvals"
    )
    op.drop_table("field_customer_approvals")
    op.drop_index("ix_field_notes_job_created", table_name="field_work_notes")
    op.drop_table("field_work_notes")
