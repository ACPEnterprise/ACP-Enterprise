"""Add HCP migration 2A non-operational evidence foundation.

Revision ID: f3b7d9e1a624
Revises: e0a6c2d8f351
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3b7d9e1a624"
down_revision: str | Sequence[str] | None = "e0a6c2d8f351"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_migration_unlinked_estimate_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("native_estimate_id", sa.String(191), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("package_digest", sa.String(64), nullable=False),
        sa.Column("owner_binding_digest", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("native_customer_id", sa.String(191), nullable=True),
        sa.Column("native_service_location_id", sa.String(191), nullable=True),
        sa.Column("source_status", sa.String(100), nullable=False),
        sa.Column("option_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("source_timestamps", postgresql.JSONB(), nullable=False),
        sa.Column("source_context", postgresql.JSONB(), nullable=False),
        sa.Column("disposition", sa.String(80), nullable=False),
        sa.Column("job_relationship_state", sa.String(20), nullable=False),
        sa.Column("reconciliation_state", sa.String(40), nullable=False),
        sa.Column("operational_effects_enabled", sa.Boolean(), nullable=False),
        sa.Column("accounting_truth_accepted", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "disposition = 'UNLINKED_NON_OPERATIONAL_ESTIMATE'",
            name="ck_unlinked_estimate_evidence_disposition",
        ),
        sa.CheckConstraint(
            "job_relationship_state = 'ABSENT'",
            name="ck_unlinked_estimate_job_absent",
        ),
        sa.CheckConstraint(
            "operational_effects_enabled = false AND accounting_truth_accepted = false",
            name="ck_unlinked_estimate_non_operational",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_unlinked_estimate_evidence_branch_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_system",
            "native_estimate_id",
            name="uq_unlinked_estimate_evidence_native_identity",
        ),
        sa.UniqueConstraint(
            "company_id",
            "branch_id",
            "evidence_digest",
            name="uq_unlinked_estimate_evidence_replay",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION reject_unlinked_estimate_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'unlinked Estimate source evidence is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_unlinked_estimate_evidence_immutable
        BEFORE UPDATE OR DELETE
        ON operational_migration_unlinked_estimate_evidence
        FOR EACH ROW EXECUTE FUNCTION reject_unlinked_estimate_evidence_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_unlinked_estimate_evidence_immutable "
        "ON operational_migration_unlinked_estimate_evidence"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_unlinked_estimate_evidence_mutation()")
    op.drop_table("operational_migration_unlinked_estimate_evidence")
