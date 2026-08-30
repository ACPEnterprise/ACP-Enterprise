"""immutable economics result history

Revision ID: h6f8j0l2n497
Revises: l0j9h48g5e1c
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "h6f8j0l2n497"
down_revision: str | Sequence[str] | None = "l0j9h48g5e1c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_eco_profitability_result_company_id",
        "economics_profitability_results",
        ["company_id", "id"],
    )
    op.create_table(
        "economics_profitability_result_supersessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "predecessor_result_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("successor_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_kind", sa.String(32), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("basis", sa.String(32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("predecessor_digest", sa.String(64), nullable=False),
        sa.Column("successor_digest", sa.String(64), nullable=False),
        sa.Column("predecessor_package_digest", sa.String(64), nullable=False),
        sa.Column("successor_package_digest", sa.String(64), nullable=False),
        sa.Column("predecessor_computation_digest", sa.String(64), nullable=False),
        sa.Column("successor_computation_digest", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("supersession_digest", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "predecessor_result_id <> successor_result_id",
            name="ck_eco_profitability_supersession_distinct",
        ),
        sa.CheckConstraint(
            "reason IN ('source_correction','policy_recomputation','computation_version','attribution_correction')",
            name="ck_eco_profitability_supersession_reason",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "predecessor_result_id"],
            [
                "economics_profitability_results.company_id",
                "economics_profitability_results.id",
            ],
            name="fk_eco_profitability_supersession_predecessor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "successor_result_id"],
            [
                "economics_profitability_results.company_id",
                "economics_profitability_results.id",
            ],
            name="fk_eco_profitability_supersession_successor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "predecessor_result_id", name="uq_eco_profitability_single_successor"
        ),
        sa.UniqueConstraint(
            "successor_result_id", name="uq_eco_profitability_single_predecessor"
        ),
        sa.UniqueConstraint(
            "company_id", "supersession_digest", name="uq_eco_supersession_digest"
        ),
    )
    op.create_index(
        "ix_eco_profitability_supersession_lineage",
        "economics_profitability_result_supersessions",
        ["company_id", "subject_id", "period_start", "period_end"],
    )
    op.execute(
        """
        CREATE FUNCTION acp_reject_economics_result_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'immutable economics profitability evidence'
            USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_eco_profitability_result_immutable
        BEFORE UPDATE OR DELETE ON economics_profitability_results
        FOR EACH ROW EXECUTE FUNCTION acp_reject_economics_result_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION acp_validate_economics_result_supersession() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE predecessor economics_profitability_results%ROWTYPE;
        DECLARE successor economics_profitability_results%ROWTYPE;
        BEGIN
          SELECT * INTO STRICT predecessor FROM economics_profitability_results
            WHERE company_id = NEW.company_id AND id = NEW.predecessor_result_id;
          SELECT * INTO STRICT successor FROM economics_profitability_results
            WHERE company_id = NEW.company_id AND id = NEW.successor_result_id;
          IF (predecessor.subject_id, predecessor.subject_kind, predecessor.scope,
              predecessor.basis, predecessor.period_start, predecessor.period_end,
              predecessor.currency)
             IS DISTINCT FROM
             (successor.subject_id, successor.subject_kind, successor.scope,
              successor.basis, successor.period_start, successor.period_end,
              successor.currency) THEN
            RAISE EXCEPTION 'economics successor belongs to a different lineage'
              USING ERRCODE = '23514';
          END IF;
          IF (NEW.subject_id, NEW.subject_kind, NEW.scope, NEW.basis,
              NEW.period_start, NEW.period_end, NEW.currency,
              NEW.predecessor_digest, NEW.successor_digest,
              NEW.predecessor_package_digest, NEW.successor_package_digest,
              NEW.predecessor_computation_digest, NEW.successor_computation_digest)
             IS DISTINCT FROM
             (predecessor.subject_id, predecessor.subject_kind, predecessor.scope,
              predecessor.basis, predecessor.period_start, predecessor.period_end,
              predecessor.currency, predecessor.result_digest, successor.result_digest,
              predecessor.package_digest, successor.package_digest,
              predecessor.computation_digest, successor.computation_digest) THEN
            RAISE EXCEPTION 'economics supersession evidence contradicts results'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_eco_profitability_supersession_validate
        BEFORE INSERT ON economics_profitability_result_supersessions
        FOR EACH ROW EXECUTE FUNCTION acp_validate_economics_result_supersession()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_eco_profitability_supersession_immutable
        BEFORE UPDATE OR DELETE ON economics_profitability_result_supersessions
        FOR EACH ROW EXECUTE FUNCTION acp_reject_economics_result_mutation()
        """
    )


def downgrade() -> None:
    # Result rows are never removed. Downgrade removes only the repair contract.
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM economics_profitability_result_supersessions)"
        )
    ):
        raise RuntimeError(
            "refusing destructive downgrade with accepted Economics supersession evidence"
        )
    op.execute(
        "DROP TRIGGER trg_eco_profitability_supersession_immutable ON economics_profitability_result_supersessions"
    )
    op.execute(
        "DROP TRIGGER trg_eco_profitability_supersession_validate ON economics_profitability_result_supersessions"
    )
    op.execute(
        "DROP TRIGGER trg_eco_profitability_result_immutable ON economics_profitability_results"
    )
    op.execute("DROP FUNCTION acp_validate_economics_result_supersession()")
    op.execute("DROP FUNCTION acp_reject_economics_result_mutation()")
    op.drop_index(
        "ix_eco_profitability_supersession_lineage",
        table_name="economics_profitability_result_supersessions",
    )
    op.drop_table("economics_profitability_result_supersessions")
    op.drop_constraint(
        "uq_eco_profitability_result_company_id",
        "economics_profitability_results",
        type_="unique",
    )
