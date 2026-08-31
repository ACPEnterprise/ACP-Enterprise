"""Protect immutable Customer Migration cutover-readiness evidence.

Revision ID: g3f1e39z6x2v
Revises: f2e0d28y5w1u
"""

from alembic import op

revision = "g3f1e39z6x2v"
down_revision = "f2e0d28y5w1u"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_cutover_readiness_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'cutover readiness evidence is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_customer_migration_cutover_readiness_immutable
        BEFORE UPDATE OR DELETE
        ON customer_migration_cutover_readiness_evidence
        FOR EACH ROW EXECUTE FUNCTION reject_cutover_readiness_evidence_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_customer_migration_cutover_readiness_immutable
        ON customer_migration_cutover_readiness_evidence
        """
    )
    op.execute("DROP FUNCTION IF EXISTS reject_cutover_readiness_evidence_mutation()")
