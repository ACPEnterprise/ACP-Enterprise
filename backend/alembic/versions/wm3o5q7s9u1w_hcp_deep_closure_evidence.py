"""Create immutable whole-HCP closure evidence.

Revision ID: wm3o5q7s9u1w
Revises: vl2n4p6r8t0v
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "wm3o5q7s9u1w"
down_revision = "vl2n4p6r8t0v"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hcp_cutover_closure_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("master_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_source_digest", sa.String(64), nullable=False),
        sa.Column("packet", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unexplained_gap_count", sa.Integer(), nullable=False),
        sa.Column("replay_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('BLOCKED','RETIREMENT_READY')",
            name="ck_hcp_cutover_closure_status",
        ),
        sa.CheckConstraint(
            "unexplained_gap_count >= 0",
            name="ck_hcp_cutover_closure_unexplained",
        ),
        sa.ForeignKeyConstraint(
            ["master_run_id", "company_id", "branch_id"],
            [
                "hcp_migration_master_runs.id",
                "hcp_migration_master_runs.company_id",
                "hcp_migration_master_runs.branch_id",
            ],
            name="fk_hcp_cutover_closure_master_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "master_run_id",
            "replay_digest",
            name="uq_hcp_cutover_closure_replay",
        ),
    )
    op.create_index(
        "ix_hcp_cutover_closure_scope_status",
        "hcp_cutover_closure_evidence",
        ["company_id", "branch_id", "status", "as_of"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_hcp_cutover_closure_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'HCP cutover closure evidence is append-only'
            USING ERRCODE = '23514';
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_hcp_cutover_closure_append_only "
        "BEFORE UPDATE OR DELETE ON hcp_cutover_closure_evidence "
        "FOR EACH ROW EXECUTE FUNCTION reject_hcp_cutover_closure_mutation()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_hcp_cutover_closure_append_only "
        "ON hcp_cutover_closure_evidence"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_hcp_cutover_closure_mutation()")
    op.drop_index(
        "ix_hcp_cutover_closure_scope_status",
        table_name="hcp_cutover_closure_evidence",
    )
    op.drop_table("hcp_cutover_closure_evidence")
