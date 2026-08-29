"""protect replenishment decision evidence

Revision ID: b9s1o3q5t720
Revises: a8r0n2p4s619
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b9s1o3q5t720"
down_revision: str | Sequence[str] | None = "a8r0n2p4s619"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_replenishment_decision_evidence_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Replenishment decision evidence is immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_replenishment_decision_evidence_immutable
        BEFORE UPDATE OR DELETE ON purchasing_replenishment_decisions
        FOR EACH ROW
        EXECUTE FUNCTION reject_replenishment_decision_evidence_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_replenishment_decision_evidence_immutable
        ON purchasing_replenishment_decisions
        """
    )
    op.execute(
        "DROP FUNCTION IF EXISTS reject_replenishment_decision_evidence_mutation()"
    )
