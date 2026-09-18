"""Create append-only Beacon evaluation history.

Revision ID: p6r8t0v2x4z6
Revises: o5q7s9u1w3y5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p6r8t0v2x4z6"
down_revision: str | Sequence[str] | None = "o5q7s9u1w3y5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "beacon_evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope_identity", sa.String(length=64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluator_version", sa.String(length=80), nullable=False),
        sa.Column("covered_definitions", postgresql.JSONB(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column("provenance_digest", sa.String(length=64), nullable=False),
        sa.Column("run_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(run_digest) = 64", name="ck_beacon_runs_digest"),
        sa.CheckConstraint(
            "length(provenance_digest) = 64",
            name="ck_beacon_runs_provenance_digest",
        ),
        sa.CheckConstraint(
            "length(scope_identity) = 64", name="ck_beacon_runs_scope_identity"
        ),
        sa.CheckConstraint(
            "length(btrim(evaluator_version)) > 0",
            name="ck_beacon_runs_evaluator_version",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_beacon_evaluation_runs_branch",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "scope_identity",
            "evaluated_at",
            "evaluator_version",
            name="uq_beacon_evaluation_run_identity",
        ),
    )
    op.create_index(
        "ix_beacon_runs_company_evaluated",
        "beacon_evaluation_runs",
        ["company_id", "evaluated_at", "id"],
    )
    op.create_table(
        "beacon_signal_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("condition_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("definition_id", sa.String(length=160), nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False),
        sa.Column("evidence_digest", sa.String(length=64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluator_version", sa.String(length=80), nullable=False),
        sa.Column("disposition", sa.String(length=24), nullable=False),
        sa.Column("prior_evaluation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "disposition IN ('new','still_active','changed','resolved','expired','superseded')",
            name="ck_beacon_evaluations_disposition",
        ),
        sa.CheckConstraint(
            "definition_version > 0", name="ck_beacon_evaluations_definition_version"
        ),
        sa.CheckConstraint(
            "length(evidence_digest) = 64",
            name="ck_beacon_evaluations_evidence_digest",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_beacon_evaluations_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prior_evaluation_id"],
            ["beacon_signal_evaluations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["beacon_evaluation_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "condition_key", name="uq_beacon_evaluation_run_condition"
        ),
    )
    op.create_index(
        "ix_beacon_evaluations_company_condition",
        "beacon_signal_evaluations",
        ["company_id", "condition_key", "evaluated_at", "id"],
    )
    op.create_index(
        "ix_beacon_evaluations_company_disposition",
        "beacon_signal_evaluations",
        ["company_id", "disposition", "evaluated_at", "id"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_beacon_evaluation_history_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'Beacon evaluation history is append-only'
            USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$
        """
    )
    for table in ("beacon_evaluation_runs", "beacon_signal_evaluations"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_beacon_evaluation_history_mutation()
            """
        )


def downgrade() -> None:
    for table in ("beacon_signal_evaluations", "beacon_evaluation_runs"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_beacon_evaluation_history_mutation()")
    op.drop_index(
        "ix_beacon_evaluations_company_disposition",
        table_name="beacon_signal_evaluations",
    )
    op.drop_index(
        "ix_beacon_evaluations_company_condition",
        table_name="beacon_signal_evaluations",
    )
    op.drop_table("beacon_signal_evaluations")
    op.drop_index(
        "ix_beacon_runs_company_evaluated", table_name="beacon_evaluation_runs"
    )
    op.drop_table("beacon_evaluation_runs")
