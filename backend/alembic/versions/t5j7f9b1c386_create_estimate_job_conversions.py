"""create estimate job conversions

Revision ID: t5j7f9b1c386
Revises: t5j7e9g1i386
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "t5j7f9b1c386"
down_revision: str | None = "t5j7e9g1i386"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "estimate_job_conversions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("branch_id", UUID, nullable=False),
        sa.Column("estimate_id", UUID, nullable=False),
        sa.Column("estimate_revision_id", UUID, nullable=False),
        sa.Column("job_id", UUID, nullable=False),
        sa.Column("estimate_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_lineage", sa.JSON(), nullable=False),
        sa.Column("snapshot_lineage_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("converted_by_user_id", UUID, nullable=False),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_estimate_conversions_company_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "estimate_id"],
            ["estimate_proposals.company_id", "estimate_proposals.id"],
            name="fk_estimate_conversions_estimate",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "estimate_revision_id"],
            ["estimate_revisions.company_id", "estimate_revisions.id"],
            name="fk_estimate_conversions_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id", "job_id"],
            ["jobs.company_id", "jobs.branch_id", "jobs.id"],
            name="fk_estimate_conversions_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["converted_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "estimate_version >= 1", name="ck_estimate_conversions_version"
        ),
        sa.CheckConstraint(
            "snapshot_lineage_digest ~ '^[0-9a-f]{64}$'",
            name="ck_estimate_conversions_digest",
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name="ck_estimate_conversions_idempotency_key",
        ),
        sa.UniqueConstraint(
            "company_id", "estimate_id", name="uq_estimate_conversions_estimate"
        ),
        sa.UniqueConstraint("company_id", "job_id", name="uq_estimate_conversions_job"),
        sa.UniqueConstraint(
            "company_id", "idempotency_key", name="uq_estimate_conversions_idempotency"
        ),
    )
    op.create_index(
        "ix_estimate_conversions_company_branch_time",
        "estimate_job_conversions",
        ["company_id", "branch_id", "converted_at"],
    )
    op.execute(
        "CREATE TRIGGER trg_estimate_conversions_immutable "
        "BEFORE UPDATE OR DELETE ON estimate_job_conversions FOR EACH ROW "
        "EXECUTE FUNCTION reject_estimate_evidence_mutation()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER trg_estimate_conversions_immutable ON estimate_job_conversions"
    )
    op.drop_table("estimate_job_conversions")
