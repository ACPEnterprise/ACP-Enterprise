"""Protect append-only native Customer and Location identity evidence.

Revision ID: h4g2f40a7y3w
Revises: g3f1e39z6x2v
"""

from alembic import op

revision = "h4g2f40a7y3w"
down_revision = "g3f1e39z6x2v"
branch_labels = None
depends_on = None

TABLES = (
    "customer_identity_consolidation_evidence",
    "service_location_identity_evidence",
    "service_location_reconciliation_evidence",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_native_identity_evidence_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'native identity evidence is immutable'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable "
            f"BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_native_identity_evidence_mutation()"
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_native_identity_evidence_mutation()")
