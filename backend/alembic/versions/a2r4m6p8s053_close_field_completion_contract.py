"""close field completion contract

Revision ID: a2r4m6p8s053
Revises: z1q3l5n7r942
Create Date: 2026-08-27 20:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a2r4m6p8s053"
down_revision: str | Sequence[str] | None = "z1q3l5n7r942"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "field_completion_requirement_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("requirements_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version >= 1", name="ck_field_requirement_snapshot_version"
        ),
        sa.CheckConstraint(
            "requirements_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_field_requirement_snapshot_fingerprint",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_requirement_snapshots_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["dispatch_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "job_id", name="uq_field_requirement_snapshot_job"
        ),
        sa.UniqueConstraint(
            "company_id",
            "job_id",
            "version",
            name="uq_field_requirement_snapshot_version",
        ),
    )
    op.create_table(
        "field_completion_evidence",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column("requirement_code", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("recorded_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_completion_evidence_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["field_completion_requirement_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "snapshot_id",
            "requirement_code",
            name="uq_field_evidence_requirement",
        ),
    )
    op.create_table(
        "field_non_billable_dispositions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("authorized_by_user_id", sa.UUID(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(btrim(reason)) > 0", name="ck_field_non_billable_reason"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_field_non_billable_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["dispatch_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["authorized_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "job_id", name="uq_field_non_billable_job"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_field_non_billable_idempotency"
        ),
    )


def downgrade() -> None:
    op.drop_table("field_non_billable_dispositions")
    op.drop_table("field_completion_evidence")
    op.drop_table("field_completion_requirement_snapshots")
